"""slop→clean golden PAIR fixtures.

Each `tests/fixtures/eval/pair-*` dir is a labeled before/after pair: `original.md` (slop) +
`clean.md` (the target clean rewrite) + a loader-valid `fixture.json`. Unlike the `qa-*` cases
(single-doc discrepancies) and the clean-only controls, a pair carries the *destination* an
aggressive de-slop pass should approach — the labeled data the #25 calibration harness was
starved of. See `tests/fixtures/eval/qa-fixtures.md` (Golden pairs section).

This hermetic guard globs `pair-*`, so new pairs are drop-in. It does NOT assert that any
particular edit reproduces `clean.md` byte-for-byte — that (and promotion into the pinned
`run_eval` inventory) needs a live model and is a deliberate follow-up.
"""
import glob
import os

from eval.loader import load_fixture, validate_manifest

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "eval")
PAIR_DIRS = sorted(d for d in glob.glob(os.path.join(FX, "pair-*")) if os.path.isdir(d))


def test_golden_pairs_present():
    # fail closed: an empty glob must NOT let the checks below pass vacuously
    assert len(PAIR_DIRS) >= 2, f"expected the seeded slop→clean pairs, found {PAIR_DIRS}"


def test_golden_pairs_validate():
    for d in PAIR_DIRS:
        original, manifest = load_fixture(d)
        name = os.path.basename(d)
        assert original, f"{name}: empty original.md"
        assert validate_manifest(original, manifest) == [], name


def test_golden_pairs_have_distinct_clean_target():
    for d in PAIR_DIRS:
        original, manifest = load_fixture(d)
        name = os.path.basename(d)
        # honor the manifest's declared clean_file (default clean.md) — the field is not dead data
        clean_name = manifest.get("clean_file", "clean.md")
        clean_path = os.path.join(d, clean_name)
        assert os.path.isfile(clean_path), f"{name}: missing {clean_name} (the after target)"
        with open(clean_path, "rb") as fh:
            clean = fh.read()
        assert clean, f"{name}: empty {clean_name}"
        clean.decode("utf-8")  # a pair target must be valid UTF-8 (raises => fail)
        assert clean != original, f"{name}: {clean_name} is byte-identical to original.md (not a pair)"


def test_golden_pairs_disposition_is_coherent():
    for d in PAIR_DIRS:
        _, m = load_fixture(d)
        name = os.path.basename(d)
        # a pair contains slop by construction — never a clean control
        assert m["control"] is False, f"{name}: a golden pair must be control:false"
        assert m["seeded_defects"], f"{name}: a pair must name the slop it removes"
