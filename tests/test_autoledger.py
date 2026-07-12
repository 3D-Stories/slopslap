"""Whole-doc invariant auto-extraction for arbitrary prose (#19).

build_invariant_regions(doc) replaces the hand-authored manifest ``invariant_regions``
with a real derivation over arbitrary UTF-8 prose. It emits manifest regions that feed
``ledger.build_ledger`` directly, and the ledger's own ``_CHECK_KIND`` assigns
kind/preservation/confidence per the design R3 per-kind table (never re-invented here).
"""

import pytest
from helpers import fixture_dir

from slopslap_verification.autoledger import build_invariant_regions
from slopslap_verification.editscript import Edit
from slopslap_verification.ledger import (
    LedgerBuildError,
    build_ledger,
    validate_ledger,
    verify,
)
from eval.loader import load_fixture


def _spec():
    orig, _ = load_fixture(fixture_dir("normative-spec"))
    return orig


# ---- shape + byte-exactness ----------------------------------------------
def test_regions_are_well_formed_and_in_bounds():
    orig = _spec()
    regions = build_invariant_regions(orig)
    assert regions, "auto-builder found no invariants in a normative spec"
    n = len(orig)
    for r in regions:
        assert set(r) >= {"start_byte", "end_byte", "checks"}
        assert 0 <= r["start_byte"] < r["end_byte"] <= n
        assert r["checks"], "a region must carry at least one check"


def test_first_sentence_region_has_modal_and_number_checks_at_exact_bytes():
    orig = _spec()
    regions = build_invariant_regions(orig)
    off = orig.find(b"The client MUST retry")
    assert off >= 0
    region = next(r for r in regions if r["start_byte"] <= off < r["end_byte"])
    # byte-exact: the region slice decodes to the sentence and starts on the sentence.
    assert region["start_byte"] == off
    text = orig[region["start_byte"]:region["end_byte"]].decode("utf-8")
    assert text.startswith("The client MUST retry a failed request at most 5 times.")
    assert "modality" in region["checks"]
    assert "numbers" in region["checks"] or "units" in region["checks"]


def test_byte_offsets_are_bytes_not_chars_multibyte():
    # a leading multibyte paragraph pushes the first invariant sentence's byte offset
    # PAST its char index; a char-based builder would report the wrong start.
    doc = "café\n\nThe fee MUST be 5 USD.".encode("utf-8")
    regions = build_invariant_regions(doc)
    assert len(regions) == 1
    r = regions[0]
    assert r["start_byte"] == len("café\n\n".encode("utf-8"))  # 7 bytes, char index 6
    assert doc[r["start_byte"]:r["end_byte"]].decode("utf-8") == "The fee MUST be 5 USD."
    assert "modality" in r["checks"]


# ---- feeds build_ledger; R3 kind/preservation/confidence -----------------
def test_output_feeds_build_ledger_and_validates():
    orig = _spec()
    regions = build_invariant_regions(orig)
    led = build_ledger(orig, {"invariant_regions": regions, "protected_spans": []})
    assert validate_ledger(orig, led) == []
    kinds = {e.kind for e in led.entries}
    assert "number_or_quantity" in kinds
    assert "normative_statement" in kinds


def test_cross_ref_and_defined_term_kinds_carry_r3_values():
    # a GENUINE definitional phrase (not bare markdown bold) + a URL cross-ref.
    doc = '"Foo" means the widget; see https://x.com now.'.encode("utf-8")
    regions = build_invariant_regions(doc)
    led = build_ledger(doc, {"invariant_regions": regions, "protected_spans": []})
    triples = {(e.kind, e.preservation, e.confidence) for e in led.entries}
    assert ("cross_reference", "lexically_exact", 950) in triples
    assert ("defined_term", "lexically_exact", 950) in triples


def test_markdown_bold_is_not_a_defined_term():
    # **bold** is emphasis/labels in real prose, NOT a definition: it must NOT freeze the
    # sentence lexically-exact (regression guard for the #19 review High finding).
    doc = "The **widget** provides the service to users.".encode("utf-8")
    regions = build_invariant_regions(doc)
    led = build_ledger(doc, {"invariant_regions": regions, "protected_spans": []})
    assert not any(e.kind == "defined_term" for e in led.entries)


def test_number_or_quantity_uses_r3_values():
    doc = "The limit MUST be 5 times.".encode("utf-8")
    led = build_ledger(doc, {"invariant_regions": build_invariant_regions(doc),
                             "protected_spans": []})
    numq = [e for e in led.entries if e.kind == "number_or_quantity"]
    assert numq
    assert all(e.preservation == "lexically_exact" and e.confidence == 950 for e in numq)
    norms = [e for e in led.entries if e.kind == "normative_statement"]
    assert norms and all(e.preservation == "semantic_exact" for e in norms)


def test_dates_covered_as_number_or_quantity():
    doc = "Delivery is due 2026-07-12 sharp.".encode("utf-8")
    led = build_ledger(doc, {"invariant_regions": build_invariant_regions(doc),
                             "protected_spans": []})
    assert any(e.kind == "number_or_quantity" for e in led.entries)


# ---- end-to-end: verify REJECTS a weakening edit -------------------------
def test_verify_rejects_number_change_on_auto_derived_invariant():
    orig = _spec()
    led = build_ledger(orig, {"invariant_regions": build_invariant_regions(orig),
                             "protected_spans": []})
    off = orig.find(b"at most 5 times")
    five = off + len(b"at most ")
    assert orig[five:five + 1] == b"5"
    r = verify(orig, [Edit(five, five + 1, b"9")], led, allow_two_layer=True)
    assert r["decision"] == "REJECT"


def test_verify_rejects_must_downgraded_to_should():
    orig = _spec()
    led = build_ledger(orig, {"invariant_regions": build_invariant_regions(orig),
                             "protected_spans": []})
    off = orig.find(b"MUST retry")
    r = verify(orig, [Edit(off, off + 4, b"SHOULD")], led, allow_two_layer=True)
    assert r["decision"] == "REJECT"
    # L2 modality (not just L1 claim-atoms) must be the one that catches a MUST->SHOULD.
    assert any(f["code"] == "entry_weakened" for f in r["findings"])


# ---- edge cases ----------------------------------------------------------
def test_empty_doc_is_empty():
    assert build_invariant_regions(b"") == []


def test_prose_with_no_invariants_is_empty():
    assert build_invariant_regions(b"The cat sat on the mat.") == []


def test_non_utf8_fails_loud():
    with pytest.raises(LedgerBuildError):
        build_invariant_regions(b"\xff\xfe not utf-8 here")
