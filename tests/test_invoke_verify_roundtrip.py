"""Verdict + attribution round-trip through the verify() seam (#26, Task 5).

Proves the CLOSED ``invoke_semantic`` API plugs into the real 3-positional semantic seam
(``verify(original, revision, ledger_canonical)``) via ``functools.partial`` and that each
verdict + attribution shape drives the EXACT decision the ledger decision-rule specifies
(ledger.py:348-392). The "model" is a hermetic fake CLI written to tmp that emits the desired
verdict envelope — the real ``claude`` binary is never invoked.

Deterministic-layer discipline: every "all-layers-passing" case uses a whitespace-preserving
interior edit so Layer 1 (no new atoms, markdown structure, locality) and Layer 2 (literal
region normalized-text equality) both PASS — leaving the decision to Layer 3 alone.
"""

import functools
import json
import stat

from slopslap_invoke.invoke import invoke_semantic
from slopslap_verification.editscript import Edit, sha256_hex
from slopslap_verification.ledger import Ledger, LedgerEntry, verify

MODEL = "claude-test-model"


def _verdict_cli(tmp_path, result_obj, name):
    """A fake CLI that emits a success envelope whose .result is `result_obj` (verbatim)."""
    src = (
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        f"result = {json.dumps(json.dumps(result_obj))}\n"
        "sys.stdout.write(json.dumps({'type': 'result', 'result': result}))\n"
    )
    p = tmp_path / name
    p.write_text(src)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


def _sem_fn(tmp_path, result_obj, name):
    exe = _verdict_cli(tmp_path, result_obj, name)
    return functools.partial(invoke_semantic, model=MODEL, timeout_s=10.0, executable=exe)


# ---- base ledger: ONE literal entry over [0,10]; a whitespace edit keeps L1+L2 clean ----
_ORIG = b"alpha beta gamma delta epsilon zeta text here\n"
_ENTRY_RANGE = (0, 10)  # "alpha beta"


def _base_ledger():
    return Ledger(sha256_hex(_ORIG), entries=[
        LedgerEntry("e0", "literal", 0, 10, sha256_hex(_ORIG[0:10]),
                    {"text": "alpha beta"}, "byte_exact", 900)])


def _ws_edit():
    # replace the interior space (byte 5) with two spaces: bytes change, normalized text does not
    return [Edit(5, 6, b"  ")]


def _auth():
    return [{"start_byte": 0, "end_byte": len(_ORIG)}]


def _concern(**kw):
    base = {"code": "drift", "message": "meaning changed"}
    base.update(kw)
    return base


# ---- decision-table cases ----
def test_real_attributed_rejects_only_implicated_hunks(tmp_path):
    sem = _sem_fn(tmp_path, {"verdict": "real", "concerns": [
        _concern(entry_ids=["e0"],
                 original_ranges=[{"start_byte": _ENTRY_RANGE[0], "end_byte": _ENTRY_RANGE[1]}])]},
        "real_attr.py")
    r = verify(_ORIG, _ws_edit(), _base_ledger(), authorized_ranges=_auth(), semantic_fn=sem)
    assert r["decision"] == "REJECT"
    assert r["proposal_status"] == "BLOCKED"
    assert r["semantic_status"] == "real"
    h0 = next(h for h in r["hunks"] if h["hunk_id"] == "h0")
    assert h0["decision"] == "REJECT"          # implicated hunk rejected
    assert h0["revertable"] is True            # attributed -> selective rollback stays possible


def test_real_entry_ids_only_degrades_to_global_non_revertable(tmp_path):
    sem = _sem_fn(tmp_path, {"verdict": "real", "concerns": [_concern(entry_ids=["e0"])]},
                  "real_eids.py")
    r = verify(_ORIG, _ws_edit(), _base_ledger(), authorized_ranges=_auth(), semantic_fn=sem)
    assert r["decision"] == "REJECT" and r["proposal_status"] == "BLOCKED"
    assert all(h["revertable"] is False for h in r["hunks"])  # attributed-but-no-ranges => all non-revertable


def test_real_unattributed_is_reject_global(tmp_path):
    sem = _sem_fn(tmp_path, {"verdict": "real", "concerns": [_concern()]}, "real_unattr.py")
    r = verify(_ORIG, _ws_edit(), _base_ledger(), authorized_ranges=_auth(), semantic_fn=sem)
    assert r["decision"] == "REJECT" and r["proposal_status"] == "BLOCKED"
    assert any(f["disposition"] == "reject_global" for f in r["findings"])
    assert all(h["revertable"] is False for h in r["hunks"])


def test_ambiguous_surfaces(tmp_path):
    sem = _sem_fn(tmp_path, {"verdict": "ambiguous", "concerns": []}, "amb.py")
    r = verify(_ORIG, [], _base_ledger(), semantic_fn=sem)
    assert r["decision"] == "SURFACE"
    assert r["proposal_status"] == "BLOCKED"
    assert r["semantic_status"] == "ambiguous"


def test_clean_accepts_and_is_shippable(tmp_path):
    sem = _sem_fn(tmp_path, {"verdict": "clean", "concerns": []}, "clean.py")
    r = verify(_ORIG, [], _base_ledger(), semantic_fn=sem)
    assert r["decision"] == "ACCEPT"
    assert r["proposal_status"] == "ACCEPT"          # only an L3-clean proposal ships
    assert r["semantic_status"] == "clean"


def test_deterministic_hard_failure_beats_clean(tmp_path):
    # a Layer-1 hard failure (a new number atom) must REJECT regardless of a "clean" verdict.
    orig = b"the limit is 200 ms today\n"
    idx = orig.find(b"200")
    led = Ledger(sha256_hex(orig))  # no entries; L1 no_new_claim_atoms owns this
    sem = _sem_fn(tmp_path, {"verdict": "clean", "concerns": []}, "clean_hard.py")
    r = verify(orig, [Edit(idx, idx + 3, b"900")], led,
               authorized_ranges=[{"start_byte": 0, "end_byte": len(orig)}], semantic_fn=sem)
    assert r["decision"] == "REJECT"  # L1 owns hard decisions; semantic "clean" cannot lift it


def test_multibyte_content_attribution_roundtrip(tmp_path):
    # non-ASCII region: byte ranges must line up end-to-end through verify().
    head = "café résumé"
    hb = head.encode("utf-8")
    orig = head.encode("utf-8") + " señor here\n".encode("utf-8")
    end = len(hb)  # 14 bytes
    led = Ledger(sha256_hex(orig), entries=[
        LedgerEntry("e0", "literal", 0, end, sha256_hex(orig[0:end]),
                    {"text": head}, "byte_exact", 900)])
    edits = [Edit(5, 6, b"  ")]  # byte 5 is the space between café and résumé (interior)
    sem = _sem_fn(tmp_path, {"verdict": "real", "concerns": [
        _concern(entry_ids=["e0"], original_ranges=[{"start_byte": 0, "end_byte": end}])]},
        "mb_real.py")
    r = verify(orig, edits, led, authorized_ranges=[{"start_byte": 0, "end_byte": len(orig)}],
               semantic_fn=sem)
    assert r["decision"] == "REJECT" and r["semantic_status"] == "real"
    h0 = next(h for h in r["hunks"] if h["hunk_id"] == "h0")
    assert h0["decision"] == "REJECT" and h0["revertable"] is True
