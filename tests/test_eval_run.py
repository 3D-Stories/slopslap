"""The DONE gate: invoke the evaluator and assert the contract §7 outcomes (design R4/R11).

Iterates the explicit decision-rule inventory; does not trust committed result files.
"""

import os

from eval.run_eval import (
    CANONICAL, CANONICAL_GATES, CONTROL_GATES, CONTROLS, MD_PATH, render_md, run_eval,
)

# pinned first-pass slopslap output digests — freezes the SKILL's demonstrated output (design R3).
PINNED_SLOPSLAP_OUTPUT = {
    "distinctive-essay": "2089d05a94a8f5c366415f01cf3c396ad454c2c566ebc36614ba3958bbda3712",
    "normative-spec": "c4fea54776ce1d4f137d2a2067fb7ed6769e43aea50dccecdcfda6d73cc6eeb8",
    "underspecified-prd": "7c544731a5f7cac0a8bd2bfbd95c4738e4531ea9c77db0e7c78b7d483683829a",
    "clean-personal": "4b43b822e24b4989c6e5de888912549e72c38f92975c602b2c8f72cdda1d1d64",
    "clean-spec": "5c3b460fecc139d43824a930354f9d8515614059b0d36f6d43f2c73113fb4ceb",
}

_R = run_eval()  # run once for the module


def test_all_done_criteria_pass():
    assert _R["done"]["ALL_PASS"] is True, _R["done"]


def test_slopslap_clears_hard_gates_on_all_canonicals():
    for fx in CANONICAL:
        cell = _R["fixtures"][fx]["baselines"]["slopslap"]
        assert cell["hard_gates_pass"], (fx, cell["gates"])
        # no expected gate absent + none failed
        assert not any(v == "fail" for v in cell["gates"].values()), (fx, cell["gates"])


def test_slopslap_abstains_on_controls_without_byte_change():
    for fx in CONTROLS:
        cell = _R["fixtures"][fx]["baselines"]["slopslap"]
        assert cell["disposition"] == "abstain" and cell["unchanged"] is True, (fx, cell)


def test_slopslap_first_pass_output_matches_pinned_digest():
    for fx in CANONICAL + CONTROLS:
        got = _R["fixtures"][fx]["baselines"]["slopslap"]["output_sha256"]
        assert got == PINNED_SLOPSLAP_OUTPUT[fx], f"{fx}: {got}"


def test_slopslap_idempotent_second_pass_empty():
    for fx in CANONICAL + CONTROLS:
        assert _R["fixtures"][fx]["baselines"]["slopslap"]["second_pass_edits"] == 0, fx


def test_kukakuka_real_repair_zero_invariant_violations():
    k = _R["kukakuka"]
    # a REAL model-driven audit repaired demonstrated harm (NOT a stub abstention) with 0
    # invariant violations (issue #14 fix)
    assert k["invariant_violations"] == 0
    assert k["disposition"] == "repair" and k["edits"] >= 1
    assert k["preservation"]["headings_preserved"] is True
    assert k["negative_control_bad_edit_rejected"] is True


def test_kukakuka_scanner_flags_the_cadence_tells():
    # the scanner must actually SEE the synthetic-cadence class (was a 0-cluster coverage gap)
    cad = _R["kukakuka"]["audit"]["cadence"]
    assert cad["negative_parallelism"] >= 5 and cad["negative_parallelism_flagged"] is True
    assert cad["punctuation_flagged"] is True


def test_beats_or_ties_humanizer_emulation():
    assert _R["comparison"]["verdict"] in ("BEATS", "TIES")
    assert _R["comparison"]["worse_anywhere"] is False


def test_decision_rule_inventory_complete_and_all_required_gates_pass():
    # every required gate for the fixture TYPE must be present AND "pass" (WF5-diff H5)
    for fx in CANONICAL:
        gates = _R["fixtures"][fx]["baselines"]["slopslap"]["gates"]
        for g in CANONICAL_GATES:
            assert gates.get(g) == "pass", (fx, g, gates)
    for fx in CONTROLS:
        gates = _R["fixtures"][fx]["baselines"]["slopslap"]["gates"]
        for g in CONTROL_GATES:
            assert gates.get(g) == "pass", (fx, g, gates)


def test_kukakuka_negative_control_rejects_bad_edit():
    # proves the ledger is LIVE (a hypothetical invariant-violating edit is rejected)
    assert _R["kukakuka"]["negative_control_bad_edit_rejected"] is True


def test_committed_artifact_matches_live_render():
    # a stale committed report (obsolete PASS) fails CI (WF5-diff H6)
    assert os.path.exists(MD_PATH), "results artifact not committed"
    with open(MD_PATH, encoding="utf-8") as fh:
        committed = fh.read()
    assert committed == render_md(_R), "committed eval-results.md is stale (re-run run_eval.py --write)"


def test_judge_status_is_surfaced():
    assert _R["judge"]["status"] in ("not_run", "failed", "completed")
