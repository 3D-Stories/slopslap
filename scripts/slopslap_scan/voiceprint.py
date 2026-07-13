"""One-shot manual voice sample — measure-only diction signals (#24).

`extract_voice_features(sample)` is a PURE function over a SINGLE inline sample the user pastes with a
suggest request. It returns diction signals (register / contraction rate / punctuation / directness)
the model MAY use to BIAS its choice among ALREADY-SAFE phrasings — it NEVER authorizes an edit,
never widens an edit boundary, never persists, and never learns (that is the deferred v2 hook). Per
the authority order (protected > invariants + no-fabrication > genre > current instruction >
voiceprint > default), these signals sit second-from-last: the keystone holds unchanged.

Like the scanner, this MEASURES; it never verdicts. Every result carries
`purpose="diction_bias_only"` and `authorizes_edit=False` so a consumer cannot mistake it for an
edit authorization.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_scan.extract import split_sentences, words  # noqa: E402

# contraction apostrophe (straight or curly); a word containing one is a contraction ("can't", "we'll")
_APOS = ("'", "’")
_FIRST = {"i", "we", "me", "us", "my", "our", "mine", "ours", "i'm", "we're", "we'll", "i'll",
          "i've", "we've", "i'd", "we'd"}
_SECOND = {"you", "your", "yours", "you're", "you'll", "you've", "you'd", "yourself"}


class VoiceError(RuntimeError):
    """The provided voice sample was not decodable UTF-8. Fail loud — never guess a voice."""


def _contraction_rate(toks: list[str]) -> float:
    if not toks:
        return 0.0
    n = sum(1 for w in toks if any(a in w for a in _APOS))
    return round(n / len(toks), 4)


def _person_lean(toks: list[str]) -> str:
    lowered = [w.lower() for w in toks]
    first = sum(1 for w in lowered if w in _FIRST)
    second = sum(1 for w in lowered if w in _SECOND)
    # third person is the residual — inferred, not counted, so it is the fallback when neither
    # first nor second pronouns lead. "none" only when there are no words at all.
    if not toks:
        return "none"
    if first == 0 and second == 0:
        return "third"
    return "first" if first >= second else "second"


def _punctuation(text: str, sentences: list[str]) -> dict:
    n = max(len(sentences), 1)
    return {
        "exclamation_rate": round(text.count("!") / n, 4),
        "question_rate": round(text.count("?") / n, 4),
        "em_dash_rate": round((text.count("—") + text.count(" -- ")) / n, 4),
        "semicolon_rate": round(text.count(";") / n, 4),
    }


def extract_voice_features(sample) -> dict:
    """Extract measure-only diction signals from a single voice sample (str or UTF-8 bytes).

    Returns a dict — NEVER an edit or an authorization:
      {purpose:"diction_bias_only", authorizes_edit:False,
       contraction_rate:float, mean_sentence_len:float, person_lean:"first|second|third|none",
       punctuation:{exclamation_rate,question_rate,em_dash_rate,semicolon_rate}, sample_words:int}
    """
    if isinstance(sample, (bytes, bytearray)):
        try:
            text = bytes(sample).decode("utf-8")
        except UnicodeDecodeError as err:
            raise VoiceError(f"voice sample is not valid utf-8: {err}") from err
    elif isinstance(sample, str):
        text = sample
    else:
        raise VoiceError(f"voice sample must be str or bytes, got {type(sample).__name__}")

    toks = words(text)
    sentences = [s for s in split_sentences(text) if s.strip()]
    mean_len = round(sum(len(words(s)) for s in sentences) / len(sentences), 4) if sentences else 0.0

    return {
        "purpose": "diction_bias_only",   # measure-only; NEVER authorizes or widens an edit
        "authorizes_edit": False,
        "contraction_rate": _contraction_rate(toks),
        "mean_sentence_len": mean_len,
        "person_lean": _person_lean(toks),
        "punctuation": _punctuation(text, sentences),
        "sample_words": len(toks),
    }
