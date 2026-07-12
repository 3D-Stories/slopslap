"""Deterministic atom extractors for the preservation gates.

All extractors operate on decoded text (utf-8) and return either multisets (Counter) or
sorted lists, so region-scoped comparisons are order-insensitive but count-sensitive
(a deleted value can't be masked by inserting the same token elsewhere).

Reliability tiers (peer + WF5 review):
  HARD  — numbers, dates, urls/endpoints, citation markers, thresholds/comparators:
          low false-positive; a new one anywhere is a hard-gate failure.
  ADVISORY — proper-noun candidates: capitalization makes these noisy, so they are
          reported but do NOT by themselves fail the mechanical gate (the semantic
          residue is a required judge dimension; see design R2).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

# ---- numbers / quantities -------------------------------------------------
# optional comparator, optional sign, integer/decimal with optional thousands
# separators, optional percent/unit-ish suffix captured separately.
_NUM_RE = re.compile(
    r"(?P<cmp>[<>]=?|≤|≥|±)?\s*"
    r"(?P<sign>[-−+])?"
    r"(?P<val>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<pct>%)?"
)

# ISO, slashed, and month-name dates
_DATE_RE = re.compile(
    r"\b("
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:,?\s*\d{4})?"
    r")\b"
)

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\)\]]+", re.IGNORECASE)

# citation markers: [1], [12], (Smith 2020), [Smith2020]
_CITATION_RE = re.compile(r"\[\d{1,3}\]|\((?:[A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?,?\s*)\d{4}[a-z]?\)")

# comparator/threshold words + symbols (order-independent presence multiset)
_THRESHOLD_RE = re.compile(
    r"[<>]=?|≤|≥|\b(?:at\s+least|at\s+most|no\s+more\s+than|no\s+fewer\s+than|"
    r"greater\s+than|less\s+than|minimum|maximum|up\s+to)\b",
    re.IGNORECASE,
)

# normative modal lexicon — pinned, case-insensitive, phrase-aware. Longest first so
# "must not" wins over "must".
_MODALS = [
    "must not",
    "shall not",
    "should not",
    "may not",
    "will not",
    "cannot",
    "is required to",
    "are required to",
    "required to",
    "must",
    "shall",
    "should",
    "may",
    "will",
    "can",
    "might",
    "could",
    "required",
]
_MODAL_RE = re.compile(
    r"\b(" + "|".join(m.replace(" ", r"\s+") for m in _MODALS) + r")\b",
    re.IGNORECASE,
)

_NEGATION_RE = re.compile(
    r"\b(not|no|never|none|neither|nor|without|cannot)\b|n['’]t\b", re.IGNORECASE
)

_CONDITION_RE = re.compile(
    r"\b(if|when|whenever|unless|provided\s+that|in\s+case|as\s+long\s+as|"
    r"only\s+if|where|assuming)\b",
    re.IGNORECASE,
)

# TitleCase multi-word runs OR a lone Capitalized token that is not sentence-initial.
_PROPER_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|[A-Z][A-Za-z]{2,})\b")


def _norm_num(m: re.Match) -> str:
    cmp_ = (m.group("cmp") or "").replace("≤", "<=").replace("≥", ">=")
    sign = (m.group("sign") or "").replace("−", "-")
    val = m.group("val").replace(",", "")
    pct = m.group("pct") or ""
    return f"{cmp_}{sign}{val}{pct}"


def numbers(text: str) -> Counter:
    return Counter(_norm_num(m) for m in _NUM_RE.finditer(text))


def dates(text: str) -> Counter:
    return Counter(re.sub(r"\s+", " ", m.group(0).strip()) for m in _DATE_RE.finditer(text))


def urls(text: str) -> Counter:
    return Counter(m.group(0).rstrip(".,;:") for m in _URL_RE.finditer(text))


def citations(text: str) -> Counter:
    return Counter(re.sub(r"\s+", " ", m.group(0)) for m in _CITATION_RE.finditer(text))


def thresholds(text: str) -> Counter:
    return Counter(m.group(0).lower().strip() for m in _THRESHOLD_RE.finditer(text))


def modality(text: str) -> Counter:
    return Counter(re.sub(r"\s+", " ", m.group(0).lower()) for m in _MODAL_RE.finditer(text))


def negation(text: str) -> Counter:
    return Counter(m.group(0).lower() for m in _NEGATION_RE.finditer(text))


def conditions(text: str) -> Counter:
    return Counter(re.sub(r"\s+", " ", m.group(0).lower()) for m in _CONDITION_RE.finditer(text))


def proper_nouns(text: str) -> Counter:
    return Counter(m.group(0) for m in _PROPER_RE.finditer(text))


# check-name -> extractor, used for region-scoped preservation.
CHECK_EXTRACTORS = {
    "numbers": numbers,
    "units": numbers,  # units ride along with the numeric token in this MVP
    "modality": modality,
    "negation": negation,
    "conditions": conditions,
}

# HARD claim-atom categories (low false-positive). proper_nouns intentionally excluded
# from the hard set (advisory-only).
HARD_CLAIM_EXTRACTORS = {
    "number": numbers,
    "date": dates,
    "url": urls,
    "citation": citations,
    "threshold": thresholds,
}


def hard_claim_atoms(text: str) -> Dict[str, Counter]:
    return {name: fn(text) for name, fn in HARD_CLAIM_EXTRACTORS.items()}


def new_claim_atoms(original: str, revision: str, allowed: List[str] | None = None) -> Dict[str, List[str]]:
    """Return per-category atoms present in ``revision`` but absent from ``original``.

    Distinct-atom set difference (not multiset): re-using an existing atom is fine; the
    gate targets INVENTED atoms. ``allowed`` exempts fixture-declared atoms.
    """
    allowed_set = set(allowed or [])
    out: Dict[str, List[str]] = {}
    orig = hard_claim_atoms(original)
    rev = hard_claim_atoms(revision)
    for cat in HARD_CLAIM_EXTRACTORS:
        introduced = sorted(
            a for a in rev[cat] if a not in orig[cat] and a not in allowed_set
        )
        if introduced:
            out[cat] = introduced
    return out
