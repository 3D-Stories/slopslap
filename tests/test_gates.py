"""Per-gate pass + mutation (fail) coverage — the red-before-green discrimination proof.

Each gate has a passing case and a mutation that must flip it to FAIL; a no-op gate would
fail the mutation assertion.
"""

from helpers import fixture_dir, make_envelope

from slopslap_verification import gates as G
from slopslap_verification.editscript import parse_edits
from slopslap_verification.gates import GateStatus
from eval.loader import load_fixture


def _load(name):
    return load_fixture(fixture_dir(name))


def test_edit_locality_pass_inside_range():
    orig, man = _load("distinctive-essay")
    er = man["editable_ranges"][0]
    env, _ = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Short.")])
    r = G.edit_locality(parse_edits(env["edits"]), man)
    assert r.passed


def test_edit_locality_fail_outside_range():
    orig, man = _load("distinctive-essay")
    env, _ = make_envelope(orig, [(0, 5, b"XXXXX")])
    r = G.edit_locality(parse_edits(env["edits"]), man)
    assert r.status is GateStatus.FAIL


def test_protected_span_intact_pass():
    orig, man = _load("normative-spec")
    er = man["editable_ranges"][0]
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Define a metric.")])
    r = G.protected_spans_intact(rev, parse_edits(env["edits"]), man)
    assert r.passed


def test_protected_span_mutation_fail():
    orig, man = _load("normative-spec")
    sp = man["protected_spans"][0]  # the curl code block
    env, rev = make_envelope(orig, [(sp["start_byte"], sp["end_byte"], b"    rm -rf /")])
    r = G.protected_spans_intact(rev, parse_edits(env["edits"]), man)
    assert r.status is GateStatus.FAIL


def test_preservation_region_scoped_pass_when_region_untouched():
    orig, man = _load("normative-spec")
    er = man["editable_ranges"][0]
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Is it testable?")])
    r = G.preservation_region_scoped(orig, rev, parse_edits(env["edits"]), man)
    assert r.passed


def test_preservation_region_scoped_number_change_fail():
    orig, man = _load("normative-spec")
    idx = orig.find(b"at most 5 times")
    env, rev = make_envelope(orig, [(idx + 8, idx + 9, b"9")])  # 5 -> 9 inside region
    r = G.preservation_region_scoped(orig, rev, parse_edits(env["edits"]), man)
    assert r.status is GateStatus.FAIL


def test_preservation_region_scoped_modality_change_fail():
    orig, man = _load("normative-spec")
    idx = orig.find(b"MUST NOT retry")
    env, rev = make_envelope(orig, [(idx, idx + len(b"MUST NOT"), b"MAY")])
    r = G.preservation_region_scoped(orig, rev, parse_edits(env["edits"]), man)
    assert r.status is GateStatus.FAIL


def test_no_new_claim_atoms_pass():
    orig, man = _load("underspecified-prd")
    er = man["editable_ranges"][0]
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Delivery details TBD.")])
    r = G.no_new_claim_atoms(orig, rev, man)
    assert r.passed


def test_no_new_claim_atoms_fail_invented_number():
    orig, man = _load("underspecified-prd")
    er = man["editable_ranges"][0]
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Delivery in 12 ms flat.")])
    r = G.no_new_claim_atoms(orig, rev, man)
    assert r.status is GateStatus.FAIL


def test_markdown_structure_pass_and_fail():
    orig, man = _load("distinctive-essay")
    er = man["editable_ranges"][0]
    ok_env, ok_rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Solder well.")])
    assert G.markdown_structure(orig, ok_rev).passed
    bad_env, bad_rev = make_envelope(
        orig, [(er["start_byte"], er["end_byte"], b"```py\nprint(x)")]
    )
    assert G.markdown_structure(orig, bad_rev).status is GateStatus.FAIL


def test_control_abstention_pass_and_fail():
    orig, man = _load("clean-personal")
    assert G.control_abstention(orig, orig, man).passed
    edited = orig.replace(b"does not", b"doesn't", 1)
    assert G.control_abstention(orig, edited, man).status is GateStatus.FAIL


def test_control_abstention_none_for_non_control():
    orig, man = _load("normative-spec")
    assert G.control_abstention(orig, orig, man) is None


def test_idempotence_states():
    orig, man = _load("distinctive-essay")
    assert G.idempotence(orig, None, man).status is GateStatus.NOT_EVALUATED
    assert G.idempotence(orig, orig, man).passed
    assert G.idempotence(orig, orig + b"drift", man).status is GateStatus.FAIL


def test_material_equal_trailing_newline_policy():
    assert G.material_equal(b"x", b"x\n", {"trailing_newline": "normalize"})
    assert not G.material_equal(b"x", b"x\n", {"trailing_newline": "preserve"})
