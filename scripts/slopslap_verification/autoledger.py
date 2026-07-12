"""Whole-doc invariant-region auto-extraction for arbitrary UTF-8 prose (#19).

``build_invariant_regions(doc)`` scans arbitrary prose and emits manifest
``invariant_regions`` — the SAME shape ``run_eval._kukakuka`` hand-authored — so
``slopslap_verification.ledger.build_ledger`` derives a real invariant ledger instead of a
few hardcoded spans. It REUSES the ``atoms`` deterministic detectors (no second
number/date/modal parser) and defers kind/preservation/confidence entirely to the ledger's
own ``_CHECK_KIND`` table (the design R3 per-kind table). This module only NAMES the checks
found in each sentence; it never assigns a preservation mode or confidence, so the R3 table
stays single-sourced in ``ledger.py``.

Segmentation is sentence/paragraph level (a blank line, or sentence-final punctuation
followed by whitespace). A whole sentence — not a bare token — is the region, so a
multiset-preserving edit elsewhere in the sentence is checked against the FULL region
(a bare-token region would false-REJECT any edit that merely spans an unchanged neighbour).
Ledger entries MAY overlap, so nested invariants (a number inside a normative sentence) are
fine (validate_ledger only forbids overlapping protected_spans).

Byte offsets are EXACT (UTF-8, computed by encoding the char prefix — never char offsets).
Input MUST be valid UTF-8; non-UTF-8 raises ``LedgerBuildError`` rather than silently
mis-extracting a shifted span (same fail-loud discipline as ``slopslap_scan.protected`` and
the ledger's own strict-bytes contract).
"""

from __future__ import annotations

import re
from typing import List

from . import atoms
from .ledger import LedgerBuildError

# a segment boundary: a blank line (paragraph break) OR sentence-final punctuation followed
# by whitespace. Decimals ("200.5") and dotted hosts ("api.example.com") are NOT split
# because they have no whitespace after the dot.
_BOUNDARY = re.compile(r"(?:\n[ \t]*\n)|(?:(?<=[.!?])\s+)")

# conservative defined-term patterns (LOW false-positive): an explicit definitional phrase
# ("term" means / refers to / is defined as / shall mean) or a hereafter/hereinafter marker.
# Markdown **bold** is deliberately NOT a signal: in real prose it is emphasis/labels/headings
# (e.g. "**Date:**", "**Status:**"), not a definition — matching it froze ~46% of kukakuka
# sentences lexically-exact and defeated the rewrite. Bare proper-noun runs are advisory-only
# per atoms.py, likewise excluded. (A real definitional detector is a follow-up refinement.)
_DEFINED_TERM = re.compile(
    r'"[^"\n]+"\s+(?:means|refers\s+to|is\s+defined\s+as|shall\s+mean)\b'
    r"|\b(?:hereafter|hereinafter)\b",
    re.IGNORECASE,
)


def _checks_for(segment: str) -> List[str]:
    """The invariant checks present in one sentence, as ``_CHECK_KIND`` check names.

    Dates are grouped with numbers/units (design decision #5: dates -> lexically_exact,
    same as numbers) — any date carries digits the quantity extractor catches, and a
    month-name change is caught doc-wide by Layer-1's date claim-atom gate.
    """
    checks: List[str] = []
    if atoms.quantities(segment) or atoms.dates(segment):
        checks += ["numbers", "units"]
    if atoms.modality(segment):
        checks.append("modality")
    if atoms.negation(segment):
        checks.append("negation")
    if atoms.conditions(segment):
        checks.append("conditions")
    if atoms.citations(segment) or atoms.urls(segment):
        checks.append("cross_refs")
    if _DEFINED_TERM.search(segment):
        checks.append("defined_terms")
    return checks


def _iter_segments(text: str):
    """Yield ``(char_start, char_end, segment_text)`` for each sentence/paragraph, with no
    characters dropped between segments so cumulative offsets stay exact."""
    pos = 0
    for m in _BOUNDARY.finditer(text):
        yield pos, m.start(), text[pos:m.start()]
        pos = m.end()
    if pos < len(text):
        yield pos, len(text), text[pos:]


def build_invariant_regions(doc: bytes) -> List[dict]:
    """Auto-derive manifest ``invariant_regions`` for arbitrary UTF-8 prose.

    Returns a list of ``{start_byte, end_byte, checks}`` (byte-exact, half-open) ready to
    drop straight into a ``build_ledger`` manifest. Regions are sorted by ``start_byte``.
    Raises ``LedgerBuildError`` on non-UTF-8 input.
    """
    if not doc:
        return []
    try:
        text = doc.decode("utf-8")
    except UnicodeDecodeError as err:
        raise LedgerBuildError(f"input is not valid utf-8: {err}") from err

    regions: List[dict] = []
    for cs, ce, segment in _iter_segments(text):
        # tighten the span to the sentence's non-whitespace extent (byte-exact).
        lead = len(segment) - len(segment.lstrip())
        trail = len(segment) - len(segment.rstrip())
        cs, ce = cs + lead, ce - trail
        segment = segment.strip()
        if not segment:
            continue
        checks = _checks_for(segment)
        if not checks:
            continue
        regions.append({
            "start_byte": len(text[:cs].encode("utf-8")),
            "end_byte": len(text[:ce].encode("utf-8")),
            "checks": checks,
        })
    return regions
