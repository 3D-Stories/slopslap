"""Passage-local authorized ranges derived from scan diagnoses (#20).

``authorized_ranges_from_diagnoses(doc)`` turns the scanner's per-passage diagnosis
locations into ``[{start_byte, end_byte}]`` byte spans of the DIAGNOSED passages, so
``slopslap_verification.ledger.verify(..., authorized_ranges=<result>)`` enforces
passage-local editing deterministically on a LIVE doc — where no hand-authored
``editable_ranges`` exist and ``edit_locality`` would otherwise be only prompt-guided
(``authorized_ranges=None`` yields the ``locality_unverified`` ASK).
"""

import os

import pytest

from slopslap_scan.diagnoses import DiagnosisError, authorized_ranges_from_diagnoses
from slopslap_verification.editscript import Edit, sha256_hex
from slopslap_verification.ledger import Ledger, verify

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KUKA = os.path.join(REPO, "tests", "fixtures", "kukakuka-prd.md")


def _kuka() -> bytes:
    with open(KUKA, "rb") as fh:
        return fh.read()


def _empty_ledger(doc: bytes) -> Ledger:
    # no entries / no protected spans: isolates the edit_locality gate under test.
    return Ledger(sha256_hex(doc))


def _locality_findings(result):
    return [f for f in result["findings"]
            if f["code"] in ("edit_locality", "locality_unverified")]


def _covered(ranges, offset):
    return any(r["start_byte"] <= offset < r["end_byte"] for r in ranges)


# ---- byte-exactness + shape (real doc) -----------------------------------
def test_ranges_are_byte_exact_sorted_and_disjoint_on_real_prd():
    doc = _kuka()
    ranges = authorized_ranges_from_diagnoses(doc)
    assert ranges, "the cadence-heavy PRD must diagnose at least one passage"
    n = len(doc)
    prev_end = -1
    for r in ranges:
        assert set(r) == {"start_byte", "end_byte"}
        s, e = r["start_byte"], r["end_byte"]
        assert 0 <= s < e <= n
        # sorted and pairwise disjoint (merged/deduped)
        assert s > prev_end
        prev_end = e
        # a range slice is valid UTF-8 (byte-exact on char boundaries)
        doc[s:e].decode("utf-8")
        # start begins a source line; end sits at a line start or EOF
        assert s == 0 or doc[s - 1:s] == b"\n"
        assert e == n or doc[e - 1:e] == b"\n"


def test_covers_a_diagnosed_passage_but_not_a_clean_one():
    doc = _kuka()
    ranges = authorized_ranges_from_diagnoses(doc)
    # a negative-parallelism finding sits in the Date/Status paragraph -> its passage is covered
    diagnosed = doc.find(b"quality, not expediency")
    assert diagnosed >= 0
    assert _covered(ranges, diagnosed), "a diagnosed passage must be authorized"
    # the H1 title carries no per-passage diagnosis -> it is NOT authorized
    title = doc.find(b"# PRD")
    assert title == 0
    assert not _covered(ranges, title), "an undiagnosed passage must NOT be authorized"


# ---- end-to-end through verify (real doc) --------------------------------
def test_edit_inside_diagnosed_passage_passes_locality():
    doc = _kuka()
    ranges = authorized_ranges_from_diagnoses(doc)
    led = _empty_ledger(doc)
    s = ranges[0]["start_byte"]
    # a self-replacement (revision == original) isolates edit_locality: every other gate
    # stays green, so only the locality decision is observed.
    edit = Edit(s, s + 1, doc[s:s + 1])
    r = verify(doc, [edit], led, authorized_ranges=ranges)
    assert _locality_findings(r) == [], "an in-passage edit must not raise a locality finding"


def test_edit_outside_all_ranges_triggers_locality_reject():
    doc = _kuka()
    ranges = authorized_ranges_from_diagnoses(doc)
    led = _empty_ledger(doc)
    # first byte covered by no authorized range (a self-replacement keeps all other gates green)
    outside = next(i for i in range(len(doc)) if not _covered(ranges, i))
    edit = Edit(outside, outside + 1, doc[outside:outside + 1])
    r = verify(doc, [edit], led, authorized_ranges=ranges)
    assert any(f["code"] == "edit_locality" for f in r["findings"])
    assert r["decision"] == "REJECT"


def test_none_authorized_ranges_is_only_prompt_guided_ask():
    # the contrast: the SAME in-passage edit, but with no derived ranges, is undecidable
    # locality -> the fail-closed locality_unverified ASK (issue #17 behavior).
    doc = _kuka()
    ranges = authorized_ranges_from_diagnoses(doc)
    led = _empty_ledger(doc)
    s = ranges[0]["start_byte"]
    edit = Edit(s, s + 1, doc[s:s + 1])
    r = verify(doc, [edit], led, authorized_ranges=None)
    assert r["decision"] == "ASK"
    assert any(f["code"] == "locality_unverified" for f in r["findings"])


# ---- no-diagnoses edge ---------------------------------------------------
def test_no_diagnoses_yields_empty_ranges_and_verify_forbids_edits():
    doc = b"The cat sat on the mat.\n"
    assert authorized_ranges_from_diagnoses(doc, "text") == []
    # empty authorized set => a clean doc must be left alone: ANY edit is out of locality.
    led = _empty_ledger(doc)
    r = verify(doc, [Edit(0, 3, doc[0:3])], led, authorized_ranges=[])
    assert any(f["code"] == "edit_locality" for f in r["findings"])
    assert r["decision"] == "REJECT"


# ---- byte-not-char offsets (multibyte) -----------------------------------
def test_byte_offsets_are_bytes_not_chars_multibyte():
    # a leading multibyte paragraph pushes the flagged passage's byte offset PAST its char
    # index; a char-based deriver would authorize the wrong span.
    doc = "café\n\nThe plan is fast, not slow, and works.".encode("utf-8")
    ranges = authorized_ranges_from_diagnoses(doc, "text")
    assert len(ranges) == 1
    assert ranges[0]["start_byte"] == len("café\n\n".encode("utf-8"))  # 7 bytes, char index 6
    assert doc[ranges[0]["start_byte"]:ranges[0]["end_byte"]].decode("utf-8").startswith(
        "The plan is fast, not slow")
    # the clean leading paragraph carries no diagnosis -> not authorized
    assert not _covered(ranges, doc.find(b"caf"))


# ---- fail-loud + empty ---------------------------------------------------
def test_non_utf8_fails_loud():
    with pytest.raises(DiagnosisError):
        authorized_ranges_from_diagnoses(b"\xff\xfe not utf-8", "text")


def test_empty_doc_is_empty():
    assert authorized_ranges_from_diagnoses(b"") == []


def test_unknown_format_fails_loud():
    with pytest.raises(DiagnosisError):
        authorized_ranges_from_diagnoses(b"hello", "rtf")


def test_doc_level_only_flags_are_not_localizable():
    # [] is OVERLOADED: a doc flagged ONLY by doc-level metrics (soft_flag True but empty
    # per-passage locations) yields NO ranges — same as a clean doc — so verify rejects every
    # edit. The live orchestrator (#27) owns the doc-wide rewrite lane for such slop; this
    # deriver has no passage-local path for it (fails closed by design).
    from slopslap_scan.diagnoses import _diagnosed_line_ranges
    doc_level_only = {
        "punctuation_rates": {"soft_flag": True, "locations": []},
        "sentence_length_dispersion": {"soft_flag": True, "locations": []},
    }
    assert _diagnosed_line_ranges(doc_level_only) == []
