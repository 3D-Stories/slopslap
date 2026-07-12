"""Protected-span auto-extractor (#18) — extract protected_spans[] from arbitrary input.

Reuses the scan tokenizer (markdown-it + the extract.py URL matchers) to emit byte-exact,
non-overlapping protected spans (code fences, inline code, URLs/link destinations,
blockquotes, identifiers). Tests run over REAL docs (the eval fixtures + kukakuka-prd) and
prove the output plugs straight into build_ledger -> verify so a bad edit inside a protected
span REJECTS.
"""

import os

from slopslap_scan.protected import extract_protected_spans
from slopslap_verification.editscript import Edit, sha256_hex
from slopslap_verification.ledger import build_ledger, verify

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(REPO, "tests", "fixtures")
NORMATIVE = os.path.join(FIX, "eval", "normative-spec", "original.md")
KUKAKUKA = os.path.join(FIX, "kukakuka-prd.md")


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _by_bounds(spans):
    return {(s["start_byte"], s["end_byte"]): s["kind"] for s in spans}


# ---- real-doc byte ranges -------------------------------------------------
def test_reproduces_hand_authored_fixture_spans():
    """The hand-authored normative-spec protected spans must fall out of auto-extraction at
    the SAME byte ranges: the indented code block and the `Retry-After` identifier."""
    doc = _read(NORMATIVE)
    spans = extract_protected_spans(doc)
    bounds = _by_bounds(spans)
    # indented code block: hand-authored kind "code" at [492, 562)
    assert bounds.get((492, 562)) == "code"
    assert doc[492:562].startswith(b"    curl -sS")
    # inline-code identifier `Retry-After` at [215, 228)
    assert bounds.get((215, 228)) == "identifier"
    assert doc[215:228] == b"`Retry-After`"


def test_kukakuka_wehewehe_url_present():
    """The URL the eval ledger protects by hand (wehewehe.org) is auto-extracted as kind url."""
    doc = _read(KUKAKUKA)
    ui = doc.find(b"wehewehe.org")
    assert ui >= 0
    bounds = _by_bounds(extract_protected_spans(doc))
    assert bounds.get((ui, ui + len(b"wehewehe.org"))) == "url"


def test_all_kinds_at_exact_byte_ranges():
    doc = (
        "# Doc\n\n"
        "Prose with `inline code` and an `ident_x` token.\n\n"
        "See [label](https://ex.example/p) and bare https://bare.example/q here.\n\n"
        "> a quoted line here\n\n"
        "```\nfenced = 1\n```\n"
    ).encode("utf-8")
    bounds = _by_bounds(extract_protected_spans(doc))

    def span_of(sub):
        i = doc.find(sub)
        assert i >= 0, sub
        return (i, i + len(sub))

    assert bounds.get(span_of(b"`inline code`")) == "inline_code"   # has whitespace
    assert bounds.get(span_of(b"`ident_x`")) == "identifier"        # single token
    assert bounds.get(span_of(b"https://ex.example/p")) == "url"    # link destination
    assert bounds.get(span_of(b"https://bare.example/q")) == "url"  # bare URL
    assert bounds.get(span_of(b"```\nfenced = 1\n```")) == "code"   # fenced block
    # blockquote span covers the quoted line
    bq = [(s, e) for (s, e), k in bounds.items() if k == "blockquote"]
    assert bq and doc[bq[0][0]:bq[0][1]] == b"> a quoted line here"


# ---- hashing convention ---------------------------------------------------
def test_sha256_matches_span_bytes():
    for path in (NORMATIVE, KUKAKUKA):
        doc = _read(path)
        for s in extract_protected_spans(doc):
            assert s["sha256"] == sha256_hex(doc[s["start_byte"]:s["end_byte"]])
            assert set(s) == {"start_byte", "end_byte", "sha256", "kind"}


# ---- invariants: non-overlap, in-bounds -----------------------------------
def test_spans_non_overlapping_and_in_bounds():
    doc = _read(KUKAKUKA)
    spans = sorted(extract_protected_spans(doc), key=lambda s: (s["start_byte"], s["end_byte"]))
    n = len(doc)
    for s in spans:
        assert 0 <= s["start_byte"] < s["end_byte"] <= n
    for a, b in zip(spans, spans[1:]):
        assert a["end_byte"] <= b["start_byte"], (a, b)


# ---- edge cases -----------------------------------------------------------
def test_empty_doc():
    assert extract_protected_spans(b"") == []


def test_doc_with_no_protected_spans():
    assert extract_protected_spans(b"Just plain prose, nothing to protect here.\n") == []


def test_multibyte_offsets_are_bytes_not_chars():
    # "Café " is 6 bytes / 5 chars; the identifier's byte start must exceed its char index.
    doc = "Café id `naïve_id` and https://münchen.example/ü path.\n".encode("utf-8")
    spans = extract_protected_spans(doc)
    bounds = _by_bounds(spans)
    ident = doc.find(b"`na")  # byte offset of the inline-code start
    assert bounds.get((ident, ident + len(b"`na\xc3\xafve_id`"))) == "identifier"
    text = doc.decode("utf-8")
    char_idx = text.index("`na")
    assert ident != char_idx  # byte offset diverged from char offset (multibyte prefix)
    # every span round-trips through its byte range
    assert all(s["sha256"] == sha256_hex(doc[s["start_byte"]:s["end_byte"]]) for s in spans)


# ---- the point: output feeds build_ledger and verify honors it ------------
def test_feeds_build_ledger_then_verify_rejects_bad_edit():
    doc = _read(NORMATIVE)
    spans = extract_protected_spans(doc)
    ledger = build_ledger(doc, {"protected_spans": spans, "invariant_regions": []})
    assert len(ledger.protected_spans) == len(spans)

    # a bad edit strictly inside the protected `Retry-After` identifier must REJECT
    rid = next(s for s in spans if doc[s["start_byte"]:s["end_byte"]] == b"`Retry-After`")
    bad = verify(doc, [Edit(rid["start_byte"] + 1, rid["end_byte"] - 1, b"Retry-Before")],
                 ledger, allow_two_layer=True)
    assert bad["decision"] == "REJECT"

    # a bad edit inside the protected code block must also REJECT
    cid = next(s for s in spans if s["kind"] == "code")
    bad2 = verify(doc, [Edit(cid["start_byte"] + 4, cid["start_byte"] + 8, b"wget")],
                  ledger, allow_two_layer=True)
    assert bad2["decision"] == "REJECT"

    # a no-op (no edits) is not rejected on protected-span grounds
    clean = verify(doc, [], ledger, allow_two_layer=True)
    assert clean["decision"] == "ACCEPT"
