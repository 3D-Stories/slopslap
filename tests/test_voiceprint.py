"""#24 — one-shot manual voice sample (no learning, no persistence).

`extract_voice_features` is a PURE function over a single inline sample: it returns measure-only
diction signals (register/contraction/punctuation/directness) that the model may use to BIAS diction
among ALREADY-SAFE phrasings — it never authorizes an edit, never persists, never learns. Per the
authority order (protected > invariants+no-fabrication > genre > instruction > voiceprint > default),
these signals sit second-from-last; the keystone still holds.
"""
import pytest

from slopslap_scan.voiceprint import VoiceError, extract_voice_features


def _f(sample):
    return extract_voice_features(sample)


def test_returns_measure_only_shape():
    f = _f(b"I can't wait. We'll ship it. It's ready.")
    # measure-only: features + an explicit non-authorization declaration, never an edit/verdict
    assert f["purpose"] == "diction_bias_only"
    assert "authorizes_edit" in f and f["authorizes_edit"] is False
    for k in ("contraction_rate", "mean_sentence_len", "person_lean", "punctuation"):
        assert k in f


def test_contraction_rate_high_vs_low():
    hi = _f(b"I can't do it. We're not sure. It's fine. Don't.")
    lo = _f(b"I cannot do it. We are not sure. It is fine. Do not.")
    assert hi["contraction_rate"] > lo["contraction_rate"]
    assert lo["contraction_rate"] == 0.0


def test_person_lean_first_vs_second_vs_third():
    assert _f(b"I think we should go. I like it.")["person_lean"] == "first"
    assert _f(b"You should go. You will like it.")["person_lean"] == "second"
    assert _f(b"The system runs. It returns a value. They agree.")["person_lean"] == "third"


def test_punctuation_profile_flags_exclamation_and_dashes():
    f = _f("Wow! This is huge! Really — truly — big!".encode("utf-8"))
    assert f["punctuation"]["exclamation_rate"] > 0
    assert f["punctuation"]["em_dash_rate"] > 0


def test_mean_sentence_len_short_vs_long():
    short = _f(b"Go. Now. Do it.")
    long = _f(b"We convened the committee to deliberate at length over the matter before us today.")
    assert long["mean_sentence_len"] > short["mean_sentence_len"]


def test_empty_and_whitespace_sample_is_safe_neutral():
    f = _f(b"   \n  ")
    assert f["mean_sentence_len"] == 0.0 and f["contraction_rate"] == 0.0
    assert f["person_lean"] == "none" and f["authorizes_edit"] is False


def test_non_utf8_raises_voiceerror():
    with pytest.raises(VoiceError):
        _f(b"\xff\xfe not utf-8")


def test_accepts_str_or_bytes():
    assert _f("I can't.")["contraction_rate"] == _f(b"I can't.")["contraction_rate"]
