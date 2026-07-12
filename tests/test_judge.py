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

    t = Trial({"meaning_preservation": 5}, {"meaning_preservation": 1})
    with pytest.raises(ValueError):
        t.validate()
