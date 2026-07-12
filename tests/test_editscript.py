import pytest

from slopslap_verification.editscript import (
    Edit,
    EditError,
    MapError,
    apply_edits,
    derive_edits,
    map_offset,
    map_region,
    parse_edits,
    sha256_hex,
)


def test_apply_edits_basic_replace():
    orig = b"hello world"
    out = apply_edits(orig, [Edit(6, 11, b"there")])
    assert out == b"hello there"


def test_apply_edits_insertion():
    orig = b"ab"
    out = apply_edits(orig, [Edit(1, 1, b"X")])
    assert out == b"aXb"


def test_apply_edits_multiple_sorted_and_unsorted():
    orig = b"0123456789"
    edits = [Edit(8, 9, b"H"), Edit(1, 2, b"A")]  # out of order on purpose
    assert apply_edits(orig, edits) == b"0A234567H9"


def test_overlapping_edits_rejected():
    with pytest.raises(EditError):
        apply_edits(b"abcdef", [Edit(1, 4, b"X"), Edit(3, 5, b"Y")])


def test_out_of_bounds_rejected():
    with pytest.raises(EditError):
        apply_edits(b"abc", [Edit(2, 9, b"X")])


def test_two_insertions_same_offset_ambiguous():
    with pytest.raises(EditError):
        apply_edits(b"abc", [Edit(1, 1, b"X"), Edit(1, 1, b"Y")])


def test_parse_edits_b64_roundtrip():
    edits = parse_edits([{"start_byte": 0, "end_byte": 1, "replacement_b64": "WA=="}])
    assert edits[0].replacement == b"X"


def test_derive_edits_reconstructs():
    orig = b"the quick brown fox"
    rev = b"the slow brown cat"
    edits = derive_edits(orig, rev)
    assert apply_edits(orig, edits) == rev


def test_map_offset_after_growth():
    # replace [1,2) len1 with len3 -> everything at/after offset 2 shifts +2
    edits = [Edit(1, 2, b"XYZ")]
    assert map_offset(edits, 0) == 0
    assert map_offset(edits, 2) == 4  # 2 + (3-1)


def test_map_offset_inside_replaced_span_raises():
    edits = [Edit(2, 6, b"Z")]
    with pytest.raises(MapError):
        map_offset(edits, 4)


def test_map_region_fail_closed_on_boundary_in_edit():
    edits = [Edit(2, 6, b"Z")]
    with pytest.raises(MapError):
        map_region(edits, 4, 8)


def test_multibyte_offsets_are_byte_based():
    # em dash is 3 bytes in utf-8; offsets must be byte offsets, not codepoints
    orig = "a—b".encode("utf-8")  # 5 bytes: 61 e2 80 94 62
    assert len(orig) == 5
    out = apply_edits(orig, [Edit(4, 5, b"c")])  # replace 'b'
    assert out == "a—c".encode("utf-8")


def test_sha256_hex_stable():
    assert sha256_hex(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
