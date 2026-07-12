from helpers import fixture_dir

from slopslap_verification.editscript import Edit, sha256_hex
from slopslap_verification.ledger import (
    Ledger,
    LedgerEntry,
    ProtectedSpanRec,
    build_ledger,
    validate_ledger,
    verify,
)
from eval.loader import load_fixture


def _spec():
    orig, man = load_fixture(fixture_dir("normative-spec"))
    return orig, man, build_ledger(orig, man)


# ---- build + validate ----
def test_build_ledger_derives_entries_and_spans():
    orig, man, led = _spec()
    kinds = {e.kind for e in led.entries}
    assert "number_or_quantity" in kinds and "normative_statement" in kinds
    assert len(led.protected_spans) == 2
    assert validate_ledger(orig, led) == []


def test_ledger_entries_may_overlap():
    orig = b"0123456789"
    led = Ledger(source_sha256=sha256_hex(orig), entries=[
        LedgerEntry("a", "literal", 0, 6, sha256_hex(orig[0:6]), {"text": "012345"}, "byte_exact", 900),
        LedgerEntry("b", "literal", 2, 8, sha256_hex(orig[2:8]), {"text": "234567"}, "byte_exact", 900),
    ])
    assert validate_ledger(orig, led) == []  # overlapping ENTRIES are legal


def test_validate_catches_duplicate_id():
    orig = b"abcdef"
    led = Ledger(source_sha256=sha256_hex(orig), entries=[
        LedgerEntry("x", "literal", 0, 3, sha256_hex(orig[0:3]), {}, "byte_exact", 1),
        LedgerEntry("x", "literal", 3, 6, sha256_hex(orig[3:6]), {}, "byte_exact", 1),
    ])
    assert any("duplicate id" in p for p in validate_ledger(orig, led))


def test_validate_catches_bad_hash_and_enum_and_conf():
    orig = b"abcdef"
    led = Ledger(source_sha256=sha256_hex(orig), entries=[
        LedgerEntry("x", "not_a_kind", 0, 3, "0" * 64, {}, "byte_exact", 5000),
    ])
    probs = validate_ledger(orig, led)
    assert any("bad kind" in p for p in probs)
    assert any("text_hash" in p for p in probs)
    assert any("confidence" in p for p in probs)


def test_validate_catches_protected_span_overlap():
    orig = b"0123456789"
    led = Ledger(source_sha256=sha256_hex(orig), protected_spans=[
        ProtectedSpanRec("p0", 0, 5, sha256_hex(orig[0:5])),
        ProtectedSpanRec("p1", 3, 8, sha256_hex(orig[3:8])),
    ])
    assert any("protected_spans overlap" in p for p in validate_ledger(orig, led))


def test_validate_catches_wrong_source_sha():
    orig = b"abc"
    led = Ledger(source_sha256="0" * 64)
    assert any("source_sha256" in p for p in validate_ledger(orig, led))


# ---- canonical serialization ----
def test_canonical_serialization_vector():
    led = Ledger(source_sha256="ab", entries=[
        LedgerEntry("e0", "literal", 0, 3, "hh", {"text": "abc"}, "byte_exact", 1000)])
    expected = (
        '{"entries":[{"confidence":1000,"extracted":{"text":"abc"},"id":"e0","kind":"literal",'
        '"preservation":"byte_exact","source":{"end_byte":3,"start_byte":0,"text_hash":"hh"}}],'
        '"protected_spans":[],"schema_version":1,"source_sha256":"ab"}'
    )
    assert led.canonical_bytes().decode() == expected
    assert led.ledger_sha256() == sha256_hex(expected.encode())


def test_ledger_sha256_is_order_independent():
    orig = b"0123456789"
    e1 = LedgerEntry("a", "literal", 0, 3, sha256_hex(orig[0:3]), {}, "byte_exact", 1)
    e2 = LedgerEntry("b", "literal", 5, 8, sha256_hex(orig[5:8]), {}, "byte_exact", 1)
    a = Ledger(sha256_hex(orig), entries=[e1, e2])
    b = Ledger(sha256_hex(orig), entries=[e2, e1])
    assert a.ledger_sha256() == b.ledger_sha256()


# ---- verify decision matrix ----
def test_two_layer_accept_is_not_shippable():
    orig, _, led = _spec()
    r = verify(orig, [], led, allow_two_layer=True)
    # decision ACCEPT for tests, but NOT shippable without Layer 3 (WF5-diff H5)
    assert r["decision"] == "ACCEPT"
    assert r["proposal_status"] == "BLOCKED" and r["semantic_status"] == "not_run"


def test_only_l3_clean_is_shippable():
    orig, _, led = _spec()
    r = verify(orig, [], led, semantic_fn=lambda o, rev, l: {"verdict": "clean", "concerns": []})
    assert r["decision"] == "ACCEPT" and r["proposal_status"] == "ACCEPT"


def test_no_edit_without_l3_is_surface_not_ship():
    orig, _, led = _spec()
    r = verify(orig, [], led)  # no semantic, no allow_two_layer
    assert r["decision"] == "SURFACE" and r["proposal_status"] == "BLOCKED"


def test_number_change_rejects():
    orig, _, led = _spec()
    idx = orig.find(b"at most 5 times")
    r = verify(orig, [Edit(idx + 8, idx + 9, b"9")], led, allow_two_layer=True)
    assert r["decision"] == "REJECT"
    assert any(f["code"] in ("entry_weakened", "no_new_claim_atoms") for f in r["findings"])


def test_protected_span_mutation_rejects_layer1():
    orig, man, led = _spec()
    sp = man["protected_spans"][0]
    r = verify(orig, [Edit(sp["start_byte"], sp["end_byte"], b"    rm -rf /")], led, allow_two_layer=True)
    assert r["decision"] == "REJECT"
    assert any(f["layer"] == 1 for f in r["findings"])


def test_deleted_entry_region_rejects_layer2():
    orig = b"the client MUST wait 200 ms here.\n"
    led = Ledger(sha256_hex(orig), entries=[
        LedgerEntry("e0", "number_or_quantity", 21, 27, sha256_hex(orig[21:27]),
                    {"200|ms": 1}, "lexically_exact", 950)])
    # this hash/extracted is illustrative; assert against actual bytes
    led.entries[0].text_hash = sha256_hex(orig[21:27])
    r = verify(orig, [Edit(0, len(orig), b"gone\n")], led, allow_two_layer=True)
    assert r["decision"] == "REJECT"
    assert any(f["code"] == "entry_dropped" for f in r["findings"])


def test_unsupported_kind_is_ask():
    orig = b"alpha beta gamma delta epsilon text here"
    led = Ledger(sha256_hex(orig), entries=[
        LedgerEntry("e0", "causal_claim", 0, 10, sha256_hex(orig[0:10]), {}, "relationship_exact", 700)])
    r = verify(orig, [Edit(2, 4, b"XY")], led)  # modified region, no L2 rule -> ASK
    assert r["decision"] == "ASK"
    assert any(f["code"] == "entry_no_rule" for f in r["findings"])


def test_l3_clean_accepts_real_rejects_ambiguous_surfaces():
    orig, _, led = _spec()
    clean = verify(orig, [], led, semantic_fn=lambda o, rev, l: {"verdict": "clean", "concerns": []})
    assert clean["decision"] == "ACCEPT" and clean["semantic_status"] == "clean"
    real = verify(orig, [], led, semantic_fn=lambda o, rev, l: {
        "verdict": "real", "concerns": [{"code": "c", "message": "m", "entry_ids": ["e0_numbers"]}]})
    assert real["decision"] == "REJECT"
    amb = verify(orig, [], led, semantic_fn=lambda o, rev, l: {"verdict": "ambiguous", "concerns": []})
    assert amb["decision"] == "SURFACE"


def test_l3_exception_is_ambiguous_never_clean():
    orig, _, led = _spec()
    def boom(o, rev, l):
        raise RuntimeError("model down")
    r = verify(orig, [], led, semantic_fn=boom)
    assert r["semantic_status"] == "ambiguous" and r["decision"] == "SURFACE"


def test_unattributed_real_makes_all_hunks_non_revertable():
    orig, _, led = _spec()
    er = load_fixture(fixture_dir("normative-spec"))[1]["editable_ranges"][0]
    edits = [Edit(er["start_byte"], er["end_byte"], b"Is that testable?")]
    r = verify(orig, edits, led, semantic_fn=lambda o, rev, l: {
        "verdict": "real", "concerns": [{"code": "c", "message": "global"}]})  # no attribution
    assert r["decision"] == "REJECT"
    assert all(h["revertable"] is False for h in r["hunks"])


def test_invalid_ledger_rejects():
    orig = b"abc"
    led = Ledger("0" * 64)  # wrong source sha
    r = verify(orig, [], led)
    assert r["decision"] == "REJECT"
    assert any(f["code"] == "invalid_ledger" for f in r["findings"])


def test_build_ledger_rejects_unknown_check():
    import pytest

    from slopslap_verification.ledger import LedgerBuildError

    orig = b"the client MUST wait 200 ms here.\n"
    man = {"invariant_regions": [{"start_byte": 0, "end_byte": 10, "checks": ["telepathy"]}],
           "protected_spans": []}
    with pytest.raises(LedgerBuildError):
        build_ledger(orig, man)


def test_build_ledger_rejects_empty_checks():
    import pytest

    from slopslap_verification.ledger import LedgerBuildError

    orig = b"abcdefghij"
    man = {"invariant_regions": [{"start_byte": 0, "end_byte": 5, "checks": []}], "protected_spans": []}
    with pytest.raises(LedgerBuildError):
        build_ledger(orig, man)


def test_locality_unverified_is_ask_when_edits_without_authorized_ranges():
    orig = b"alpha beta gamma delta epsilon zeta text"
    led = Ledger(sha256_hex(orig))  # no entries, no protected spans
    r = verify(orig, [Edit(0, 5, b"ALPHA")], led)  # edits but no authorized_ranges
    assert r["decision"] == "ASK"
    assert any(f["code"] == "locality_unverified" for f in r["findings"])


def test_malformed_semantic_concern_is_ambiguous_not_crash():
    orig, _, led = _spec()
    # a concern that is a string, not a dict — must not crash; must map to ambiguous
    r = verify(orig, [], led, semantic_fn=lambda o, rev, l: {"verdict": "real", "concerns": ["boom"]})
    assert r["semantic_status"] == "ambiguous" and r["decision"] == "SURFACE"


def test_ask_finding_marks_hunk_ask():
    # an entry with no L2 rule + an edit in its region -> ASK, and the hunk decision folds to ASK
    orig = b"alpha beta gamma delta epsilon zeta eta theta text here"
    led = Ledger(sha256_hex(orig), entries=[
        LedgerEntry("e0", "causal_claim", 0, 20, sha256_hex(orig[0:20]), {}, "relationship_exact", 700)])
    r = verify(orig, [Edit(2, 4, b"XY")], led, authorized_ranges=[{"start_byte": 0, "end_byte": 20}])
    assert r["decision"] == "ASK"
    assert any(h["decision"] == "ASK" for h in r["hunks"])
