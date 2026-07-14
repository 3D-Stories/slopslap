"""Prompt-injection / adversarial-model resistance (#31, residual #26 hardening).

The trust boundary is: a Layer-3 semantic model (or any config/CLAUDE.md loaded into it) is
UNTRUSTED. It can be coerced to say "clean", to forge an attribution range, or to answer as a
different model. These tests assert the deterministic core cannot be talked out of a verdict:

  31a  neutrality clause pins the verifier to faithfulness (no voice/style bias) — drift guard
  31c  contract._validate rejects a range that doesn't belong to its paired entry_id
  31d  normalize_semantic + verify reject an INVENTED attribution range (fail to ambiguous)
  31e  _model_confirmed drops the loose substring match (a distinct id containing the alias)

Cross-cutting: a coerced "clean" from Layer 3 can NEVER override a Layer-1/Layer-2 hard REJECT,
and no garbled/forged model output is ever read as "clean".
"""

import json

from eval.loader import load_fixture
from helpers import fixture_dir

from slopslap_invoke.contract import _INSTRUCTION, build_request, parse_response
from slopslap_invoke.invoke import _model_confirmed
from slopslap_verification.editscript import Edit, sha256_hex
from slopslap_verification.ledger import Ledger, LedgerEntry, build_ledger, normalize_semantic, verify


def _spec():
    orig, man = load_fixture(fixture_dir("normative-spec"))
    return orig, man, build_ledger(orig, man)


_CLEAN = lambda o, rev, l: {"verdict": "clean", "concerns": []}  # a coerced/compromised "clean"


# ---- coerced-clean can NEVER override a deterministic hard reject (the core #26 threat) ----
def test_coerced_clean_cannot_override_layer1_protected_span():
    orig, man, led = _spec()
    sp = man["protected_spans"][0]
    r = verify(orig, [Edit(sp["start_byte"], sp["end_byte"], b"    rm -rf /")], led,
               semantic_fn=_CLEAN, allow_two_layer=True)
    assert r["decision"] == "REJECT"                       # L1 owns it; L3 "clean" is ignored
    assert any(f["layer"] == 1 for f in r["findings"])
    assert r["proposal_status"] == "BLOCKED"


def test_coerced_clean_cannot_override_layer2_entry_drop():
    orig = b"the client MUST wait 200 ms here.\n"
    led = Ledger(sha256_hex(orig), entries=[
        LedgerEntry("e0", "number_or_quantity", 21, 27, sha256_hex(orig[21:27]),
                    {"200|ms": 1}, "lexically_exact", 950)])
    r = verify(orig, [Edit(0, len(orig), b"gone\n")], led, semantic_fn=_CLEAN, allow_two_layer=True)
    assert r["decision"] == "REJECT"                       # deleted ledger entry; clean cannot rescue
    assert any(f["code"] == "entry_dropped" for f in r["findings"])


def test_coerced_clean_cannot_override_number_change():
    orig, _, led = _spec()
    idx = orig.find(b"at most 5 times")
    r = verify(orig, [Edit(idx + 8, idx + 9, b"9")], led, semantic_fn=_CLEAN, allow_two_layer=True)
    assert r["decision"] == "REJECT"                       # 5 -> 9 tripped a hard gate


# ---- 31d: an INVENTED attribution range fails to ambiguous, never clean ----
def test_normalize_rejects_invented_range():
    out = {"verdict": "clean", "concerns": [
        {"code": "c", "message": "m", "original_ranges": [{"start_byte": 999, "end_byte": 1000}]}]}
    got = normalize_semantic(out, valid_ranges={(0, 6)})
    assert got["verdict"] == "ambiguous" and "invented" in got.get("note", "")


def test_normalize_accepts_ledger_range():
    out = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "original_ranges": [{"start_byte": 0, "end_byte": 6}]}]}
    got = normalize_semantic(out, valid_ranges={(0, 6)})
    assert got["verdict"] == "real" and got["concerns"][0]["original_ranges"] == [{"start_byte": 0, "end_byte": 6}]


def test_verify_semantic_cannot_smuggle_invented_range():
    # a model claiming a REAL violation attributed to a fabricated range must not be trusted as-is:
    # normalize downgrades the whole verdict to ambiguous (surfaces, never a bogus attributed reject).
    orig, _, led = _spec()
    bad = lambda o, rev, l: {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "original_ranges": [{"start_byte": 100000, "end_byte": 100001}]}]}
    r = verify(orig, [], led, semantic_fn=bad)
    assert r["semantic_status"] == "ambiguous" and r["decision"] == "SURFACE"


# ---- 31c/contract: forged model responses fail CLOSED to ambiguous, never clean ----
def _canon(entries):
    return {"entries": [{"id": i, "kind": "literal", "source": {"start_byte": s, "end_byte": e}}
                        for i, s, e in entries]}


def _envelope(obj):
    return json.dumps({"type": "result", "result": obj})  # CLI --output-format json envelope


def test_contract_bad_verdict_fails_closed():
    canon = _canon([("a", 0, 6)])
    r = parse_response(_envelope({"verdict": "definitely_clean", "concerns": []}), canon)
    assert r == {"verdict": "ambiguous", "concerns": []}


def test_contract_invented_range_fails_closed():
    canon = _canon([("a", 0, 6)])
    obj = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "original_ranges": [{"start_byte": 50, "end_byte": 60}]}]}
    assert parse_response(_envelope(obj), canon) == {"verdict": "ambiguous", "concerns": []}


def test_contract_range_not_belonging_to_paired_entry_fails_closed():
    # 31c: entry "a" occupies (0,6); the concern pairs id "a" with (6,12) — b's range. Mis-attribution.
    canon = _canon([("a", 0, 6), ("b", 6, 12)])
    obj = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "entry_ids": ["a"],
         "original_ranges": [{"start_byte": 6, "end_byte": 12}]}]}
    assert parse_response(_envelope(obj), canon) == {"verdict": "ambiguous", "concerns": []}


def test_contract_unhashable_entry_id_does_not_raise():
    # 31c regression (reviewer-found): a nested/unhashable element in entry_ids must NOT raise
    # TypeError out of parse_response — the "never raises on model output" contract. It fails closed
    # to a normalized dict (the garbage id is stringified; the valid range keeps the concern).
    canon = _canon([("a", 0, 6)])
    obj = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "entry_ids": [{"nested": 1}],
         "original_ranges": [{"start_byte": 0, "end_byte": 6}]}]}
    r = parse_response(_envelope(obj), canon)  # must not raise
    assert r["verdict"] == "real" and r["concerns"][0]["entry_ids"] == ["{'nested': 1}"]


def test_normalize_mispaired_real_range_is_ambiguous():
    # 31c PARITY on the straight-wired path: entry "a"=(0,6) paired with entry "b"'s range (6,12)
    # is a mis-attribution — normalize_semantic now catches it (was contract-adapter-only before).
    out = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "entry_ids": ["a"], "original_ranges": [{"start_byte": 6, "end_byte": 12}]}]}
    got = normalize_semantic(out, valid_ranges={(0, 6), (6, 12)}, id_to_range={"a": (0, 6), "b": (6, 12)})
    assert got["verdict"] == "ambiguous" and "paired" in got.get("note", "")


def test_normalize_matching_pair_kept():
    out = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "entry_ids": ["a"], "original_ranges": [{"start_byte": 0, "end_byte": 6}]}]}
    got = normalize_semantic(out, valid_ranges={(0, 6), (6, 12)}, id_to_range={"a": (0, 6), "b": (6, 12)})
    assert got["verdict"] == "real"


def test_normalize_unhashable_entry_id_does_not_raise():
    # the same stringify-first guard on the straight-wired path
    out = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "entry_ids": [{"x": 1}], "original_ranges": [{"start_byte": 0, "end_byte": 6}]}]}
    got = normalize_semantic(out, valid_ranges={(0, 6)}, id_to_range={"a": (0, 6)})  # must not raise
    assert got["verdict"] == "real" and got["concerns"][0]["entry_ids"] == ["{'x': 1}"]


def test_contract_matching_paired_range_is_kept():
    canon = _canon([("a", 0, 6), ("b", 6, 12)])
    obj = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "entry_ids": ["a"],
         "original_ranges": [{"start_byte": 0, "end_byte": 6}]}]}
    r = parse_response(_envelope(obj), canon)
    assert r["verdict"] == "real" and r["concerns"][0]["entry_ids"] == ["a"]


def test_contract_garbled_output_is_ambiguous_never_clean():
    canon = _canon([("a", 0, 6)])
    assert parse_response("not json at all", canon) == {"verdict": "ambiguous", "concerns": []}
    assert parse_response(_envelope("still not an object"), canon) == {"verdict": "ambiguous", "concerns": []}
    assert parse_response(json.dumps({"no_result_key": 1}), canon) == {"verdict": "ambiguous", "concerns": []}


# ---- 31e: _model_confirmed no longer confirms on a loose substring ----
def test_model_confirmed_rejects_substring_only_match():
    assert _model_confirmed("opus", ["claude-opusx-9"]) is False   # "opus" is a substring, not a token
    assert _model_confirmed("son", ["claude-sonnet-5"]) is False    # partial token
    assert _model_confirmed("net", ["claude-sonnet-5"]) is False


def test_model_confirmed_accepts_token_and_exact():
    assert _model_confirmed("sonnet", ["claude-sonnet-5"]) is True
    assert _model_confirmed("opus", ["claude_opus_5"]) is True       # underscore-delimited token
    assert _model_confirmed("claude-sonnet-5", ["claude-sonnet-5"]) is True  # exact


def test_model_confirmed_empty_reported_fails_closed():
    assert _model_confirmed("sonnet", []) is False


# ---- 31a: neutrality clause pinned (a compromised CLAUDE.md/config must not bias the verdict) ----
def test_instruction_carries_neutrality_clause():
    low = _INSTRUCTION.lower()
    assert "neutral" in low and "disregard" in low
    assert "claude.md" in low or "configuration" in low
    # and it survives serialization into the request payload
    req = build_request(b"hello world", "hello there", {"entries": []})
    assert "DISREGARD" in req
