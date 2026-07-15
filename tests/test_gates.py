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


def test_preservation_region_scoped_unit_change_fail():
    # 200 ms -> 200 s: bare number unchanged, but the UNIT changed (WF5-diff F4)
    orig, man = _load("normative-spec")
    idx = orig.find(b"no less than 200 ms")
    env, rev = make_envelope(orig, [(idx + len(b"no less than 200 "), idx + len(b"no less than 200 ms"), b"s")])
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


# --------------------------------------------------------------------------- #82 lexeme tier


def test_no_new_claim_atoms_fail_per_hard_kind():
    # #82 AC1: each HARD atom kind is individually caught, reason names the atom.
    man = {"allowed_claim_atoms": []}
    orig = b"The service handles requests."
    # (kind, revision, the atom value the evidence must NAME — adversarial F2)
    cases = [
        ("number", b"The service handles 12,000 requests.", "12000"),
        ("date", b"The service handles requests since 2024-01-15.", "2024-01-15"),
        ("url", b"The service handles requests (see https://example.com/bench).", "https://example.com/bench"),
        ("citation", b"The service handles requests [1].", "[1]"),
        ("threshold", b"The service handles requests in at most 5 ms.", "at most"),
    ]
    for kind, rev, atom in cases:
        r = G.no_new_claim_atoms(orig, rev, man)
        assert not r.passed, kind
        assert r.evidence and kind in r.evidence[0], (kind, r.evidence)
        assert any(atom in a for a in r.evidence[0][kind]), (kind, r.evidence)


def test_no_new_claim_atoms_fail_new_buzzword_named():
    # #82 AC2: a buzzword absent from the original is an introduced claim-lexeme.
    man = {"allowed_claim_atoms": []}
    orig = b"Our parser handles every supported grammar."
    rev = b"Our best-in-class parser handles every supported grammar."
    r = G.no_new_claim_atoms(orig, rev, man)
    assert not r.passed
    assert "buzzword" in r.evidence[0] and "best-in-class" in str(r.evidence[0]["buzzword"])


def test_no_new_claim_atoms_fail_new_borrowed_authority_named():
    # #82 AC2: introducing borrowed authority ("experts agree") is a new claim.
    man = {"allowed_claim_atoms": []}
    orig = b"Microservices can reduce coupling."
    rev = b"Experts agree that microservices reduce coupling."
    r = G.no_new_claim_atoms(orig, rev, man)
    assert not r.passed
    assert "borrowed_authority" in r.evidence[0]


def test_no_new_claim_atoms_pass_on_removal_and_reuse():
    # #82 AC3: removing or reusing existing claims never trips the gate.
    man = {"allowed_claim_atoms": []}
    orig = b"Our robust, best-in-class parser processes 10,000 docs/s (see https://x.io) [1]."
    rev = b"Our parser processes 10,000 docs/s (see https://x.io) [1]."
    r = G.no_new_claim_atoms(orig, rev, man)
    assert r.passed, r.reason
    reuse = b"Our best-in-class parser processes 10,000 docs/s; truly best-in-class [1] (https://x.io)."
    assert G.no_new_claim_atoms(orig, reuse, man).passed


def test_no_new_claim_atoms_lexeme_word_boundary():
    # "robustness" is not the buzzword "robust" — token-boundary match only.
    man = {"allowed_claim_atoms": []}
    orig = b"The design is sound."
    rev = b"The design favors robustness."
    assert G.no_new_claim_atoms(orig, rev, man).passed


def test_verify_blocks_buzzword_introducing_edit_end_to_end():
    # #82: the lexeme tier is live inside verify() L1 (ledger.py wiring), not just the gate fn.
    from slopslap_verification.editscript import Edit, sha256_hex
    from slopslap_verification.ledger import Ledger, verify
    orig = b"Our parser handles every supported grammar."
    led = Ledger(sha256_hex(orig))
    r = verify(orig, [Edit(0, 10, b"Our best-in-class parser")], led,
               authorized_ranges=[{"start_byte": 0, "end_byte": 10}],
               semantic_fn=None, allow_two_layer=True)
    assert r["decision"] != "ACCEPT"
    assert any(f.get("code") == "no_new_claim_atoms" for f in r["findings"])
