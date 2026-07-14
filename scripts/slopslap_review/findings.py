"""Findings-with-recommendations envelope (issue #59, de-slop pivot P1 / AC2).

``build_findings(audit, doc)`` turns an ``AuditResult`` (+ its source bytes) into a list of
strip-ready ``Finding``s — one per scanner metric location — each carrying:
  - the genre-gated *advisory* ``recommendation`` (``metrics.recommend``; genre NEVER authorizes),
  - a CANDIDATE ``proposed_rewrite`` (a delete of the span for ``strip``; ``None`` for ``keep``),
  - a ``verifier_precheck`` that runs the candidate through ``verify()`` Layers 1+2 (semantic not
    run) so a review UI can show "safe" vs "blocked" per finding.

The doc bytes are an EXPLICIT parameter: an ``AuditResult`` carries no bytes (it is snapshot-immutable
and byte-free) and scanner metric ``locations`` are LINE-based only, so byte spans and the verifier
precheck can only be derived from the bytes here. ``doc`` is bound to the audit by sha256 (a
drifted-file / replay guard). This module only PRODUCES findings — nothing here mutates a document,
and the ``recommendation`` is advisory: the user's review decision authorizes, the byte-exact verifier
hard-gates every applied edit (keystone v2).
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import List, Optional

from slopslap_scan import diagnoses
from slopslap_scan import extract as ext
from slopslap_scan import metrics as met
from slopslap_verification.editscript import Edit
from slopslap_verification.ledger import verify

# base64 of an empty replacement — a delete. Precomputed (b64 of b"" is "").
_DELETE_B64 = base64.b64encode(b"").decode("ascii")

# short human-readable snippet keys a scanner location may carry (first present wins).
_EVIDENCE_KEYS = ("match", "phrase", "opener", "prefix", "cluster", "adjective")


class FindingsError(ValueError):
    """The supplied ``doc`` bytes do not match the ``AuditResult`` (drifted file / replay)."""


@dataclass(frozen=True)
class Finding:
    """One strip-ready finding. ``id`` = ``f"{metric}:{start_byte}:{end_byte}"`` — content-keyed on
    the (metric, span) that is unique after dedup, stable across re-scans of the same bytes, colon-safe
    (metric names are snake_case), so it never collides on the #58 decisions-layer id guard.

    A strip finding's ``proposed_rewrite`` is a delete (empty ``replacement_b64``); a P3 consumer
    expresses accepting it as a decisions ``user_action:"apply"`` (NOT ``"edit"``, whose schema
    requires a non-empty base64 replacement)."""

    id: str
    category: str                     # the metric name (the tell's category)
    span: dict                        # {"start": int, "end": int}, half-open byte offsets
    evidence: str                     # distinct snippet(s) of the tell, "; "-joined (may be "")
    genre: str
    recommendation: str               # "strip" | "keep"
    rationale: str
    confidence: str                   # the metric's confidence tier
    proposed_rewrite: Optional[dict]  # {"start","end","replacement_b64"} for strip; None for keep
    # {"status": "deterministic_pass"|"blocked"|"n/a", "decision", "proposal_status",
    #  "semantic_status", "reason"} — status is NON-authorizing (see _precheck): deterministic_pass
    #  means Layers 1+2 clear, NOT shippable (semantic layer not run).
    verifier_precheck: dict


def _line_starts(raw: bytes) -> List[int]:
    """Byte offset of the start of each source line, plus a sentinel == len(raw). Mirrors
    ``slopslap_scan.diagnoses._line_starts`` (the established byte-offset-per-line convention);
    kept local so this producer does not depend on another module's private symbol."""
    starts = [0]
    for i, b in enumerate(raw):
        if b == 0x0A:  # '\n'
            starts.append(i + 1)
    starts.append(len(raw))
    return starts


def _evidence(loc: dict) -> str:
    for k in _EVIDENCE_KEYS:
        v = loc.get(k)
        if v:
            return str(v)
    return ""


def _extract_units(doc: bytes, fmt: str):
    """Re-extract the scanner Units for ``doc`` the SAME way the audit did (assemble._scan_metrics /
    diagnoses use these exact calls), so a location's line resolves to an identical Unit span."""
    text = doc.decode("utf-8")
    if fmt == "markdown":
        return ext.extract_markdown(text, diagnoses._markdown_it_cls())
    return ext.extract_text(text)  # fmt == "text"


def _span_for(loc: dict, units, starts, last):
    """Byte span for a scanner location, resolved to its CONTAINING Unit(s) — NOT the raw location
    line. Six metrics record only ``line_start`` (the containing Unit's start line, no ``line_end``),
    so using the location line alone would cover just the first physical line of a wrapped paragraph;
    resolving to the overlapping Unit(s) makes the finding span byte-identical to what
    ``authorized_ranges_from_diagnoses`` authorizes (diagnoses.py overlap logic, per-location here).
    Returns ``(start_byte, end_byte)`` or ``None`` for a doc-level (line-less) location."""
    ls = loc.get("line_start")
    if not isinstance(ls, int) or ls < 1:
        return None  # doc-level (no line) or a malformed/hostile <1 line number: no localizable span
    le = loc.get("line_end", ls)
    overlapping = [u for u in units if not (u.line_end < ls or u.line_start > le)]
    if not overlapping:
        # a location always sits in a unit; fall back to the raw line range if the scanner ever drifts.
        return (starts[ls - 1], starts[min(le, last)])
    s = min(u.line_start for u in overlapping)
    e = max(u.line_end for u in overlapping)
    return (starts[s - 1], starts[min(e, last)])


def _precheck(recommendation: str, doc: bytes, start: int, end: int, ledger):
    """Return (proposed_rewrite, verifier_precheck) for one finding.

    For ``keep`` there is no proposed rewrite. For ``strip`` the CANDIDATE is a delete of the span,
    run through ``verify()`` Layers 1+2 (``semantic_fn=None, allow_two_layer=True``) restricted to
    this span. We read ``decision`` (NOT ``proposal_status``, which stays BLOCKED whenever the
    semantic layer did not run).

    ``status`` is a DELIBERATELY NON-AUTHORIZING label so a downstream review UI can never read it as
    "verified shippable": ``deterministic_pass`` means only "Layers 1+2 (the deterministic gates:
    numbers/modals/negations/conditions/defined-terms/protected-spans/structure) find no violation" —
    the adversarial SEMANTIC layer (causal claims, attribution, unsupported intent) is NOT run here,
    so a ``deterministic_pass`` delete is still NOT shippable. ``proposal_status`` (always BLOCKED for
    this L1+2-only check) and ``semantic_status`` ("not_run") are carried alongside so the seam is
    unambiguous. ``blocked`` = a delete that would drop a detected invariant/protected span (a NORMAL,
    expected outcome surfaced per finding)."""
    if recommendation != "strip":
        return None, {"status": "n/a", "decision": None, "proposal_status": None,
                      "semantic_status": None, "reason": "keep recommendation: no rewrite proposed"}
    result = verify(doc, [Edit(start, end, b"")], ledger,
                    authorized_ranges=[{"start_byte": start, "end_byte": end}],
                    semantic_fn=None, allow_two_layer=True)
    decision = result["decision"]
    if decision == "ACCEPT":
        status = "deterministic_pass"
        reason = ("verifier Layers 1+2 (deterministic) find no violation; semantic layer NOT run "
                  "here — this is NOT a shippable verdict")
    else:
        status = "blocked"
        reason = "; ".join(f"{f.get('code')}: {f.get('message')}" for f in result.get("findings", [])) \
            or f"verifier decision {decision}"
    precheck = {"status": status, "decision": decision,
                "proposal_status": result.get("proposal_status"),
                "semantic_status": result.get("semantic_status"), "reason": reason}
    proposed = {"start": start, "end": end, "replacement_b64": _DELETE_B64}
    return proposed, precheck


def build_findings(audit, doc: bytes) -> List[Finding]:
    """Build the findings-with-recommendations envelope for ``audit`` over its source ``doc`` bytes.

    Raises ``FindingsError`` when ``doc`` does not hash to ``audit.source_sha256``.
    """
    if hashlib.sha256(doc).hexdigest() != audit.source_sha256:
        raise FindingsError("doc bytes do not match audit.source_sha256 (drifted file / replay)")

    starts = _line_starts(doc)
    last = len(starts) - 1
    units = _extract_units(doc, audit.fmt)

    # Collapse locations that resolve to the SAME (metric, span) into ONE finding: many tells in a
    # paragraph resolve to the same containing-Unit span, and N byte-identical delete candidates would
    # be N duplicate findings + N redundant verify() calls (and could not be jointly applied — they
    # overlap). One finding per unique (metric, span) carries the distinct evidence snippets. (One
    # verify() per unique span remains; memoizing the per-doc ledger/parse across prechecks is a
    # deeper ledger.py optimization left as a follow-up.)
    groups: dict = {}   # (metric, start, end) -> {"rec","cls","conf","evidence":[...]}
    order: list = []    # first-seen order -> stable output
    for metric_name, res in audit.metrics.items():
        recommendation = met.recommend(audit.genre, metric_name)
        cls = met.METRIC_CLASS.get(metric_name, "unclassified")
        confidence = res.get("confidence", "unknown")
        for loc in res.get("locations") or []:
            span = _span_for(loc, units, starts, last)
            if span is None:
                continue  # a doc-level metric with no localizable passage contributes no finding
            key = (metric_name, span[0], span[1])
            grp = groups.get(key)
            if grp is None:
                grp = {"rec": recommendation, "cls": cls, "conf": confidence, "evidence": []}
                groups[key] = grp
                order.append(key)
            ev = _evidence(loc)
            if ev and ev not in grp["evidence"]:
                grp["evidence"].append(ev)

    findings: List[Finding] = []
    for metric_name, start, end in order:
        grp = groups[(metric_name, start, end)]
        proposed, precheck = _precheck(grp["rec"], doc, start, end, audit.ledger)
        findings.append(Finding(
            id=f"{metric_name}:{start}:{end}",
            category=metric_name,
            span={"start": start, "end": end},
            evidence="; ".join(grp["evidence"]),
            genre=audit.genre,
            recommendation=grp["rec"],
            rationale=f"{metric_name} ({grp['cls']} class) under genre '{audit.genre}' → {grp['rec']}",
            confidence=grp["conf"],
            proposed_rewrite=proposed,
            verifier_precheck=precheck,
        ))
    return findings
