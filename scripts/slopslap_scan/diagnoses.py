"""Passage-local authorized ranges from live scan diagnoses (#20).

``authorized_ranges_from_diagnoses(doc)`` scans arbitrary UTF-8 prose and returns the byte
spans of the DIAGNOSED passages, so feeding them to
``slopslap_verification.ledger.verify(..., authorized_ranges=<result>)`` makes
``gates.edit_locality`` enforce passage-local editing DETERMINISTICALLY on a live doc. Until
now ``edit_locality`` only fired when a fixture hand-declared ``editable_ranges``; on a live
doc there are none, so ``authorized_ranges=None`` and locality was merely prompt-guided (the
``locality_unverified`` ASK, ledger.py). This module derives those ranges from the emitted
diagnoses instead.

DIAGNOSED PASSAGE — the definition: an eligible ``extract.Unit`` (paragraph / heading /
list_item — the granularity the scanner extracts) whose 1-indexed inclusive line range
OVERLAPS some scanner metric location's line range. Every ``metrics`` ``locations`` entry
carrying a ``line_start`` counts, regardless of ``soft_flag`` / confidence tier: the scanner
is candidate-selection-only and each emitted location IS a candidate passage a live rewrite
may address. A location with only ``line_start`` (negative_parallelism, rule_of_three,
transition_clusters, vague_attribution, stock_lexical_clusters) is treated as a single-line
range; one with ``line_start`` + ``line_end`` (paragraph_sentence_count_runs, bold_label,
repeated_openers) authorizes every eligible Unit it spans.

Three metrics are DOC-LEVEL and carry NO per-passage location, so they never contribute a
range (and we never fabricate one): ``sentence_length_distribution``,
``sentence_length_dispersion``, ``punctuation_rates``. Punctuation may ``soft_flag`` the whole
document, but with no per-passage location it cannot be localized — inventing a whole-doc
range would defeat the point of locality.

``[]`` IS OVERLOADED. It means "no passage-local authorization", which arises from EITHER a
genuinely clean doc OR a doc flagged ONLY by the doc-level metrics above. In both cases verify
REJECTs every edit (an empty authorized set = leave the doc alone — the ``control_abstention``
discipline), whereas ``authorized_ranges=None`` remains the undecidable ASK. CONSEQUENCE for the
live orchestrator (#27): a doc-level-only-flagged doc (e.g. pervasive em-dash / cadence slop with
no localizable passage) has NO passage-local rewrite path through this deriver; whether such
whole-doc slop warrants a separate doc-wide rewrite lane is that seam's decision, not this
deriver's. This deriver fails closed (no ranges → no edits) by design.

Byte offsets are EXACT (UTF-8, via a byte-offset-per-line table — the ``slopslap_scan.protected``
pattern; never char offsets). Input MUST be valid UTF-8; non-UTF-8 raises ``DiagnosisError``
rather than silently shifting every re-encoded offset (same fail-loud discipline as
``protected.ProtectedSpanError`` / ``autoledger.LedgerBuildError``). The Markdown path requires
the pinned CommonMark parser (version-checked in-process, exactly as ``slopslap_scan.protected``;
the strict vendor-ORIGIN enforcement stays in ``scan_prose.py`` / ``capability.gate`` where the
CLI controls a fresh process's ``sys.path``); an unavailable/mismatched parser raises
``DiagnosisError`` rather than under-diagnosing.
"""

from __future__ import annotations

from typing import List

from . import EXTRACTION_PROFILE, TEXT_PROFILE
from . import extract as ext
from . import metrics as met
from .capability import PINNED

VALID_FORMATS = ("markdown", "text")


class DiagnosisError(RuntimeError):
    """Cannot derive byte-exact ranges: non-UTF-8 input, an unknown format, or (markdown) an
    unavailable/version-mismatched pinned CommonMark parser. Failing loud beats silently
    shifted/under-diagnosed offsets."""


def _markdown_it_cls():
    """The pinned MarkdownIt class (version-checked, in-process; mirrors protected._markdown_it_cls)."""
    try:
        import markdown_it  # noqa: PLC0415
    except Exception as err:  # noqa: BLE001
        raise DiagnosisError(f"markdown-it-py not importable: {err}") from err
    version = getattr(markdown_it, "__version__", None)
    if version != PINNED["markdown_it"]:
        raise DiagnosisError(
            f"markdown-it-py version {version!r} != pinned {PINNED['markdown_it']!r}"
        )
    return markdown_it.MarkdownIt


def _line_starts(raw: bytes) -> List[int]:
    """Byte offset of the start of each source line, plus a sentinel == len(raw)
    (the slopslap_scan.protected pattern)."""
    starts = [0]
    for i, b in enumerate(raw):
        if b == 0x0A:  # '\n'
            starts.append(i + 1)
    starts.append(len(raw))
    return starts


def _diagnosed_line_ranges(metrics: dict) -> List[tuple]:
    """(line_start, line_end) for every per-passage metric location (line_end defaults to
    line_start). Doc-level metrics have empty ``locations`` and contribute nothing."""
    ranges: List[tuple] = []
    for res in metrics.values():
        for loc in res.get("locations") or []:
            ls = loc.get("line_start")
            if ls is None:
                continue
            ranges.append((ls, loc.get("line_end", ls)))
    return ranges


def authorized_ranges_from_diagnoses(doc: bytes, fmt: str = "markdown") -> List[dict]:
    """Return byte-exact ``[{start_byte, end_byte}]`` for the diagnosed passages of ``doc``.

    ``fmt`` is ``"markdown"`` (default) or ``"text"`` — matching the scanner's two pipelines;
    there is no content sniffing (scanner keystone rule). Ranges are sorted by ``start_byte``
    and merged so they are pairwise disjoint, ready to drop straight into
    ``verify(..., authorized_ranges=<result>)``.

    Raises ``DiagnosisError`` on an unknown format, non-UTF-8 input, or (markdown) an
    unavailable pinned parser.
    """
    if not doc:
        return []
    if fmt not in VALID_FORMATS:
        raise DiagnosisError(f"unknown format {fmt!r}; expected one of {VALID_FORMATS}")
    try:
        text = doc.decode("utf-8")
    except UnicodeDecodeError as err:
        raise DiagnosisError(f"input is not valid utf-8: {err}") from err

    if fmt == "markdown":
        units = ext.extract_markdown(text, _markdown_it_cls())
        metrics = met.compute_all(units, EXTRACTION_PROFILE, source=text)
    else:
        units = ext.extract_text(text)
        metrics = met.compute_all(units, TEXT_PROFILE, source=text)

    diag = _diagnosed_line_ranges(metrics)
    if not diag:
        return []

    starts = _line_starts(doc)
    last = len(starts) - 1  # index of the len(raw) sentinel; bounds any line_end
    spans: List[tuple] = []
    for u in units:
        if any(not (u.line_end < ls or u.line_start > le) for ls, le in diag):
            spans.append((starts[u.line_start - 1], starts[min(u.line_end, last)]))

    # merge overlapping / exactly-adjacent spans into a clean, disjoint, sorted set.
    spans.sort()
    merged: List[list] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [{"start_byte": s, "end_byte": e} for s, e in merged]
