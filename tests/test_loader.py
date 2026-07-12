from eval.loader import validate_manifest
from slopslap_verification.editscript import sha256_hex

ORIG = b"The client MUST wait 200 ms.\n"


def _base():
    return {
        "schema_version": 1,
        "genre": "spec",
        "control": False,
        "byte_policy": {"encoding": "utf-8", "trailing_newline": "preserve"},
        "editable_ranges": [],
        "protected_spans": [],
        "invariant_regions": [],
        "expected_invariants": [],
        "allowed_claim_atoms": [],
        "seeded_defects": [],
        "control_reason": None,
    }


def test_valid_manifest_has_no_problems():
    assert validate_manifest(ORIG, _base()) == []


def test_bad_schema_version():
    m = _base()
    m["schema_version"] = 99
    assert any("schema_version" in p for p in validate_manifest(ORIG, m))


def test_out_of_bounds_range():
    m = _base()
    m["editable_ranges"] = [{"start_byte": 0, "end_byte": 9999}]
    assert any("out of bounds" in p for p in validate_manifest(ORIG, m))


def test_overlapping_editable_ranges():
    m = _base()
    m["editable_ranges"] = [
        {"start_byte": 0, "end_byte": 10},
        {"start_byte": 5, "end_byte": 12},
    ]
    assert any("overlap" in p for p in validate_manifest(ORIG, m))


def test_editable_protected_not_disjoint():
    m = _base()
    m["editable_ranges"] = [{"start_byte": 0, "end_byte": 10}]
    m["protected_spans"] = [
        {"start_byte": 5, "end_byte": 8, "sha256": sha256_hex(ORIG[5:8]), "kind": "code"}
    ]
    assert any("overlaps protected" in p for p in validate_manifest(ORIG, m))


def test_wrong_protected_hash():
    m = _base()
    m["protected_spans"] = [
        {"start_byte": 0, "end_byte": 3, "sha256": "0" * 64, "kind": "code"}
    ]
    assert any("sha256" in p for p in validate_manifest(ORIG, m))


def test_control_with_editable_ranges_rejected():
    m = _base()
    m["control"] = True
    m["editable_ranges"] = [{"start_byte": 0, "end_byte": 3}]
    assert any("control fixture" in p for p in validate_manifest(ORIG, m))


def test_missing_required_field_rejected():
    # a truncated manifest missing a gate-defining field must be FIXTURE_ERROR, not vacuous (F3)
    m = _base()
    del m["protected_spans"]
    assert any("missing required field 'protected_spans'" in p for p in validate_manifest(ORIG, m))


def test_mistyped_field_rejected():
    m = _base()
    m["editable_ranges"] = "not-a-list"
    assert any("must be list" in p for p in validate_manifest(ORIG, m))


def test_bad_encoding_rejected():
    m = _base()
    m["byte_policy"] = {"encoding": "latin-1", "trailing_newline": "preserve"}
    assert any("encoding" in p for p in validate_manifest(ORIG, m))


def test_unknown_invariant_check_rejected():
    m = _base()
    m["invariant_regions"] = [
        {"id": "r", "start_byte": 0, "end_byte": 5, "checks": ["telepathy"]}
    ]
    assert any("unknown check" in p for p in validate_manifest(ORIG, m))
