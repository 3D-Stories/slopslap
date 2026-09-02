from eval import judge
from eval.judge import Trial


def _full(score):
    return {d: score for d in judge.DIMENSIONS}


def test_beat_criterion_true_when_strictly_better():
    cand = _full(2)
    base = _full(1)
    assert judge.beat_criterion(cand, base)


def test_beat_criterion_false_on_equal():
    assert not judge.beat_criterion(_full(1), _full(1))  # no strict win


def test_beat_criterion_false_when_worse_by_more_than_one():
    cand = _full(2)
    base = _full(1)
    # tank one dimension by 2 -> disqualified even though sum may still be >=
    first = next(iter(judge.DIMENSIONS))
    cand[first] = 0
    base[first] = 2
    assert not judge.beat_criterion(cand, base)


def test_evaluate_requires_three_trials():
    v = judge.evaluate([Trial(_full(2), _full(1))])
    assert v.errored and v.present


def test_evaluate_median_and_beat():
    trials = [Trial(_full(2), _full(1)) for _ in range(3)]
    v = judge.evaluate(trials)
    assert v.present and not v.errored and v.beat


def test_run_trials_handles_judge_errors():
    def boom(*a):
        raise RuntimeError("model down")

    v = judge.run_trials(boom, {}, b"", b"", b"")
    assert v.errored and v.present and not v.beat


def test_trial_validation_rejects_bad_scores():
    import pytest

    full = _full(1)
    full["meaning_preservation"] = 5
    t = Trial(full, _full(1))
    with pytest.raises(ValueError):
        t.validate()


def test_incomplete_dimension_set_rejected():
    # a partial trial that omits unfavorable dimensions must not validate (WF5-diff F5)
    import pytest

    partial = {"meaning_preservation": 2}  # only one dimension
    with pytest.raises(ValueError):
        Trial(partial, _full(1)).validate()


def test_incomplete_trial_makes_evaluate_errored():
    partial = {"meaning_preservation": 2}
    trials = [Trial(partial, _full(1)) for _ in range(3)]
    v = judge.evaluate(trials)
    assert v.errored and not v.beat


def test_beat_criterion_requires_full_dimension_set():
    # a median map missing dimensions can never beat
    assert not judge.beat_criterion({"meaning_preservation": 2.0}, _full(1))


# ---------------------------------------------------------------------------- #102: blind A/B contract
# The judge request/response contract that wires the scaffold above to a live, BLIND judge. The
# request names the two sides only as A and B; the response is validated against a closed schema;
# the mapping back to candidate-vs-baseline scores is a pure function of (parsed, applied_side).
import json as _json

from eval.judge import (
    JUDGE_SCHEMA, build_judge_request, judge_fn_for, live_judge_available, parse_judge_response,
    role_of, trial_from_blind,
)

_ROLE_WORDS = ("slopslap", "applied", "original", "rewrite", "candidate", "baseline", "engine")


def _valid(preferred="A", fill="A"):
    return {"preferred": preferred, "dimensions": {d: fill for d in judge.DIMENSIONS}, "reason": "A is tighter."}


def test_schema_is_closed_and_names_every_dimension():
    assert JUDGE_SCHEMA["additionalProperties"] is False
    # the structured-output contract requires EVERY property to be required (live 400 otherwise)
    assert set(JUDGE_SCHEMA["required"]) == set(JUDGE_SCHEMA["properties"]) == {"preferred", "dimensions", "reason"}
    dims = JUDGE_SCHEMA["properties"]["dimensions"]
    assert set(dims["properties"]) == set(judge.DIMENSIONS)
    assert dims["additionalProperties"] is False
    assert set(dims["required"]) == set(judge.DIMENSIONS)
    for spec in dims["properties"].values():
        assert spec["enum"] == ["A", "B", "equal"]
    assert JUDGE_SCHEMA["properties"]["preferred"]["enum"] == ["A", "B", "equal"]


def test_request_carries_both_texts_as_data_and_no_role_words():
    req = build_judge_request("First paragraph text.", "Second paragraph text.")
    obj = _json.loads(req)
    assert obj["text_a"] == "First paragraph text." and obj["text_b"] == "Second paragraph text."
    instr = obj["instruction"].lower()
    for word in _ROLE_WORDS:
        assert word not in instr, word
    assert "data" in instr  # the texts are untrusted data, never instructions
    for dim in judge.DIMENSIONS:
        assert dim in req
    assert build_judge_request("x", "y") == build_judge_request("x", "y")  # deterministic bytes


def test_request_rejects_non_text():
    import pytest
    with pytest.raises(ValueError):
        build_judge_request(b"bytes", "y")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        build_judge_request("", "y")


def test_parse_accepts_a_complete_verdict():
    got = parse_judge_response(_valid("B", "equal"))
    assert got["preferred"] == "B"
    assert got["dimensions"] == {d: "equal" for d in judge.DIMENSIONS}
    assert got["reason"] == "A is tighter."


def test_parse_fails_closed_on_every_shape_problem():
    assert parse_judge_response(None) is None
    assert parse_judge_response("A") is None
    bad = _valid(); del bad["dimensions"]["meaning_preservation"]
    assert parse_judge_response(bad) is None                          # missing dimension
    bad = _valid(); bad["dimensions"]["made_up"] = "A"
    assert parse_judge_response(bad) is None                          # unknown dimension
    bad = _valid(); bad["dimensions"]["genre_fitness"] = "C"
    assert parse_judge_response(bad) is None                          # bad enum
    bad = _valid(); bad["preferred"] = "both"
    assert parse_judge_response(bad) is None
    bad = _valid(); bad["extra"] = 1
    assert parse_judge_response(bad) is None                          # closed object
    bad = _valid(); bad["reason"] = "x" * 5000
    assert parse_judge_response(bad) is None                          # oversized free text
    bad = _valid(); del bad["reason"]
    assert parse_judge_response(bad)["reason"] == ""                  # reason is optional


def test_role_of_maps_side_letters_through_the_applied_side():
    assert role_of("A", "A") == "applied" and role_of("B", "A") == "original"
    assert role_of("A", "B") == "original" and role_of("B", "B") == "applied"
    assert role_of("equal", "A") == "equal"


def test_trial_from_blind_maps_wins_to_candidate_vs_baseline_scores():
    parsed = parse_judge_response({"preferred": "A", "reason": "",
                                   "dimensions": {**{d: "A" for d in judge.DIMENSIONS},
                                                  "genre_fitness": "B", "voice_distance_from_samples": "equal"}})
    t = trial_from_blind(parsed, applied_side="A")
    t.validate()
    assert t.candidate["meaning_preservation"] == 2 and t.baseline["meaning_preservation"] == 0
    assert t.candidate["genre_fitness"] == 0 and t.baseline["genre_fitness"] == 2
    assert t.candidate["voice_distance_from_samples"] == 1 and t.baseline["voice_distance_from_samples"] == 1
    # mirrored when the applied text sat on side B
    t2 = trial_from_blind(parsed, applied_side="B")
    assert t2.candidate["meaning_preservation"] == 0 and t2.baseline["meaning_preservation"] == 2
    assert t2.candidate["genre_fitness"] == 2


def test_three_all_win_trials_beat_through_the_existing_scaffold():
    parsed = parse_judge_response(_valid("A", "A"))
    trials = [trial_from_blind(parsed, "A") for _ in range(3)]
    v = judge.evaluate(trials)
    assert v.present and not v.errored and v.beat


def test_live_judge_available_reads_the_env_gate(monkeypatch):
    monkeypatch.delenv("SLOPSLAP_LIVE", raising=False)
    assert live_judge_available() is False
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    assert live_judge_available() is True
    monkeypatch.setenv("SLOPSLAP_LIVE", "yes")
    assert live_judge_available() is False


def test_judge_fn_for_wraps_an_injected_transport_and_fails_closed():
    calls = []
    def good(request, *, model, schema, timeout_s, status_sink=None):
        calls.append((model, timeout_s, _json.loads(request)["text_a"]))
        return _valid("B", "B")
    fn = judge_fn_for("gpt-5.6-sol", timeout_s=7.0, transport=good)
    assert fn("aaa", "bbb")["preferred"] == "B"
    assert calls == [("gpt-5.6-sol", 7.0, "aaa")]
    assert judge_fn_for("m", transport=lambda *a, **k: None)("a", "b") is None          # transport failure
    assert judge_fn_for("m", transport=lambda *a, **k: {"junk": 1})("a", "b") is None   # unparseable content
