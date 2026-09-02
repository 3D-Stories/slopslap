"""#102 — the COMMITTED eval artifacts under docs/reviews/102-eval/ must still recompute.

A Step 11 reviewer claimed the committed `judge.json` had its roles inverted for one pair, so the
published 55.6% figure was mis-scored. It was wrong: every trial's recorded `applied_side` does
recompute from its own side hashes against the real fixture bytes. But it took a hand-run of
`validate_judge_json` to establish that, and a claim that costs a hand-run to refute will be made
again. So the refutation lives here as an executable guard.

These tests bind the published numbers to the fixtures they came from. A fixture edit, an artifact
edit, or a validator regression all fail here rather than in a reader's head.
"""
import json
import os

import pytest

from eval import preference as P

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(REPO, "tests", "fixtures", "eval")
EVAL_DIR = os.path.join(REPO, "docs", "reviews", "102-eval")
PAIRS_FILE = os.path.join(EVAL_DIR, "pairs.json")
JUDGE_FILE = os.path.join(EVAL_DIR, "judge.json")
RESULTS_FILE = os.path.join(EVAL_DIR, "results.json")


@pytest.fixture(scope="module")
def fixture_pairs():
    return P.load_eval_pairs(FX)


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_the_committed_blind_file_is_this_fixture_set(fixture_pairs):
    P.validate_blind_json(_load(PAIRS_FILE), fixture_pairs)


def test_the_committed_judge_run_recomputes_against_this_fixture_set(fixture_pairs):
    """The whole of the reviewer's inverted-roles claim, as one call."""
    P.validate_judge_json(_load(JUDGE_FILE), fixture_pairs, name="the committed judge.json")


def test_every_committed_trial_applied_side_recomputes_from_its_own_side_hashes(fixture_pairs):
    """The specific claim, spelled out: the reviewer said `aaf2…` was bound to the ORIGINAL wording
    and labelled applied. It is bound to the applied wording, and every trial agrees."""
    judge = _load(JUDGE_FILE)
    by_id = {p.pair_id: p for p in fixture_pairs}
    run_id = judge["run_id"]
    checked = 0
    for jp in judge["pairs"]:
        fx = by_id[jp["pair_id"]]
        h_orig = P.side_hash(run_id, fx.original)
        h_app = P.side_hash(run_id, fx.applied)
        assert h_orig != h_app
        for tr in jp["trials"]:
            assert {tr["a_side_hash"], tr["b_side_hash"]} == {h_orig, h_app}, jp["pair_id"]
            recomputed = "A" if tr["a_side_hash"] == h_app else "B"
            assert tr["applied_side"] == recomputed, (jp["pair_id"], tr["trial"])
            checked += 1
    assert checked == 9, "three pairs, three trials each"


def test_the_blind_file_and_the_judge_run_share_one_run_id(fixture_pairs):
    """Side hashes are salted with `run_id`, so two artifacts only bind if the salt is the same."""
    assert _load(PAIRS_FILE)["run_id"] == _load(JUDGE_FILE)["run_id"]


def test_the_published_numbers_are_the_ones_the_trials_support(fixture_pairs):
    judge = _load(JUDGE_FILE)
    s = judge["summary"]
    assert judge["status"] == "completed" and s["pairs"] == len(fixture_pairs) == 3
    assert s["pairs_completed"] == 3 and s["pairs_errored"] == 0
    assert s["trials_valid"] == 9 and s["trials_scored"] == 9 and s["trials_failed"] == 0
    assert s["applied_preferred_trials"] == 5 and s["original_preferred_trials"] == 4
    assert s["equal_trials"] == 0 and s["applied_preference_pct_of_decided"] == 55.6
    assert s["pairs_majority_applied"] == 2 and s["pairs_beat"] == 2
    # the results object the document renders from carries the same figures
    published = _load(RESULTS_FILE)["llm_judge"]["summary"]
    assert published["applied_preference_pct_of_decided"] == 55.6
    assert published["applied_preferred_trials"] == 5


def test_the_judge_model_differs_from_every_engine_model(fixture_pairs):
    """AC3's cross-model condition, checked against the committed record rather than asserted."""
    judge = _load(JUDGE_FILE)
    engines = sorted({p.engine_model for p in fixture_pairs})
    assert engines and judge["engine_models"] == engines
    with pytest.raises(P.PairError, match="cross-model"):
        P._cross_model_guard(engines[0], engines)
    P._cross_model_guard(judge["model"], engines)  # the real pairing must NOT raise
    assert judge["model_confirmed"] is False, "the Codex CLI echoes no model identity"
