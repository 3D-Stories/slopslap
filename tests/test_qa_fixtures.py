"""Real-world QA discrepancy fixtures (doc-owner labeled).

Each `tests/fixtures/eval/qa-*` dir captures one case where a live slopslap run's diagnosis
diverged from a document owner's ground-truth label. They are DATA fixtures accumulating toward
promotion into the pinned `run_eval` inventory (which needs a live-model first-pass digest); see
`tests/fixtures/eval/qa-fixtures.md`. This hermetic test guards their validity + labeled
disposition so the lessons cannot silently rot. It GLOBS `qa-*`, so new captures are drop-in.
"""
import glob
import os

from eval.loader import load_fixture, validate_manifest

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "eval")
QA_DIRS = sorted(
    d for d in glob.glob(os.path.join(FX, "qa-*")) if os.path.isdir(d)
)


def test_qa_fixtures_present():
    # fail closed: an empty glob must NOT let the disposition checks pass vacuously
    assert len(QA_DIRS) >= 3, f"expected the captured qa-* fixtures, found {QA_DIRS}"


def test_qa_fixtures_validate():
    for d in QA_DIRS:
        original, manifest = load_fixture(d)
        name = os.path.basename(d)
        assert original, f"{name}: empty original.md"
        assert validate_manifest(original, manifest) == [], name


def test_qa_fixtures_disposition_is_coherent():
    for d in QA_DIRS:
        _, m = load_fixture(d)
        name = os.path.basename(d)
        if m["control"]:
            # false positive: the tool must leave clean prose alone (loader already forbids
            # editable_ranges on a control; assert the rest of the abstain contract + the lesson)
            assert m["seeded_defects"] == [], name
            assert m["control_reason"], f"{name}: a control must document WHY abstention is correct"
        else:
            # true positive: a defect is named
            assert m["seeded_defects"], f"{name}: a non-control must name its seeded defect(s)"
            if m["editable_ranges"] == []:
                # flag-only remedy (e.g. simulation): no edit authorized, any insertion fabricates
                assert m.get("expected_preservation_failure") is True, (
                    f"{name}: flag-only fixture must set expected_preservation_failure"
                )
