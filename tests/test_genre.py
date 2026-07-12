"""Genre classifier + genre-modified diagnosis mechanic (#22).

Two real parts of the issue:
(a) ``classify_genre(doc, *, declared, path)`` honoring the genre-profiles.md precedence
    (explicit declaration > file/repo context > structural markers > content inference) and the
    asymmetric-failure fallback (low/no confidence -> MOST preservation-heavy profile = spec).
(b) genre ACTUALLY constrains diagnosis: the SAME doc yields DIFFERENT diagnoses under different
    genres — spec suppresses the parallelism/repetition cadence flags (correctness infra),
    personal suppresses the voice-flattening flags (em-dashes/cadence are the point), and PRD adds
    an adjective-as-requirement candidate while never vision-policing aspirational language.
"""

import pytest

from slopslap_scan import TEXT_PROFILE
from slopslap_scan.extract import extract_text
from slopslap_scan.genre import (
    GENRE_ENUM,
    MOST_PRESERVING_GENRE,
    GenreError,
    classify_genre,
)
from slopslap_scan.metrics import GENRE_SUPPRESS, compute_all


def _metrics(text, genre=None):
    return compute_all(extract_text(text), TEXT_PROFILE, source=text, genre=genre)


# repetition-heavy: 6 "X, not Y" hits -> negative_parallelism soft_flag True under general.
_REPETITION = ". ".join(f"choose {w} thing, not other thing" for w in "abcdef") + "."
# voice-heavy: em-dash / semicolon density -> punctuation_rates soft_flag True under general.
_VOICE = "one — two; three — four; five — six; seven — eight; nine — ten."
# spec-shaped: many RFC-2119 modals.
_SPEC = ("The client MUST send a header. The server SHALL reject malformed input. "
         "A token MUST NOT be reused. Responses SHALL include a status. The field is REQUIRED.")
# PRD-shaped: distinct PRD structural markers.
_PRD = ("As a user, I want to check out quickly. Acceptance criteria: the cart persists. "
        "Non-goals: payments. Out of scope: refunds.")
# personal-voice: heavy first-person singular.
_PERSONAL = ("I keep coming back to that morning. My coffee went cold while I stared at the wall. "
             "I don't know what I expected — maybe nothing. I just sat there, and I let it happen.")


# ================= part (a): classifier =================
def test_explicit_declaration_wins_over_conflicting_structural_signal():
    # the doc is unmistakably spec-shaped, but the user declared personal -> declaration wins.
    r = classify_genre(_SPEC.encode(), declared="personal")
    assert r["genre"] == "personal"
    assert r["confidence"] == "high"


def test_declaration_beats_content_and_path():
    r = classify_genre(_PERSONAL.encode(), declared="spec", path="notes/my-diary.md")
    assert r["genre"] == "spec"
    assert r["confidence"] == "high"


def test_file_context_beats_structural_and_content():
    # a neutral doc (no usable content signal) + a PRD path -> path decides (beats fallback).
    neutral = b"This is a short note about the weather today."
    r = classify_genre(neutral, path="docs/checkout-prd.md")
    assert r["genre"] == "prd"
    assert r["confidence"] == "medium"


def test_path_beats_a_conflicting_structural_signal():
    # spec-shaped content, but a diary path -> file context (tier 2) beats structural (tier 3).
    r = classify_genre(_SPEC.encode(), path="journal/2026-07-12.md")
    assert r["genre"] == "personal"


def test_spec_shaped_doc_classifies_spec():
    r = classify_genre(_SPEC.encode())
    assert r["genre"] == "spec"


def test_prd_shaped_doc_classifies_prd():
    r = classify_genre(_PRD.encode())
    assert r["genre"] == "prd"


def test_personal_voice_doc_classifies_personal():
    r = classify_genre(_PERSONAL.encode())
    assert r["genre"] == "personal"


def test_ambiguous_doc_falls_back_to_most_preservation_heavy():
    r = classify_genre(b"asdf qwer zxcv lorem ipsum dolor sit amet.")
    assert r["genre"] == MOST_PRESERVING_GENRE == "spec"
    assert r["confidence"] == "low"


def test_empty_doc_defaults_safely():
    r = classify_genre(b"")
    assert r["genre"] == MOST_PRESERVING_GENRE
    assert r["confidence"] == "low"


def test_non_utf8_fails_loud():
    with pytest.raises(GenreError):
        classify_genre(b"\xff\xfe not utf-8")


def test_unknown_declaration_falls_through_not_crash():
    # a declared value we don't recognize must not win and must not crash — fall through.
    r = classify_genre(_SPEC.encode(), declared="haiku")
    assert r["genre"] == "spec"  # structural signal, since the bogus declaration is ignored


def test_return_shape():
    r = classify_genre(_SPEC.encode())
    assert set(r) == {"genre", "confidence", "reason"}
    assert r["genre"] in GENRE_ENUM
    assert r["confidence"] in ("high", "medium", "low")
    assert isinstance(r["reason"], str) and r["reason"]


# ================= part (b): the mechanic =================
def test_general_is_byte_identical_to_no_genre():
    units = extract_text(_REPETITION)
    base = compute_all(units, TEXT_PROFILE, source=_REPETITION)
    assert compute_all(units, TEXT_PROFILE, source=_REPETITION, genre="general") == base
    assert compute_all(units, TEXT_PROFILE, source=_REPETITION, genre=None) == base
    # general never adds the PRD-only metric or a suppression marker.
    assert "adjective_requirements" not in base
    assert all("suppressed_by_genre" not in res for res in base.values())


def test_spec_suppresses_repetition_flag_that_general_raises():
    # THE PROOF part (b) is real: the same passage flags under general but NOT under spec.
    assert _metrics(_REPETITION)["negative_parallelism"]["soft_flag"] is True
    spec = _metrics(_REPETITION, genre="spec")["negative_parallelism"]
    assert spec["soft_flag"] is False
    assert spec["locations"] == []
    assert spec["suppressed_by_genre"] == "spec"
    # count is still MEASURED honestly (suppression is about candidacy, not lying about the count).
    assert spec["count"] >= 5


def test_spec_suppresses_only_cadence_repetition_not_other_flags():
    text = _REPETITION + " However, this is fine. Furthermore, it scales."
    assert _metrics(text)["transition_clusters"]["soft_flag"] is True
    spec = _metrics(text, genre="spec")
    assert spec["negative_parallelism"]["soft_flag"] is False  # suppressed
    assert spec["transition_clusters"]["soft_flag"] is True    # untouched (not a repetition flag)


def test_personal_preserves_voice_punctuation_that_general_flags():
    assert _metrics(_VOICE)["punctuation_rates"]["soft_flag"] is True
    personal = _metrics(_VOICE, genre="personal")["punctuation_rates"]
    assert personal["soft_flag"] is False
    assert personal["suppressed_by_genre"] == "personal"


def test_personal_also_suppresses_cadence_repetition():
    assert _metrics(_REPETITION)["negative_parallelism"]["soft_flag"] is True
    assert _metrics(_REPETITION, genre="personal")["negative_parallelism"]["soft_flag"] is False


def test_prd_adds_adjective_requirement_candidate():
    text = "The system must be fast. The dashboard should be intuitive. Onboarding must be simple."
    # general emits no such metric at all (default behavior untouched).
    assert "adjective_requirements" not in _metrics(text)
    prd = _metrics(text, genre="prd")["adjective_requirements"]
    assert prd["count"] == 3
    adjectives = {loc["adjective"] for loc in prd["locations"]}
    assert adjectives == {"fast", "intuitive", "simple"}
    assert prd["soft_flag"] is True


def test_prd_does_not_vision_police_aspirational_language():
    # aspiration without a normative modal is NOT an adjective-as-requirement -> not flagged.
    text = "Our long-term vision is to delight every user and build a beautiful, powerful product."
    prd = _metrics(text, genre="prd")["adjective_requirements"]
    assert prd["count"] == 0
    assert prd["soft_flag"] is False


def test_unknown_genre_is_a_caller_error():
    with pytest.raises(ValueError):
        _metrics(_REPETITION, genre="bogus")


def test_genre_enum_and_suppress_table_do_not_drift():
    assert set(GENRE_ENUM) == set(GENRE_SUPPRESS)


# ================= part (b): reaches verify via authorized ranges =================
def test_genre_constrains_authorized_ranges_end_to_end():
    from slopslap_scan.diagnoses import authorized_ranges_from_diagnoses

    # a single repetition-heavy paragraph: diagnosed ONLY by cadence-repetition flags.
    doc = (". ".join(f"pick {w} one, not other" for w in "abcdef") + ".").encode("utf-8")
    general = authorized_ranges_from_diagnoses(doc, "text")
    assert general != [], "general authorizes the diagnosed cadence passage"
    # under spec the cadence flags are suppressed -> the passage is no longer a candidate.
    assert authorized_ranges_from_diagnoses(doc, "text", genre="spec") == []


def test_prd_adds_an_authorized_range_general_does_not():
    from slopslap_scan.diagnoses import authorized_ranges_from_diagnoses

    doc = b"The dashboard must be fast and the flow should be intuitive."
    assert authorized_ranges_from_diagnoses(doc, "text") == []
    assert authorized_ranges_from_diagnoses(doc, "text", genre="prd") != []
