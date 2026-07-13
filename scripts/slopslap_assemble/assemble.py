"""The live-orchestration seam: audit -> candidate -> verify -> apply for an arbitrary doc (#27).

Design: docs/planning/2026-07-12-live-orchestration-seam.md. This module is the missing assembler
the v0.2 epic wants — it derives a ledger manifest from any UTF-8 doc, verifies a candidate
edit-script against it, and (dry-run) routes the shippable subset through the backup-gated apply
engine. Every stage returns a uniform envelope (``StageResult``); one run returns a ``RunResult``
whose overall status is the worst stage status and whose CLI exit code is a static class map.

Ponytail: one module (the peer's 3-file layout is deferred until it outgrows ~500 lines). The seam
NEVER shells out to scan_prose.py's CLI; it calls the scan/verify/apply library APIs directly and
resolves genre ONCE, threading it to both the metrics run and the range deriver.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_scan import EXTRACTION_PROFILE, TEXT_PROFILE  # noqa: E402
from slopslap_scan import diagnoses  # noqa: E402
from slopslap_scan import extract as ext  # noqa: E402
from slopslap_scan import metrics as met  # noqa: E402
from slopslap_scan.diagnoses import DiagnosisError, authorized_ranges_from_diagnoses  # noqa: E402
from slopslap_scan.genre import GenreError, classify_genre  # noqa: E402
from slopslap_scan.protected import ProtectedSpanError, extract_protected_spans  # noqa: E402
from slopslap_verification.autoledger import build_invariant_regions  # noqa: E402
from slopslap_verification.ledger import Ledger, LedgerBuildError, build_ledger  # noqa: E402

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- data contracts (§4)
@dataclass(frozen=True)
class AuditResult:
    """The single audit-stage aggregate (§4.1). Snapshot-immutable — the candidate edit-script is
    an explicit input to verify/run, NEVER part of this object."""

    schema_version: int
    run_id: str                 # deterministic short hash of source_sha256 (golden-stable)
    source_path: str            # RESOLVED absolute path (policy binds to file identity, adv A6)
    source_sha256: str
    byte_length: int
    fmt: str                    # "markdown" | "text"
    genre: str
    genre_confidence: str
    genre_reason: str
    audit_status: str           # "clean" | "flagged" (adv A1)
    metrics: dict
    authorization: dict         # {"state": authorized|reject_all|locality_unverified, "ranges": [...] | None}
    protected_spans: List[dict]
    invariant_regions: List[dict]
    ledger: Ledger


@dataclass
class StageResult:
    """Uniform per-stage envelope so a failure is legible and never silent (§4.3)."""

    stage: str                  # "audit" | "candidate" | "verify" | "apply"
    status: str                 # "ok" | "blocked" | "failed" | "aborted"
    code: str                   # stable slug (see _EXIT_CLASS)
    message: str = ""
    data: Any = None            # AuditResult | edits | verify_result | apply report | None
    errors: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _stage_fail(stage: str, code: str, message: str) -> StageResult:
    return StageResult(stage, "failed", code, message, data=None,
                       errors=[{"code": code, "message": message}])


# --------------------------------------------------------------------------- manifest glue (§4.1)
def build_manifest(doc: bytes) -> dict:
    """The missing glue: derive a ``build_ledger`` manifest from an arbitrary UTF-8 doc.

    ``{"invariant_regions": build_invariant_regions(doc), "protected_spans":
    extract_protected_spans(doc)}``. A doc with no invariant regions and no protected spans yields
    an empty-but-VALID manifest (``build_ledger`` accepts it — an empty ledger is "no invariants to
    violate", never an error). Uses only ``build_ledger``'s own 7-entry ``_CHECK_KIND`` whitelist
    (which accepts cross_refs/defined_terms), so the seam's manifest path is not #36-gapped.

    Raises ``ProtectedSpanError`` (parser unavailable) or ``LedgerBuildError`` (non-UTF-8) from the
    underlying extractors — the caller (``audit_document``) maps them to typed stage failures.
    """
    return {
        "invariant_regions": build_invariant_regions(doc),
        "protected_spans": extract_protected_spans(doc),
    }


def _scan_metrics(doc: bytes, fmt: str, genre: Optional[str]) -> dict:
    """Run the measure-only scanner's ``compute_all`` for the audit-status derivation + surfacing.

    This is the SECOND of the two accepted pipeline runs (§4.1): ``authorized_ranges_from_diagnoses``
    owns range derivation, this owns metrics. Genre is threaded in from the single ``classify_genre``
    call. The markdown parser class is obtained via the SAME in-process, version-checked import the
    sibling scan modules use (``diagnoses._markdown_it_cls``) — NOT ``capability.gate`` (which
    enforces vendor-ORIGIN for a fresh CLI process and legitimately reports unavailable in a plain
    library environment); this keeps the metrics class identical to the range deriver's, so the two
    runs can never disagree about parser identity.
    """
    text = doc.decode("utf-8")  # doc already validated UTF-8 by classify_genre (owns bad bytes)
    if fmt == "markdown":
        units = ext.extract_markdown(text, diagnoses._markdown_it_cls())
        return met.compute_all(units, EXTRACTION_PROFILE, source=text, genre=genre)
    if fmt == "text":
        units = ext.extract_text(text)
        return met.compute_all(units, TEXT_PROFILE, source=text, genre=genre)
    raise DiagnosisError(f"unknown format {fmt!r}; expected 'markdown' or 'text'")


def _audit_status(metrics: dict) -> str:
    """"flagged" iff ANY metric emitted a location OR any doc-level ``soft_flag`` is true (adv A1);
    else "clean". This distinction survives the ``reject_all`` authorization overload."""
    for res in metrics.values():
        if res.get("locations") or res.get("soft_flag") is True:
            return "flagged"
    return "clean"


def _authorization(ranges: List[dict]) -> dict:
    """Encode the ranges into an explicit authorization state (peer contribution, resolves the
    ``[]``/``None`` overload). ``audit_document`` always derives, so it yields authorized or
    reject_all; ``locality_unverified`` (ranges None) is reachable only via an explicit opt-out."""
    if ranges:
        return {"state": "authorized", "ranges": ranges}
    return {"state": "reject_all", "ranges": []}


def _run_id(source_sha256: str) -> str:
    return source_sha256[:12]


# --------------------------------------------------------------------------- audit stage (§4.2)
def audit_document(path: str, *, fmt: str = "markdown",
                   declared_genre: Optional[str] = None) -> StageResult:
    """AUDIT stage: read the file, classify genre ONCE, derive ranges + metrics + protected spans +
    invariant regions + ledger, and package a snapshot-immutable ``AuditResult``.

    ``classify_genre`` runs FIRST and OWNS bad-bytes (raises ``GenreError`` on non-UTF-8), so every
    decode failure surfaces as ``genre_error`` (exit 3) before diagnoses/protected/autoledger run;
    ``diagnosis_error`` is therefore parser-unavailable-only (exit 4). Returns a ``StageResult``:
    ``ok`` with the ``AuditResult`` in ``data``, or ``failed`` with the typed ``code``.
    """
    resolved = os.path.realpath(os.path.abspath(path))
    try:
        with open(resolved, "rb") as fh:
            doc = fh.read()
    except OSError as err:
        return _stage_fail("audit", "genre_error", f"cannot read source {path!r}: {err}")

    try:
        gi = classify_genre(doc, declared=declared_genre, path=resolved)
    except GenreError as err:
        return _stage_fail("audit", "genre_error", str(err))
    genre = gi["genre"]

    try:
        ranges = authorized_ranges_from_diagnoses(doc, fmt, genre)
        metrics = _scan_metrics(doc, fmt, genre)
    except DiagnosisError as err:
        return _stage_fail("audit", "diagnosis_error", str(err))

    try:
        manifest = build_manifest(doc)
    except ProtectedSpanError as err:
        return _stage_fail("audit", "protected_span_error", str(err))
    except LedgerBuildError as err:  # non-UTF-8 (won't fire post-genre) — mapped for completeness
        return _stage_fail("audit", "ledger_build_error", str(err))

    try:
        ledger = build_ledger(doc, manifest)
    except LedgerBuildError as err:
        return _stage_fail("audit", "ledger_build_error", str(err))

    source_sha256 = hashlib.sha256(doc).hexdigest()
    audit = AuditResult(
        schema_version=SCHEMA_VERSION,
        run_id=_run_id(source_sha256),
        source_path=resolved,
        source_sha256=source_sha256,
        byte_length=len(doc),
        fmt=fmt,
        genre=genre,
        genre_confidence=gi["confidence"],
        genre_reason=gi["reason"],
        audit_status=_audit_status(metrics),
        metrics=metrics,
        authorization=_authorization(ranges),
        protected_spans=manifest["protected_spans"],
        invariant_regions=manifest["invariant_regions"],
        ledger=ledger,
    )
    return StageResult("audit", "ok", "ok", "audit complete", data=audit)
