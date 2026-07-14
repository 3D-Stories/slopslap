"""Lightweight per-document genre classifier (#22).

``classify_genre(doc, *, declared=None, path=None) -> {"genre", "confidence", "reason"}``.

Precedence (``references/genre-profiles.md`` §Classification precedence):
  explicit declaration > file/repo context > structural markers > content inference.
On NO usable signal (§Asymmetric-failure rule: "on low genre confidence, use the MOST
preservation-heavy applicable profile") it falls back to ``spec`` — the profile that preserves
the widest edit-constraining set (normative modals, numbers, parallelism/repetition,
enumerations), so an unsure call errs toward preserving MORE.

Genre never decides prose is "bad" and never authorizes an edit (keystone rule); since keystone v2
(issue #59) it only SETS each finding's advisory strip|keep recommendation (see
``metrics.recommend``) — it no longer zeroes any metric's locations.

Non-UTF-8 input fails loud (``GenreError``) — the same discipline as ``slopslap_scan.protected`` /
``diagnoses`` / ``autoledger`` (a classifier that silently swallows garbage bytes hides a real
encoding bug); an explicit declaration overrides the CLASSIFICATION, never the encoding check.
Empty / signal-less input defaults safely to the fallback profile.

ponytail: first-person density and modal density are treated as STRUCTURAL markers (surface
signals), not a separate "content inference" tier — the scanner has no reliable topic-level
content signal distinct from those, so a weak/ambiguous doc goes straight to the asymmetric
fallback rather than to a fabricated low-confidence guess.
"""

from __future__ import annotations

import re

from .extract import words


class GenreError(RuntimeError):
    """Input is not valid UTF-8 (or not bytes). Fail loud rather than classify garbage."""


# the profiles this classifier + the scanner mechanic distinguish. genre-profiles.md also names
# technical-doc / legal / marketing; those carry NO distinct scanner mechanic yet, so emitting
# them would be an inert label — the classifier does not. ``general`` == general-prose.
GENRE_ENUM = ("general", "spec", "prd", "personal")

# §Asymmetric-failure: unsure -> preserve MORE. spec preserves the widest edit-constraining set,
# so it is the most preservation-heavy of the profiles the mechanic distinguishes.
MOST_PRESERVING_GENRE = "spec"

# accepted explicit-declaration spellings -> canonical genre. An unrecognized declaration is
# ignored (falls through), never a crash and never a win.
_DECL_ALIASES = {
    "general": "general", "general-prose": "general", "prose": "general", "essay": "general",
    "spec": "spec", "specification": "spec", "rfc": "spec", "standard": "spec",
    "prd": "prd", "product-requirements": "prd", "product-requirements-doc": "prd",
    "personal": "personal", "personal-prose": "personal", "journal": "personal", "diary": "personal",
}

# RFC-2119 STRONG normative modals only (must/shall/required). "should"/"may" are too common in
# ordinary prose to count toward a spec signal without inflating false positives.
_MODAL_RE = re.compile(r"\b(?:must|shall|required)\b", re.IGNORECASE)

# PRD structural markers — specific multi-word phrases only (never a bare common word like "as a").
_PRD_MARKERS = (
    "user story", "user stories", "acceptance criteria", "non-goals", "non goals",
    "out of scope", "success metric", "product requirements", "as a user", "personas",
    "problem statement", "target users", "user persona",
)

# first-person-singular voice tokens. ``words()`` keeps internal apostrophes as one token, so
# "I've" -> "i've" after lowering.
_FIRST_PERSON = {"i", "i'm", "i've", "i'd", "i'll", "me", "my", "mine", "myself"}
_FP_MIN_COUNT = 3
_FP_MIN_RATIO = 0.05


def _normalize_declared(declared):
    if not declared:
        return None
    return _DECL_ALIASES.get(str(declared).strip().lower())


# whole-token path signals per genre. Matched against path COMPONENTS (split on separators),
# never as a raw substring — else "proSPECtus" / "reSPECt" / "aSPECt" / "SPECial" would all
# masquerade as spec. Plural/expanded forms are enumerated so "specification"/"requirements"
# still hit. Repo context: a ``journal/`` or ``docs/`` DIRECTORY component is a valid signal.
_PATH_SEP = re.compile(r"[/\\._\-\s]+")
_PATH_TOKENS = (
    ("prd", ("prd", "prds")),
    ("spec", ("spec", "specs", "specification", "specifications", "rfc", "rfcs",
              "requirement", "requirements")),
    ("personal", ("journal", "journals", "diary", "diaries")),
    ("general", ("readme", "readmes", "changelog", "changelogs", "guide", "guides",
                 "guideline", "guidelines")),
)


def _from_path(path):
    if not path:
        return None
    toks = {t for t in _PATH_SEP.split(str(path).lower()) if t}
    for genre, keywords in _PATH_TOKENS:  # precedence: prd > spec > personal > general
        if toks & set(keywords):
            return genre
    return None


def _from_structure(text):
    """Structural markers (medium confidence). Order = reliability: first-person density is a
    near-certain personal tell (specs/PRDs do not use it heavily), then PRD phrase markers, then
    strong-modal density for spec. Returns (genre, reason) or (None, None)."""
    # normalize the curly right-single-quote to a straight apostrophe so "I’ve" matches the
    # straight-apostrophe first-person set (words() preserves curly quotes).
    toks = [t.lower().replace("’", "'") for t in words(text)]
    n = len(toks)
    if n:
        fp = sum(1 for t in toks if t in _FIRST_PERSON)
        if fp >= _FP_MIN_COUNT and fp / n >= _FP_MIN_RATIO:
            return "personal", f"first-person density {fp}/{n}"
    low = text.lower()
    prd_hits = sum(1 for m in _PRD_MARKERS if m in low)
    if prd_hits >= 2:
        return "prd", f"{prd_hits} PRD structural markers"
    modal_hits = len(_MODAL_RE.findall(text))
    if modal_hits >= 3:
        return "spec", f"{modal_hits} normative modals"
    return None, None


def classify_genre(doc, *, declared=None, path=None):
    """Classify ``doc`` (bytes) into one of ``GENRE_ENUM`` per the precedence above.

    ``declared`` is an explicit user genre declaration (highest precedence). ``path`` is the
    document's file/repo path (second). Raises ``GenreError`` on non-UTF-8 / non-bytes input.
    """
    # input validity first (fail-loud house discipline).
    try:
        text = doc.decode("utf-8")
    except AttributeError as err:
        raise GenreError(f"doc must be bytes: {err}") from err
    except UnicodeDecodeError as err:
        raise GenreError(f"input is not valid utf-8: {err}") from err

    declared_genre = _normalize_declared(declared)
    if declared_genre:
        return {"genre": declared_genre, "confidence": "high",
                "reason": f"explicit declaration ({declared!r})"}

    path_genre = _from_path(path)
    if path_genre:
        return {"genre": path_genre, "confidence": "medium",
                "reason": f"file/repo context ({path!r})"}

    struct_genre, struct_reason = _from_structure(text)
    if struct_genre:
        return {"genre": struct_genre, "confidence": "medium",
                "reason": f"structural markers: {struct_reason}"}

    return {"genre": MOST_PRESERVING_GENRE, "confidence": "low",
            "reason": "no usable genre signal; asymmetric-failure fallback to the "
                      "most-preservation-heavy profile (spec)"}
