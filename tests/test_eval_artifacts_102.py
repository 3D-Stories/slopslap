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
    assert checked == len(fixture_pairs) * judge["trials_per_pair"], "every pair, every trial"


def test_the_blind_file_and_the_judge_run_share_one_run_id(fixture_pairs):
    """Side hashes are salted with `run_id`, so two artifacts only bind if the salt is the same."""
    assert _load(PAIRS_FILE)["run_id"] == _load(JUDGE_FILE)["run_id"]


def test_the_published_numbers_are_the_ones_the_trials_support(fixture_pairs):
    """No number is pinned by hand here: the first version of this test pinned 3 pairs, 9 trials
    and 55.6%, and those were measured on machine-authored prose (the #102 critical finding). So
    the figures are RECOMPUTED from the trials the committed judge.json carries, then compared with
    its own summary and with the results object the document renders from."""
    judge = _load(JUDGE_FILE)
    s = judge["summary"]
    n = len(fixture_pairs)
    assert judge["status"] == "completed" and s["pairs"] == n and n >= 1
    assert s["pairs_completed"] == n and s["pairs_errored"] == 0 and s["trials_failed"] == 0
    assert s["trials_valid"] == s["trials_scored"] == n * judge["trials_per_pair"]
    by_id = {p.pair_id: p for p in fixture_pairs}
    run_id = judge["run_id"]
    applied = original = equal = 0
    majority = 0
    for jp in judge["pairs"]:
        ok = [tr for tr in jp["trials"] if tr.get("ok")]
        assert len(ok) == judge["trials_per_pair"], jp["pair_id"]
        # Derive each role from the recorded PICK and the side the applied bytes actually sat on
        # (recomputed from the side hashes) — never from the stored `preferred_role`, which is itself
        # a derived field a hand edit could change (Step 11 re-run D3).
        h_app = P.side_hash(run_id, by_id[jp["pair_id"]].applied)
        roles = []
        for tr in ok:
            applied_side = "A" if tr["a_side_hash"] == h_app else "B"
            assert tr["b_side_hash" if applied_side == "A" else "a_side_hash"] != h_app
            pick = tr["preferred_side"]
            roles.append("applied" if pick == applied_side else ("original" if pick in ("A", "B") else "equal"))
            assert tr["preferred_role"] == roles[-1], (jp["pair_id"], tr["trial"])
        a = roles.count("applied")
        o = roles.count("original")
        e = len(ok) - a - o
        assert (jp["applied_preferred_trials"], jp["original_preferred_trials"], jp["equal_trials"]) == (a, o, e), jp["pair_id"]
        assert jp["majority_applied"] is (a > o), jp["pair_id"]
        applied += a; original += o; equal += e
        majority += 1 if a > o else 0
    assert (s["applied_preferred_trials"], s["original_preferred_trials"], s["equal_trials"]) == (applied, original, equal)
    decided = applied + original
    assert s["applied_preference_pct_of_decided"] == (round(100.0 * applied / decided, 1) if decided else None)
    assert s["pairs_majority_applied"] == majority
    beat = sum(1 for jp in judge["pairs"]
               if jp["verdict"]["present"] and not jp["verdict"]["errored"] and jp["verdict"]["beat"])
    assert s["pairs_beat"] == beat
    # the results object the document renders from carries the same figures
    published = _load(RESULTS_FILE)["llm_judge"]["summary"]
    for k in ("applied_preferred_trials", "original_preferred_trials", "equal_trials",
              "applied_preference_pct_of_decided", "pairs_majority_applied", "pairs_beat", "trials_scored"):
        assert published[k] == s[k], k


def test_the_judge_model_differs_from_every_engine_model(fixture_pairs):
    """AC3's cross-model condition, checked against the committed record rather than asserted."""
    judge = _load(JUDGE_FILE)
    engines = sorted({p.engine_model for p in fixture_pairs})
    assert engines and judge["engine_models"] == engines
    with pytest.raises(P.PairError, match="cross-model"):
        P._cross_model_guard(engines[0], engines)
    P._cross_model_guard(judge["model"], engines)  # the real pairing must NOT raise
    assert judge["model_confirmed"] is False, "the Codex CLI echoes no model identity"


def test_pairs_beat_is_recomputed_from_the_verdicts(fixture_pairs):
    """Step 11 re-run F6: `pairs_beat` was only range-checked; a stale value from 0 to N passed."""
    judge = _load(JUDGE_FILE)
    beat = sum(1 for jp in judge["pairs"]
               if jp["verdict"]["present"] and not jp["verdict"]["errored"] and jp["verdict"]["beat"])
    assert judge["summary"]["pairs_beat"] == beat
    assert _load(RESULTS_FILE)["llm_judge"]["summary"]["pairs_beat"] == beat


def test_committed_pair_artifacts_carry_no_host_paths(fixture_pairs):
    """Step 11 re-run F8: the apply RunResults used to embed the owner's home directory and workspace
    layout (source_path, backup path, restore command). Committed artifacts carry placeholders instead."""
    import glob
    offenders = []
    for path in glob.glob(os.path.join(FX, "pair-102-*", "*.json")) + glob.glob(os.path.join(EVAL_DIR, "*.json")):
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        for needle in ("/home/", "rocky00717", ".wf2-state", "/tmp/"):
            if needle in text:
                offenders.append((os.path.relpath(path, REPO), needle))
    assert offenders == [], offenders
