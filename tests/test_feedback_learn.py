"""P5 (#63) learning CONSUMER: the feedback ledger tunes the RECOMMENDATION only (keep-only overlay).

learn_from_feedback aggregates per (genre, metric-class) keep-evidence:
  - discard of a STRIP rec  -> +1 (the user overrode the strip = keep-evidence)
  - edit of a STRIP rec     -> +0.5 (partial-accept: kept tokens are real claims)
  - apply of a STRIP rec    -> -1 (the user endorsed the strip = evidence AGAINST a keep-flip)
When a (genre, class) net score reaches min_evidence, that class flips strip->keep for that genre.
apply_overlay is KEEP-ONLY: it can turn strip->keep, never keep->strip.
"""

from slopslap_corpus.learn import apply_overlay, learn_from_feedback
from slopslap_scan.metrics import METRIC_CLASS

# transition_clusters is in the "filler" class; negative_parallelism is in "cadence"
_M = "transition_clusters"
_CLS = METRIC_CLASS[_M]


def _line(genre, metric, rec, action, reason=None):
    ln = {"ts": "2026-07-14T16:00:00Z", "finding_id": f"{metric}:abc", "category": METRIC_CLASS[metric],
          "metric": metric, "genre": genre, "recommendation": rec, "user_action": action,
          "doc_sha": "0" * 64}
    if reason:
        ln["reason"] = reason
    return ln


def test_three_strip_overrides_flip_class_to_keep():
    lines = [_line("general", _M, "strip", "discard", "false_positive") for _ in range(3)]
    ov = learn_from_feedback(lines, min_evidence=3)
    assert _CLS in ov.keep_classes.get("general", frozenset())
    assert apply_overlay("strip", "general", _M, ov) == "keep"


def test_below_threshold_does_not_flip():
    lines = [_line("general", _M, "strip", "discard") for _ in range(2)]
    ov = learn_from_feedback(lines, min_evidence=3)
    assert _CLS not in ov.keep_classes.get("general", frozenset())
    assert apply_overlay("strip", "general", _M, ov) == "strip"


def test_edits_are_half_weight_partial_accept():
    six_edits = learn_from_feedback([_line("general", _M, "strip", "edit") for _ in range(6)], min_evidence=3)
    assert _CLS in six_edits.keep_classes.get("general", frozenset())     # 6*0.5 = 3.0 -> flip
    four_edits = learn_from_feedback([_line("general", _M, "strip", "edit") for _ in range(4)], min_evidence=3)
    assert _CLS not in four_edits.keep_classes.get("general", frozenset())  # 4*0.5 = 2.0 -> no flip


def test_apply_nets_against_keep_evidence():
    flip = learn_from_feedback(
        [_line("general", _M, "strip", "discard") for _ in range(4)] + [_line("general", _M, "strip", "apply")],
        min_evidence=3)
    assert _CLS in flip.keep_classes.get("general", frozenset())            # 4 - 1 = 3 -> flip
    noflip = learn_from_feedback(
        [_line("general", _M, "strip", "discard") for _ in range(3)] + [_line("general", _M, "strip", "apply")],
        min_evidence=3)
    assert _CLS not in noflip.keep_classes.get("general", frozenset())      # 3 - 1 = 2 -> no flip


def test_keep_recommendation_lines_contribute_nothing():
    lines = [_line("general", _M, "keep", "discard") for _ in range(5)]
    ov = learn_from_feedback(lines, min_evidence=3)
    assert _CLS not in ov.keep_classes.get("general", frozenset())


def test_apply_overlay_is_keep_only():
    ov = learn_from_feedback([_line("general", _M, "strip", "discard") for _ in range(3)], min_evidence=3)
    # a flipped class never turns a base KEEP into strip
    assert apply_overlay("keep", "general", _M, ov) == "keep"
    # a class that was NOT flipped leaves strip as strip
    assert apply_overlay("strip", "spec", _M, ov) == "strip"
    # no overlay at all is a no-op
    assert apply_overlay("strip", "general", _M, None) == "strip"


def test_empty_ledger_yields_empty_overlay():
    ov = learn_from_feedback([], min_evidence=3)
    assert ov.keep_classes == {}
    assert apply_overlay("strip", "general", _M, ov) == "strip"


def test_all_apply_never_flips():
    # a user who consistently ACCEPTS the strip must never flip the class to keep
    ov = learn_from_feedback([_line("general", _M, "strip", "apply") for _ in range(10)], min_evidence=3)
    assert _CLS not in ov.keep_classes.get("general", frozenset())


def test_per_genre_isolation():
    ov = learn_from_feedback([_line("personal", _M, "strip", "discard") for _ in range(3)], min_evidence=3)
    assert apply_overlay("strip", "personal", _M, ov) == "keep"    # learned in personal
    assert apply_overlay("strip", "general", _M, ov) == "strip"    # NOT leaked to general


def test_alternative_labeled_lines_never_flip_toward_strip():
    # #84 AC3: alternative-labeled feedback consumes cleanly and the overlay stays KEEP-ONLY —
    # no volume of alternative-pick edits can flip a keep recommendation to strip.
    from slopslap_corpus.learn import learn_from_feedback, apply_overlay
    lines = [{
        "schema_version": 1, "ts": "2026-07-15T09:00:00Z",
        "finding_id": f"generic_diction:{i:016x}", "category": "diction",
        "metric": "generic_diction", "genre": "marketing", "recommendation": "strip",
        "user_action": "edit", "replacement": "d2Ugc3RhbmQgYmVoaW5kIGl0",
        "alternative": "subjectivize", "doc_sha": "a" * 64,
    } for i in range(20)]
    overlay = learn_from_feedback(lines)
    # the alternative-labeled edits WERE consumed: 20 edits clear min_evidence, so the strip
    # base actually softens to keep (an empty/broken overlay would leave it "strip")
    assert apply_overlay("strip", "marketing", "generic_diction", overlay) == "keep"
    # keep-only is STRUCTURAL: the overlay exposes only keep_classes — there is no field or
    # mechanism through which any feedback volume could force a keep base toward strip
    assert set(vars(overlay)) == {"keep_classes"}, vars(overlay)
    assert apply_overlay("keep", "marketing", "generic_diction", overlay) == "keep"
