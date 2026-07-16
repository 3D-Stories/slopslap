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

from pathlib import Path

import pytest

from slopslap_scan import TEXT_PROFILE
from slopslap_scan.extract import extract_text
from slopslap_scan.genre import (
    GENRE_ENUM,
    MOST_PRESERVING_GENRE,
    GenreError,
    classify_genre,
)
from slopslap_scan.metrics import ALL_METRICS, METRIC_CLASS, compute_all, recommend


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

# the UAT candidate set (#98) — real docs, classified with real bytes + real path, exactly as
# scripts/slopslap_assemble/assemble.py threads them into classify_genre. The candidates are
# deliberately UNTRACKED working files (the repo is public; several are internal briefings), so
# these tests skip visibly on a checkout without them — the always-on synthetic fixture below
# carries the portable regression guard.
_CANDIDATES = Path(__file__).resolve().parents[1] / "docs" / "uat" / "candidate-test-files"
needs_candidates = pytest.mark.skipif(
    not _CANDIDATES.is_dir(),
    reason="UAT candidate set not present (untracked working files; see #98)")


def _classify_candidate(name):
    p = _CANDIDATES / name
    return classify_genre(p.read_bytes(), path=str(p))


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


@needs_candidates
def test_marketing_heavy_candidates_classify_marketing_and_strip_cadence():
    # #98 AC1: both marketing-heavy UAT candidates land on a strip-cadence profile — the new
    # ``marketing`` genre — so their corporate-cadence slop recommends strip, not keep.
    for name in ("marketing-heavy--chorestory-briefing.md",
                 "marketing-heavy--investor-briefing.md"):
        r = _classify_candidate(name)
        assert r["genre"] == "marketing", f"{name}: {r}"
        assert r["confidence"] == "medium"
        for metric in ("rule_of_three", "repeated_openers", "negative_parallelism",
                       "transition_clusters"):
            assert recommend(r["genre"], metric) == "strip", f"{name}/{metric}"


@needs_candidates
def test_uat_candidate_genre_map_no_regression():
    # #98 AC2: the other 9 candidates still land where the v0.14.0 UAT recorded them
    # (docs/reviews/2026-07-16-uat-v0.14.0-results.md, candidate audit map) — classified the same
    # way assemble.py does: real bytes + real path.
    expected = {
        "general-clean--arc-README.md": "general",
        "general-clean--presentation-builder-retro.md": "spec",
        "general-clean-voice--kukakuka-README.md": "general",
        "marketing-clean--saystory-README.md": "general",
        "prd-large--chorestory-admin-user-creation.md": "prd",
        "spec--chorestory-tenant-isolation.md": "spec",
        "spec-DENSEST--provenance-contract.md": "spec",
        "spec-clean--rawgentic-wal-guide.md": "spec",
        "spec-dense--sentinel-forced-command-ssh.md": "spec",
    }
    for name, genre in expected.items():
        assert _classify_candidate(name)["genre"] == genre, name


def test_marketing_shaped_doc_classifies_marketing():
    # #98: always-on synthetic guard (the candidate-file tests above skip off-machine). GTM-pitch
    # prose: dense, distinct marketing lexicon; no first-person density, no PRD markers, no modals.
    doc = (
        "The brand is positioned to capture an underserved market. Competitors ship flat, "
        "utility-first products; our differentiation is a cooperative model competitors cannot "
        "copy. Market analysis shows retention drives revenue, and investor interest follows "
        "adoption. Pricing lands mid-segment, with monetization layered on engagement. The "
        "competitive moat compounds: every customer cohort raises switching costs, and the "
        "flywheel turns brand awareness into adoption. Investors get a defensible position in "
        "a growing market with best-in-class retention."
    ).encode()
    r = classify_genre(doc)
    assert r["genre"] == "marketing"
    assert r["confidence"] == "medium"
    assert "marketing lexicon density" in r["reason"]


def test_declared_marketing_wins():
    # #98 AC4: "marketing" is a recognized explicit declaration.
    r = classify_genre(_SPEC.encode(), declared="marketing")
    assert r["genre"] == "marketing"
    assert r["confidence"] == "high"


def test_marketing_lexicon_below_threshold_falls_back_to_spec():
    # #98 AC3: a short marketing-flavored note under the count floor is treated as ambiguous —
    # asymmetric-failure still lands on the most-preserving profile, never on marketing.
    r = classify_genre(b"Our brand is positioned to win the market against competitors.")
    assert r["genre"] == MOST_PRESERVING_GENRE
    assert r["confidence"] == "low"


def test_single_repeated_lexeme_does_not_masquerade_as_marketing():
    # #98 AC3: the distinct-lexeme floor — a data-retention doc repeating one lexicon word passes
    # the count and ratio gates but must NOT flip to marketing (that would strip a spec-like doc's
    # cadence: the over-strip direction the asymmetric rule guards against).
    doc = ("Retention applies to logs. Retention runs nightly. Retention windows vary. "
           "Retention holds for audits. Retention excludes backups. Retention is tiered. "
           "Retention ends on delete. Retention resumes on restore.")
    r = classify_genre(doc.encode())
    assert r["genre"] == MOST_PRESERVING_GENRE
    assert r["confidence"] == "low"


def test_stronger_structural_signal_beats_marketing_lexicon():
    # a spec that talks about markets: normative modals (a stronger tier) win over the lexicon.
    doc = (_SPEC + " The market feed MUST list competitors, pricing, segments, revenue, "
           "brand positioning, customer adoption, and investor retention data.").encode()
    assert classify_genre(doc)["genre"] == "spec"


def test_marketing_genre_accepted_by_scanner():
    # #98 AC4: the scanner gate (_SCANNER_GENRES) accepts what the classifier now emits, and the
    # recommendation strips cadence (empty keep-set, like general).
    m = _metrics(_REPETITION, genre="marketing")
    assert m["negative_parallelism"]["soft_flag"] is True   # detection universal, never zeroed
    assert recommend("marketing", "negative_parallelism") == "strip"
    assert recommend("marketing", "punctuation_rates") == "strip"


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


def test_spec_keeps_repetition_flag_that_general_strips():
    # keystone v2 (#59): detection is UNIVERSAL — the same passage flags under BOTH genres and
    # genre NEVER zeroes a metric's locations. Suppression now lives ONLY in the recommendation.
    gen = _metrics(_REPETITION)["negative_parallelism"]
    spec = _metrics(_REPETITION, genre="spec")["negative_parallelism"]
    assert gen["soft_flag"] is True
    assert spec["soft_flag"] is True                 # measured identically; not zeroed
    assert spec["locations"] == gen["locations"]     # byte-identical — genre never empties locations
    assert "suppressed_by_genre" not in spec         # the old zeroing marker is gone
    assert spec["count"] >= 5                          # count still measured honestly
    # the whole difference is the advisory recommendation: spec KEEPS cadence, general STRIPS it.
    assert recommend("spec", "negative_parallelism") == "keep"
    assert recommend("general", "negative_parallelism") == "strip"


def test_spec_keeps_only_cadence_not_other_flags():
    text = _REPETITION + " However, this is fine. Furthermore, it scales."
    spec = _metrics(text, genre="spec")
    # metrics are measured identically to general (no zeroing); genre acts in the recommendation.
    assert spec["negative_parallelism"]["soft_flag"] is True
    assert spec["transition_clusters"]["soft_flag"] is True
    assert recommend("spec", "negative_parallelism") == "keep"    # correctness cadence kept in spec
    assert recommend("spec", "transition_clusters") == "strip"    # non-cadence fluff still stripped


def test_personal_keeps_voice_punctuation_that_general_strips():
    gen = _metrics(_VOICE)["punctuation_rates"]
    personal = _metrics(_VOICE, genre="personal")["punctuation_rates"]
    assert gen["soft_flag"] is True
    assert personal["soft_flag"] is True             # measured; not zeroed
    assert "suppressed_by_genre" not in personal
    assert recommend("personal", "punctuation_rates") == "keep"
    assert recommend("general", "punctuation_rates") == "strip"


def test_personal_also_keeps_cadence_repetition():
    assert _metrics(_REPETITION, genre="personal")["negative_parallelism"]["soft_flag"] is True
    assert recommend("personal", "negative_parallelism") == "keep"


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


def test_every_metric_is_classified_no_drift():
    # #59 Option C: the recommendation table is keyed by metric CLASS, so EVERY metric the scanner
    # can emit must have a class — a new metric added without one would silently fall to the
    # asymmetric-failure default (keep) instead of a deliberate polarity. Guard forces classification.
    names = {name for name, _ in ALL_METRICS}
    names.add("adjective_requirements")  # prd-only, added dynamically by _apply_genre
    missing = names - set(METRIC_CLASS)
    assert not missing, f"metrics missing a METRIC_CLASS entry: {sorted(missing)}"


def test_recommend_reproduces_prior_suppress_keepsets_no_regression():
    # zero-regression pin (D3): recommend() must KEEP exactly what the old GENRE_SUPPRESS kept for
    # each classifier-emittable genre, and STRIP everything else. The polarity flip changes the
    # MECHANISM (zeroing -> advisory recommendation), never which passages a genre treats as candidates.
    old_keep = {
        "general": (),
        "spec": ("negative_parallelism", "rule_of_three", "repeated_openers"),
        "personal": ("negative_parallelism", "rule_of_three", "repeated_openers", "punctuation_rates"),
        "prd": (),
        # marketing is emitted since #98; it never had a suppress set — strip everything.
        "marketing": (),
    }
    probe = ["negative_parallelism", "rule_of_three", "repeated_openers", "punctuation_rates",
             "transition_clusters", "vague_attribution", "stock_lexical_clusters", "bold_label_density"]
    for genre in GENRE_ENUM:
        for m in probe:
            expected = "keep" if m in old_keep[genre] else "strip"
            assert recommend(genre, m) == expected, f"{genre}/{m}: got {recommend(genre, m)}, want {expected}"


def test_recommend_genre_none_matches_general():
    # None threads as "general" everywhere in the scanner; recommend must agree.
    for m in ("negative_parallelism", "transition_clusters"):
        assert recommend(None, m) == recommend("general", m) == "strip"


def test_recommend_unknown_genre_is_a_caller_error():
    with pytest.raises(ValueError):
        recommend("bogus", "negative_parallelism")


def test_recommend_unclassified_metric_preserves():
    # asymmetric-failure: an unknown/new metric preserves (keep) until it is deliberately classified.
    assert recommend("general", "some_future_metric_not_yet_classified") == "keep"


def test_scanner_classifier_schema_genre_sets_agree():
    # the scanner (_apply_genre) accepts EXACTLY what the classifier emits — else a doc classified as
    # a genre the scanner rejects would raise ValueError uncaught -> a hard crash on a live doc.
    from slopslap_scan.metrics import _GENRE_KEEP_CLASSES, _SCANNER_GENRES
    from eval.loader import VALID_GENRES
    assert set(GENRE_ENUM) == set(_SCANNER_GENRES)
    # the recommendation table is keyed over the feedback schema's genre enum (forward-compat rows).
    assert set(_GENRE_KEEP_CLASSES) == set(VALID_GENRES)


# ================= part (b): reaches verify via authorized ranges =================
def test_genre_constrains_authorized_ranges_end_to_end():
    from slopslap_scan.diagnoses import authorized_ranges_from_diagnoses

    # a single repetition-heavy paragraph: diagnosed ONLY by cadence-repetition flags.
    doc = (". ".join(f"pick {w} one, not other" for w in "abcdef") + ".").encode("utf-8")
    general = authorized_ranges_from_diagnoses(doc, "text")
    assert general != [], "general recommends strip for the cadence passage -> it enters editable ranges"
    # under spec the cadence flags are KEPT (recommendation), never zeroed -> the passage is not a
    # strip candidate, so it is excluded from the authorized (editable) ranges. Genre never authorizes.
    assert authorized_ranges_from_diagnoses(doc, "text", genre="spec") == []


def test_prd_adds_an_authorized_range_general_does_not():
    from slopslap_scan.diagnoses import authorized_ranges_from_diagnoses

    doc = b"The dashboard must be fast and the flow should be intuitive."
    assert authorized_ranges_from_diagnoses(doc, "text") == []
    assert authorized_ranges_from_diagnoses(doc, "text", genre="prd") != []


def test_path_middle_substrings_do_not_masquerade():
    # review fix: match whole path COMPONENTS, not raw substrings — 'proSPECtus'/'reSPECt'/
    # 'aSPECt'/'SPECial' must NOT be read as spec; legitimate whole-token signals still do.
    from slopslap_scan.genre import _from_path
    assert _from_path("notes/prospectus.md") is None
    assert _from_path("x/respect.md") is None
    assert _from_path("docs/aspect-ratios.md") is None
    assert _from_path("reports/special-report.md") is None
    assert _from_path("docs/api-spec.md") == "spec"
    assert _from_path("rfcs/2119.md") == "spec"
    assert _from_path("product/requirements.md") == "spec"
    assert _from_path("me/journal/2026.md") == "personal"
    assert _from_path("epics/prd-v2.md") == "prd"


def test_curly_apostrophe_first_person_classifies_personal():
    # review fix: curly right-single-quote normalized to straight, so first-person contractions
    # are counted. This doc's ONLY first-person signal is curly contractions (no bare i/my/me).
    doc = "I’ve seen much. I’m here now. I’d go anywhere. I’ll try hard.".encode("utf-8")
    assert classify_genre(doc)["genre"] == "personal"
