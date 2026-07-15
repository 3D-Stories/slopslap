"""The live-orchestration seam: audit -> candidate -> verify -> apply for an arbitrary doc (#27).

Design: docs/planning/2026-07-12-27-live-orchestration-seam.md. This module is the missing assembler
the v0.2 epic wants — it derives a ledger manifest from any UTF-8 doc, verifies a candidate
edit-script against it, and (dry-run) routes the shippable subset through the backup-gated apply
engine. Every stage returns a uniform envelope (``StageResult``); one run returns a ``RunResult``
whose overall status is the worst stage status and whose CLI exit code is a static class map.

Ponytail: one module (the peer's 3-file layout is deferred until it outgrows ~500 lines). The seam
NEVER shells out to scan_prose.py's CLI; it calls the scan/verify/apply library APIs directly and
resolves genre ONCE, threading it to both the metrics run and the range deriver.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
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
from slopslap_verification.editscript import Edit, apply_edits, parse_edits  # noqa: E402
from slopslap_verification.ledger import (  # noqa: E402
    Ledger,
    LedgerBuildError,
    build_ledger,
    verify,
)
from slopslap_apply.apply import apply_selective  # noqa: E402

SCHEMA_VERSION = 1

# Static code-slug -> CLI exit class (§4.3 table). NO runtime judgment, no message sniffing.
#   0 ok · 2 policy-blocked · 3 invalid input/contract · 4 stage execution failure.
# ``upstream_not_ok`` is DELIBERATELY absent — it tags only ``aborted`` stages and never drives
# the exit code (an aborted stage always sits downstream of the exit-determining failure/block).
_EXIT_CLASS = {
    "ok": 0,
    # policy-blocked (2)
    "verify_not_shippable": 2,
    "candidate_empty": 2,
    "apply_blocked": 2,
    # invalid input / contract (3)
    "invalid_edits": 3,
    "invalid_decisions": 3,       # #62: untrusted decisions.json rejected (schema/id/sha) — pre-mutation
    "conflicting_decisions": 3,   # #62: two approved decisions target one span with different edits
    "path_mismatch": 3,
    "digest_mismatch": 3,
    "genre_error": 3,
    # stage execution failure (4)
    "protected_span_error": 4,
    "diagnosis_error": 4,
    "ledger_build_error": 4,
    "semantic_invocation_failed": 4,
    "verify_error": 4,
    "apply_error": 4,
}

# worst-of total order for the overall RunResult status: failed > blocked > aborted > ok.
_STATUS_RANK = {"failed": 3, "blocked": 2, "aborted": 1, "ok": 0}


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


@dataclass
class RunResult:
    """One end-to-end run. ``status`` is the worst stage status (``_STATUS_RANK``); ``audit`` /
    ``verification`` / ``apply`` are convenience summaries (the stage ``data``), None when a stage
    was not reached. ``run_id`` is the audit's deterministic id ("" if audit never produced one)."""

    schema_version: int
    run_id: str
    status: str
    stages: List[StageResult]
    audit: Any = None            # AuditResult | None
    verification: Any = None     # verify_result dict | None
    apply: Any = None            # apply report dict | None
    # "live" | "offline_stub" | "injected" | "n/a" — machine-distinguishable so a consumer can tell
    # a real Layer-3 semantic pass from an offline/stubbed one (adversarial-diff High). "n/a" when
    # the run never reached verify (semantic_fn never executed).
    semantic_mode: str = "n/a"


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


def _has_strip_candidate(metrics: dict, genre: str) -> bool:
    """True iff some metric the genre RECOMMENDS ``strip`` carries a location or a doc-level
    ``soft_flag`` — i.e. the doc has an ACTIONABLE tell (something to strip), as opposed to being
    flagged only by genre-KEPT tells (keystone v2 / #59). The empty-candidate 'flagged' block keys on
    THIS, not on bare ``audit_status``: adv A1's intent is "never silently pass actionable slop", and
    after the #59 flip a genre-kept-only doc stays ``audit_status="flagged"`` (locations survive) even
    though its genre-correct answer is 'no edits'. Gating on a strip candidate keeps that a legitimate
    no-op while still blocking an empty candidate whenever there is real slop to strip."""
    for name, res in metrics.items():
        if met.recommend(genre, name) == "strip" and (res.get("locations") or res.get("soft_flag")):
            return True
    return False


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


# --------------------------------------------------------------------------- run machinery (§4.3)
def _aborted(stage_names: List[str], cause_stage: str) -> List[StageResult]:
    """Explicit ``aborted`` results for every stage that did not run because ``cause_stage`` was
    not ``ok`` (peer key-decision: never a silent partial run). Never exit-determining."""
    return [StageResult(name, "aborted", "upstream_not_ok",
                        f"not run: upstream stage {cause_stage!r} was not ok", data=None)
            for name in stage_names]


def _overall_status(stages: List[StageResult]) -> str:
    return max((s.status for s in stages), key=lambda s: _STATUS_RANK[s])


def _build_run(run_id: str, stages: List[StageResult], semantic_mode: str = "n/a") -> RunResult:
    audit = verification = apply_rep = None
    for s in stages:
        if s.stage == "audit" and s.status == "ok":
            audit = s.data
        elif s.stage == "verify":
            verification = s.data      # preserved even when blocked (full verify_result)
        elif s.stage == "apply":
            apply_rep = s.data
    return RunResult(SCHEMA_VERSION, run_id, _overall_status(stages), stages,
                     audit=audit, verification=verification, apply=apply_rep,
                     semantic_mode=semantic_mode)


def _semantic_mode(semantic_fn) -> str:
    """How the Layer-3 verdict was produced (adversarial-diff High): ``live_semantic_fn`` tags itself
    ``live``/``offline_stub``; a test-injected callable with no marker reads ``injected`` — a
    consumer can then tell a real semantic pass from a stubbed/deterministic-only one."""
    return getattr(semantic_fn, "semantic_mode", "injected")


def exit_code(run: RunResult) -> int:
    """CLI exit code, derived mechanically from the FIRST non-ok (blocked/failed) stage's code via
    the static ``_EXIT_CLASS`` map. ``aborted`` stages are skipped (they carry ``upstream_not_ok``,
    which is never exit-determining). All-ok -> 0."""
    for st in run.stages:
        if st.status in ("blocked", "failed"):
            return _EXIT_CLASS[st.code]
    return 0


def _coerce_edits(edits_input) -> List[Edit]:
    """Accept either a list of ``Edit`` objects or the envelope dict form (parse_edits)."""
    if edits_input and isinstance(edits_input[0], Edit):
        return list(edits_input)
    return parse_edits(edits_input or [])


def _sink_status(semantic_fn) -> str:
    """The typed invocation outcome the seam's semantic_fn recorded (#27 §7). A plain injected
    callable with no ``status_sink`` reads ``ok`` (no false ops-failure)."""
    sink = getattr(semantic_fn, "status_sink", None)
    if not isinstance(sink, dict):
        return "ok"
    return sink.get("invocation_status", "ok")


def live_semantic_fn(model: str = "sonnet", timeout_s: float = 120.0):
    """The seam's Layer-3 ``semantic_fn`` factory (§5, §7). LIVE (``SLOPSLAP_LIVE=="1"``): the real
    ``invoke_semantic`` bound to ``model``/``timeout_s`` with a FRESH sticky ``status_sink`` — a
    genuine fresh-context ``claude -p`` pass. OFFLINE (default): a hardcoded ``clean`` stub, no
    model call, no import of the live transport. Either way the returned callable exposes
    ``.status_sink`` so ``run_candidate`` can reclassify an ops failure to
    ``semantic_invocation_failed``. Deliberately NOT a reuse of ``eval.semantic`` (self-review F3):
    the seam owns its own sink-injecting factory; the eval package stays a frozen proof."""
    sink: dict = {}
    if os.environ.get("SLOPSLAP_LIVE") == "1":
        import functools

        from slopslap_invoke.invoke import invoke_semantic
        bound = functools.partial(invoke_semantic, model=model, timeout_s=timeout_s,
                                  status_sink=sink)

        def fn(original, revision, ledger_canonical):
            return bound(original, revision, ledger_canonical)
        fn.semantic_mode = "live"
    else:
        def fn(original, revision, ledger_canonical):
            return {"verdict": "clean", "concerns": []}
        fn.semantic_mode = "offline_stub"

    fn.status_sink = sink
    return fn


def run_candidate(audit: AuditResult, edits, *, semantic_fn=None, write: bool = False,
                  apply_config=None) -> RunResult:
    """CANDIDATE -> VERIFY -> APPLY against an already-audited snapshot. Returns one ``RunResult``
    with the full 4-stage story (a synthesized ``audit`` ok stage first, then the three it runs).

    - candidate: source-identity re-check (path + digest, adv A6) + edit-script validation
      (parse + bounds/overlap, BEFORE verify, adv A5) + empty-candidate policy (keyed on
      ``audit_status``, adv A1).
    - verify: ``ledger.verify`` with the authorization ranges + semantic_fn; non-shippable is a
      policy ``blocked`` (full verify_result preserved), UNLESS the ``status_sink`` reports an ops
      failure, which is ``failed``/``semantic_invocation_failed`` (adv A2).
    - apply: only when verify is shippable; routes through the backup-gated ``apply_selective`` with
      a verify_fn CLOSED over this run's ledger/ranges/semantic_fn. Aborted when verify is not ok.
    """
    if semantic_fn is None:
        semantic_fn = live_semantic_fn()
    mode = _semantic_mode(semantic_fn)  # surfaced in RunResult from the verify stage onward
    audit_stage = StageResult("audit", "ok", "ok", "audit complete", data=audit)

    def _abort_after_candidate(cand: StageResult) -> RunResult:
        return _build_run(audit.run_id, [audit_stage, cand] + _aborted(["verify", "apply"], "candidate"))

    # --- candidate: source-identity boundary re-check (path BEFORE digest so identical bytes at a
    #     different path still fail as path_mismatch, adv A6) ---
    src = audit.source_path
    if os.path.realpath(src) != src:
        return _abort_after_candidate(_stage_fail(
            "candidate", "path_mismatch",
            "source path no longer resolves to the audited file (symlink/identity changed since audit)"))
    try:
        with open(src, "rb") as fh:
            original = fh.read()
    except OSError as err:
        return _abort_after_candidate(_stage_fail(
            "candidate", "digest_mismatch", f"cannot re-read audited source: {err}"))
    if hashlib.sha256(original).hexdigest() != audit.source_sha256:
        return _abort_after_candidate(_stage_fail(
            "candidate", "digest_mismatch", "source changed since audit (sha256 mismatch)"))

    # --- candidate: parse + validate the edit-script BEFORE verify (adv A5) ---
    try:
        parsed = _coerce_edits(edits)
        apply_edits(original, parsed)  # public validator: raises EditError on bounds/overlap
    except (ValueError, TypeError, KeyError) as err:  # EditError/binascii.Error subclass ValueError
        return _abort_after_candidate(_stage_fail("candidate", "invalid_edits", str(err)))

    # --- candidate: empty-candidate policy (adv A1 + keystone v2 #59). Block an empty candidate iff
    #     the genre RECOMMENDS stripping at least one detected tell — a missing model output on
    #     actionable slop is never a silent pass. Keyed on `_has_strip_candidate` ALONE, not on
    #     `audit_status`: a strip candidate (some metric with a strip recommendation + location/
    #     soft_flag) implies audit_status=="flagged" by construction, so the extra check was redundant
    #     and only added a silent-pass hole on a stale/tampered audit_status. A doc flagged only by
    #     genre-KEPT tells has nothing to strip, so its empty candidate is a legitimate no-op. ---
    if not parsed:
        if _has_strip_candidate(audit.metrics, audit.genre):
            return _build_run(audit.run_id, [
                audit_stage,
                StageResult("candidate", "blocked", "candidate_empty",
                            "empty candidate on a flagged audit with strip-recommended tells: a "
                            "missing model output is never a silent pass", data=[]),
            ] + _aborted(["verify", "apply"], "candidate"))
        # clean audit, OR flagged only by genre-kept tells: nothing to strip -> a legitimate no-op
        return _build_run(audit.run_id, [
            audit_stage,
            StageResult("candidate", "ok", "ok",
                        "empty candidate with no strip-recommended tells: no-op", data=[]),
        ])
    candidate_stage = StageResult("candidate", "ok", "ok", "candidate validated", data=parsed)

    # --- verify: one audit, one policy. authorization state chooses the ranges arg ---
    authorized = None if audit.authorization["state"] == "locality_unverified" \
        else audit.authorization["ranges"]
    try:
        verify_result = verify(original, parsed, audit.ledger,
                               authorized_ranges=authorized, semantic_fn=semantic_fn)
    except Exception as err:  # noqa: BLE001 - the seam never raises past a stage (§4.3)
        verify_stage = StageResult("verify", "failed", "verify_error",
                                   f"verify raised {type(err).__name__}", data=None,
                                   errors=[{"code": "verify_error", "detail": repr(err)}])
        return _build_run(audit.run_id, [audit_stage, candidate_stage, verify_stage]
                          + _aborted(["apply"], "verify"), mode)
    shippable = (verify_result["decision"] == "ACCEPT"
                 and verify_result["proposal_status"] == "ACCEPT"
                 and verify_result["semantic_status"] == "clean")
    sink_status = _sink_status(semantic_fn)

    if not shippable and sink_status != "ok":
        # an OPS failure (transport/timeout/parse), not a policy verdict (adv A2) — exit 4, not 2.
        verify_stage = StageResult(
            "verify", "failed", "semantic_invocation_failed",
            f"semantic invocation failed (status={sink_status}); an ops failure is not a policy "
            f"verdict", data=verify_result,
            errors=[{"code": "semantic_invocation_failed", "invocation_status": sink_status}])
        return _build_run(audit.run_id, [audit_stage, candidate_stage, verify_stage]
                          + _aborted(["apply"], "verify"), mode)
    if not shippable:
        verify_stage = StageResult(
            "verify", "blocked", "verify_not_shippable",
            f"proposal not shippable (decision={verify_result['decision']}, "
            f"proposal_status={verify_result['proposal_status']}, "
            f"semantic_status={verify_result['semantic_status']})", data=verify_result)
        return _build_run(audit.run_id, [audit_stage, candidate_stage, verify_stage]
                          + _aborted(["apply"], "verify"), mode)
    verify_stage = StageResult("verify", "ok", "ok", "proposal is shippable", data=verify_result)

    # --- apply: backup-gated, re-verifying against the untouched original each attempt. `write`
    #     flows through to the engine (#29 enablement): write=False stages a dry-run (verify + report,
    #     no mutation); write=True performs the real backup-first atomic replacement. Every mutation
    #     stays gated by the mandatory verified backup + the 3-layer verifier (#21/#27 machinery) —
    #     apply_selective fails closed on a backup failure, so enablement never bypasses the gate. ---
    def _bound_verify(orig_bytes, es):
        return verify(orig_bytes, es, audit.ledger,
                      authorized_ranges=authorized, semantic_fn=semantic_fn)

    try:
        report = apply_selective(src, parsed, _bound_verify, config=apply_config, write=write)
    except Exception as err:  # noqa: BLE001 - the seam never raises past a stage (§4.3)
        # apply_selective catches its own OSErrors and returns reports, so this is a backstop for an
        # UNEXPECTED raise. If a backup was already written it lives in the configured backup dir —
        # name it so recovery is possible even though the report was lost (adv-diff M4).
        apply_stage = StageResult("apply", "failed", "apply_error",
                                  f"apply raised {type(err).__name__}; if a backup was written it is in "
                                  f"the configured backup dir — check it before retrying", data=None,
                                  errors=[{"code": "apply_error", "detail": repr(err)}])
        return _build_run(audit.run_id, [audit_stage, candidate_stage, verify_stage, apply_stage], mode)

    # apply's re-verify loop re-invokes semantic_fn against the SAME sticky sink (§7). Re-read it:
    # an ops failure that struck ONLY during apply (verify-stage call succeeded, a later re-verify
    # timed out) must surface as semantic_invocation_failed / exit 4 — never laundered into a
    # policy `blocked` or a clean `applied` (adv A2, Step-8a High). Sticky-worst makes the read
    # meaningful across the multi-call loop.
    st = report.get("status")
    apply_sink_status = _sink_status(semantic_fn)
    if apply_sink_status != "ok":
        apply_stage = StageResult(
            "apply", "failed", "semantic_invocation_failed",
            f"semantic invocation failed during apply (status={apply_sink_status}); an ops failure "
            f"is not a policy verdict", data=report,
            errors=[{"code": "semantic_invocation_failed", "invocation_status": apply_sink_status}])
    elif st in ("applied", "no_op"):
        warns = list(report.get("warnings", []))
        # A real mutation whose Layer-3 semantic check was NOT a live model (offline stub / injected)
        # rests on the deterministic layers alone — legible in the output, not just the docs (adv-diff
        # H1). Meaning-changing edits that preserve every syntactic invariant are the residual risk.
        if write and st == "applied" and mode != "live":
            warns.append(f"applied on the DETERMINISTIC layers only (semantic_mode={mode}); the "
                         f"Layer-3 semantic check was not a live model — set SLOPSLAP_LIVE=1 for a "
                         f"model-verified apply")
        apply_stage = StageResult("apply", "ok", "ok", f"apply {st}", data=report, warnings=warns)
    elif st == "blocked":
        apply_stage = StageResult("apply", "blocked", "apply_blocked",
                                  "apply blocked (backup/attribution/convergence)", data=report,
                                  errors=[{"code": "apply_blocked", "errors": report.get("errors", [])}])
    else:  # "error" or any unexpected relayed status -> execution failure (exit 4)
        apply_stage = StageResult("apply", "failed", "apply_error",
                                  f"apply reported status={st!r}", data=report,
                                  errors=[{"code": "apply_error", "errors": report.get("errors", [])}])
    return _build_run(audit.run_id, [audit_stage, candidate_stage, verify_stage, apply_stage], mode)


def assemble(path: str, edits, *, fmt: str = "markdown", declared_genre: Optional[str] = None,
             semantic_fn=None, write: bool = False, apply_config=None) -> RunResult:
    """Audit ``path`` then run the candidate ``edits`` end-to-end (audit + run in one call).

    If the audit stage fails, candidate/verify/apply are explicitly ``aborted`` and the failed audit
    drives the exit code. (``apply_config`` threads a ``BackupConfig`` through to ``apply_selective``
    — needed so the dry-run golden can point the mandatory backup at a test-owned dir.)
    """
    audit_stage = audit_document(path, fmt=fmt, declared_genre=declared_genre)
    if audit_stage.status != "ok":
        run_id = audit_stage.data.run_id if isinstance(audit_stage.data, AuditResult) else ""
        return _build_run(run_id, [audit_stage] + _aborted(["candidate", "verify", "apply"], "audit"))
    return run_candidate(audit_stage.data, edits, semantic_fn=semantic_fn, write=write,
                         apply_config=apply_config)


# --------------------------------------------------------------------------- JSON CLI (§4.4)
def _edit_json(e: Edit) -> dict:
    return {"start_byte": e.start_byte, "end_byte": e.end_byte,
            "replacement_b64": base64.b64encode(e.replacement).decode("ascii")}


def _audit_json(a: AuditResult) -> dict:
    """Serialize an AuditResult with NO source bytes: the ledger becomes
    ``{"canonical": ..., "sha256": ...}`` (never a raw pickled Ledger), and only the sha256 +
    byte_length identify the content (§4.4 CLI hygiene)."""
    return {
        "schema_version": a.schema_version, "run_id": a.run_id,
        "source_path": a.source_path, "source_sha256": a.source_sha256,
        "byte_length": a.byte_length, "fmt": a.fmt,
        "genre": a.genre, "genre_confidence": a.genre_confidence, "genre_reason": a.genre_reason,
        "audit_status": a.audit_status, "metrics": a.metrics,
        "authorization": a.authorization, "protected_spans": a.protected_spans,
        "invariant_regions": a.invariant_regions,
        "ledger": {"canonical": a.ledger.canonical_obj(), "sha256": a.ledger.ledger_sha256()},
    }


def _data_json(data: Any) -> Any:
    if isinstance(data, AuditResult):
        return _audit_json(data)
    if isinstance(data, list) and data and isinstance(data[0], Edit):
        return [_edit_json(e) for e in data]
    return data  # verify_result / apply report dicts are already JSON-safe (no bytes); None/[] pass


def _run_to_json(run: RunResult) -> dict:
    """The wire form: schema_version, run_id, overall status, and each stage's envelope. Source
    bytes never appear; the in-process ``RunResult.audit``/``verification``/``apply`` summaries are
    NOT duplicated at top level (the stage ``data`` already carries them)."""
    return {
        "schema_version": run.schema_version,
        "run_id": run.run_id,
        "status": run.status,
        "semantic_mode": run.semantic_mode,  # live | offline_stub | injected | n/a (adversarial-diff High)
        "stages": [
            {"stage": s.stage, "status": s.status, "code": s.code, "message": s.message,
             "data": _data_json(s.data), "errors": s.errors, "warnings": s.warnings}
            for s in run.stages
        ],
    }


def apply_from_decisions(path: str, decisions_path: str, *, fmt: str = "markdown",
                         declared_genre: Optional[str] = None, semantic_fn=None, write: bool = True,
                         apply_config=None, log_feedback: bool = False,
                         feedback_ledger_path=None) -> RunResult:
    """Apply ONLY the user-approved (apply/edit) hunks of a review ``decisions.json`` (#62/P4).

    The verifier + mandatory verified backup + atomic pathname replacement are the UNCHANGED engine
    (``run_candidate`` → ``apply_selective``). The only new inputs are (a) the approved edit-script and
    (b) the authorization ranges — which, per keystone v2, come from the USER's accepted findings, NOT
    the genre strip-gate. ``decisions.json`` is UNTRUSTED: schema-validated, its finding-ids matched
    against the audit's own findings, and bound to ``source_sha256`` (a drifted file → digest_mismatch
    inside run_candidate). A user-approved hunk the verifier rejects is surfaced blocked, never applied;
    an all-discard/undecided set is a clean no-op (the user's decision, not a missing model output).

    ``log_feedback`` (#63/P5, OPT-IN — the ``apply`` CLI turns it on; OFF for library/test callers so
    they never write the user's real ledger) appends every validated decision to the local feedback
    ledger best-effort AFTER validation. This is pure OBSERVATION for later learning — it never changes
    the authorization, the edits, or the verifier verdict (a ledger-write failure is swallowed)."""
    import dataclasses  # noqa: PLC0415
    from slopslap_review.findings import FindingsError, build_findings  # noqa: PLC0415 (review-layer; lazy avoids a load cycle)
    from slopslap_review.schema import validate_decisions_for_apply  # noqa: PLC0415

    stage = audit_document(path, fmt=fmt, declared_genre=declared_genre)
    if stage.status != "ok":
        rid = stage.data.run_id if isinstance(stage.data, AuditResult) else ""
        return _build_run(rid, [stage] + _aborted(["candidate", "verify", "apply"], "audit"))
    audit = stage.data
    audit_stage = StageResult("audit", "ok", "ok", "audit complete", data=audit)

    def _cand_fail(code, msg, errors=None):
        return _build_run(audit.run_id, [audit_stage, StageResult(
            "candidate", "failed", code, msg, data=None,
            errors=errors or [{"code": code, "message": msg}])] + _aborted(["verify", "apply"], "candidate"))

    # re-read the source + rebuild findings; a file change since the audit read → clean digest_mismatch
    # (FindingsError) rather than an uncaught crash (the run_candidate digest recheck also guards it).
    try:
        with open(audit.source_path, "rb") as fh:
            doc = fh.read()
        by_id = {f.id: f for f in build_findings(audit, doc)}
    except OSError as err:
        return _cand_fail("digest_mismatch", f"cannot re-read audited source: {err}")
    except FindingsError as err:
        return _cand_fail("digest_mismatch", f"source changed since audit: {err}")

    try:
        with open(decisions_path, "r", encoding="utf-8") as fh:
            decisions_obj = json.load(fh)
    except (OSError, ValueError) as err:
        return _cand_fail("invalid_decisions", f"cannot read --decisions: {err}")
    # UNTRUSTED boundary: both replay bindings REQUIRED (finding-ids matched + source_sha256 bound).
    problems = validate_decisions_for_apply(
        decisions_obj, audit_finding_ids=set(by_id), expected_source_sha256=audit.source_sha256,
        alternative_ids={fid: {a["id"] for a in f.alternatives or []} for fid, f in by_id.items()})
    if problems:
        return _cand_fail("invalid_decisions", "; ".join(problems)[:400],
                          errors=[{"code": "invalid_decisions", "detail": problems}])

    # #63/P5: OBSERVE the validated decisions for later learning (opt-in; best-effort). This records
    # what the user decided — it NEVER feeds authorization or the verifier (those come from the user's
    # accepted findings + the byte-exact gate below). A ledger-write failure must not fail the apply.
    if log_feedback:
        try:
            from slopslap_review.feedback import append_feedback  # noqa: PLC0415 (review-layer; lazy)
            append_feedback(decisions_obj, list(by_id.values()), audit.genre, path=feedback_ledger_path)
        except Exception:  # noqa: BLE001 — observation only; never break the mutating path
            pass

    edits, spans, seen = [], [], {}
    for d in decisions_obj["decisions"]:
        action = d["user_action"]
        if action == "discard":
            continue  # discarded/undecided → left untouched
        f = by_id[d["finding_id"]]  # validated present by validate_decisions_for_apply
        s, e = f.span["start"], f.span["end"]
        repl_b64 = d["replacement"] if action == "edit" else ""  # apply strip = delete the span
        if (s, e) in seen:
            if seen[(s, e)] != repl_b64:
                return _cand_fail("conflicting_decisions",
                                  f"two approved decisions target the same span [{s},{e}) with different edits")
            continue  # identical edit for the same span already recorded
        seen[(s, e)] = repl_b64
        edits.append({"start_byte": s, "end_byte": e, "replacement_b64": repl_b64})
        spans.append({"start_byte": s, "end_byte": e})

    if not edits:  # all-discard / undecided → a legitimate no-op (the user's decision), never a block
        return _build_run(audit.run_id, [audit_stage, StageResult(
            "candidate", "ok", "ok", "no approved hunks (all discard/undecided): no-op", data=[])])

    # keystone v2: the USER authorizes the edited spans — override the genre-derived authorization.
    audit = dataclasses.replace(audit, authorization={"state": "authorized", "ranges": spans})
    return run_candidate(audit, edits, semantic_fn=semantic_fn, write=write, apply_config=apply_config)


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slopslap-assemble",
        description="Live-orchestration seam (#27): audit / dry-run a candidate against any doc.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("audit", help="audit a document; emit one JSON RunResult")
    pa.add_argument("--path", required=True)
    pa.add_argument("--declared-genre", default=None)
    pa.add_argument("--format", default="markdown", choices=("markdown", "text"))

    pr = sub.add_parser("run", help="dry-run a candidate edit-script end-to-end (never mutates)")
    pr.add_argument("--path", required=True)
    pr.add_argument("--edits", required=True, help="path to a JSON edit-script (list of edits, or {\"edits\": [...]})")
    pr.add_argument("--declared-genre", default=None)
    pr.add_argument("--format", default="markdown", choices=("markdown", "text"))
    # `run` is DRY-RUN ONLY — the safe default preview. --dry-run is always on; kept for explicitness.
    pr.add_argument("--dry-run", action="store_true", default=True)

    # #29 enablement: `apply` is the explicit MUTATING path (write=True) — a separate subcommand, not a
    # flag on `run`, so a real file mutation can never be triggered by omitting/mistyping a flag. Every
    # apply stays backup-gated + verifier-gated (apply_selective fails closed on backup failure).
    pap = sub.add_parser("apply", help="APPLY approved edits to the file (mutates, backup-gated)")
    pap.add_argument("--path", required=True)
    src = pap.add_mutually_exclusive_group(required=True)
    src.add_argument("--edits", help="path to a JSON edit-script (list of edits, or {\"edits\": [...]})")
    src.add_argument("--decisions",
                     help="path to a review decisions.json — apply ONLY the approved (apply/edit) hunks (#62/P4)")
    pap.add_argument("--declared-genre", default=None)
    pap.add_argument("--format", default="markdown", choices=("markdown", "text"))
    pap.add_argument("--no-feedback", action="store_true",
                     help="do NOT append the applied decisions to the local learning ledger (#63/P5)")
    return parser


def main(argv=None) -> int:
    """CLI entry: ``audit`` / ``run`` (dry-run) / ``apply`` (mutating) subcommands, exactly one JSON
    RunResult to stdout, diagnostics to stderr, exit code via the static ``_EXIT_CLASS`` map (0/2/3/4)."""
    parser = _build_argparser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: 0 for --help, 2 for bad args -> map bad args to exit 3
        return 0 if exc.code in (0, None) else 3

    if args.cmd == "audit":
        stage = audit_document(args.path, fmt=args.format, declared_genre=args.declared_genre)
        run_id = stage.data.run_id if isinstance(stage.data, AuditResult) else ""
        run = _build_run(run_id, [stage])
        sys.stdout.write(json.dumps(_run_to_json(run)) + "\n")
        return exit_code(run)

    # apply --decisions: apply ONLY the user-approved hunks of a review decisions.json (#62/P4).
    if args.cmd == "apply" and getattr(args, "decisions", None):
        run = apply_from_decisions(args.path, args.decisions, fmt=args.format,
                                   declared_genre=args.declared_genre, semantic_fn=live_semantic_fn(),
                                   write=True, log_feedback=not args.no_feedback)
        sys.stdout.write(json.dumps(_run_to_json(run)) + "\n")
        return exit_code(run)

    # cmd in ("run", "apply") — `apply` is the ONLY mutating path (write=True); `run` is dry-run only.
    write = args.cmd == "apply"
    try:
        with open(args.edits, "r", encoding="utf-8") as fh:
            edits_input = json.load(fh)
    except (OSError, ValueError) as err:
        # Honor §4.4: every invocation emits exactly one JSON RunResult to stdout (diagnostic to
        # stderr), so a machine consumer never has to special-case bad --edits.
        sys.stderr.write(f"slopslap-assemble: cannot read --edits {args.edits!r}: {err}\n")
        bad = _build_run("", [StageResult("candidate", "failed", "invalid_edits",
                                          f"cannot read --edits: {err}", data=None,
                                          errors=[{"code": "invalid_edits", "detail": str(err)}])])
        sys.stdout.write(json.dumps(_run_to_json(bad)) + "\n")
        return exit_code(bad)  # invalid input / contract -> 3
    if isinstance(edits_input, dict) and "edits" in edits_input:
        edits_input = edits_input["edits"]

    run = assemble(args.path, edits_input, fmt=args.format, declared_genre=args.declared_genre,
                   semantic_fn=live_semantic_fn(), write=write)
    sys.stdout.write(json.dumps(_run_to_json(run)) + "\n")
    return exit_code(run)


if __name__ == "__main__":
    raise SystemExit(main())
