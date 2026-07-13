"""Real-world QA fixtures captured from the Winnipeg SMS deck (doc-owner labeled 2026-07-13).

These are DATA fixtures: two must-abstain controls (first-pass false positives) and one
flag-only true positive. They are NOT yet in the pinned `run_eval` inventory (that needs a
live-model first-pass digest); this hermetic test guards their validity and the labeled
disposition so the lessons cannot silently rot.
"""
import os

from eval.loader import load_fixture, validate_manifest

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "eval")
CONTROLS = ["qa-clean-numeric-referent", "qa-clean-hedged-example"]
FLAG_ONLY = "qa-flag-missing-basis"


def _load(name):
    return load_fixture(os.path.join(FX, name))


def test_qa_fixtures_validate():
    for name in CONTROLS + [FLAG_ONLY]:
        original, manifest = _load(name)
        assert original, f"{name}: empty original.md"
        assert validate_manifest(original, manifest) == [], name
        assert manifest["genre"] == "technical", name


def test_qa_controls_are_abstain_cases():
    # the two false positives: the tool must leave clean prose alone (no authorized edit)
    for name in CONTROLS:
        _, m = _load(name)
        assert m["control"] is True, name
        assert m["editable_ranges"] == [], name
        assert m["seeded_defects"] == [], name
        assert m["control_reason"], f"{name}: a control must document WHY abstention is correct"


def test_qa_flag_only_is_simulation_never_edited():
    # the valid-but-minor finding: category simulation, remedy = flag, NEVER fabricate a citation
    _, m = _load(FLAG_ONLY)
    assert m["control"] is False
    assert m["editable_ranges"] == [], "flag-only: no edit is authorized"
    assert m["expected_preservation_failure"] is True, "any inserted source is fabrication -> reject"
    classes = [d["class"] for d in m["seeded_defects"]]
    assert classes == ["simulation"], classes
