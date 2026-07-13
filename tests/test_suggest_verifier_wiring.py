"""#23 — suggest → deterministic verifier wiring (deterministic tests only; no live model).

The suggest→verifier WIRING is the #27 seam (scripts/slopslap_assemble). These tests lock the
CONTRACT #23 makes authoritative: suggest's invariant-check is the REAL deterministic verifier
(ledger.verify Layers 1+2), not a model claim. Every check here runs with an OFFLINE clean stub
(or no model at all), so ONLY the deterministic layers decide — a candidate that violates an
invariant is BLOCKED regardless of any model verdict.

Net-new only: #27's tests/test_assemble_seam.py already covers ACCEPT-clean and NUMBER-weakening
BLOCK; here we add the invariant classes the seam tests miss (modality / negation / protected-span),
verifier input construction, the CLI entry path, and the SKILL.md doc-drift guard.
"""
import base64
import json
import os
import re
import subprocess
import sys

from slopslap_verification.editscript import Edit, parse_edits, sha256_hex
from slopslap_verification.ledger import build_ledger, verify

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SEAM = os.path.join(_ROOT, "scripts", "slopslap_assemble", "assemble.py")


def _clean_stub(original, revision, ledger_canonical):
    """Offline Layer-3 stub: always clean, so Layers 1+2 are the SOLE gate (never semantic_fn=None,
    which would SURFACE-not-ACCEPT a preserving repair — ledger.py:365)."""
    return {"verdict": "clean", "concerns": []}


# --------------------------------------------------------------- verifier input construction
def test_suggest_candidate_diff_roundtrips_to_editscript():
    """A suggest candidate diff serializes to the {start_byte,end_byte,replacement_b64} the seam
    consumes and round-trips through parse_edits to the same Edit."""
    e = Edit(5, 9, b"quick")
    wire = {"start_byte": e.start_byte, "end_byte": e.end_byte,
            "replacement_b64": base64.b64encode(e.replacement).decode("ascii")}
    back = parse_edits([wire])
    assert back == [e]


# --------------------------------------------------------------- deterministic BLOCK (no model)
def _ledger_with_region(original: bytes, s: int, e: int, checks):
    return build_ledger(original, {"invariant_regions": [{"start_byte": s, "end_byte": e, "checks": checks}],
                                   "protected_spans": []})


def test_modality_weakening_is_blocked_deterministically():
    original = b"The system must reject invalid tokens.\n"
    s, e = 0, len(original) - 1  # the sentence bytes
    ledger = _ledger_with_region(original, s, e, ["modality"])
    i = original.index(b"must")
    edit = Edit(i, i + 4, b"may")  # must -> may weakens the modality invariant
    result = verify(original, [edit], ledger, authorized_ranges=[{"start_byte": s, "end_byte": e}],
                    semantic_fn=_clean_stub)
    assert result["decision"] == "REJECT"
    assert any(f["code"] == "entry_weakened" for f in result["findings"])


def test_negation_flip_is_blocked_deterministically():
    original = b"The endpoint does not accept anonymous requests.\n"
    s, e = 0, len(original) - 1
    ledger = _ledger_with_region(original, s, e, ["negation"])
    i = original.index(b" not")
    edit = Edit(i, i + 4, b"")  # drop " not" — flips the negation invariant
    result = verify(original, [edit], ledger, authorized_ranges=[{"start_byte": s, "end_byte": e}],
                    semantic_fn=_clean_stub)
    assert result["decision"] == "REJECT"
    assert any(f["code"] == "entry_weakened" for f in result["findings"])


def test_protected_span_edit_is_blocked_deterministically():
    original = b"Run `git reset --hard` to discard changes.\n"
    cs = original.index(b"`git reset --hard`")
    ce = cs + len(b"`git reset --hard`")
    manifest = {"invariant_regions": [],
                "protected_spans": [{"start_byte": cs, "end_byte": ce,
                                     "sha256": sha256_hex(original[cs:ce])}]}
    ledger = build_ledger(original, manifest)
    # edit lands INSIDE the protected span (authorized_ranges = whole doc so locality passes and the
    # protected-span violation is the sole blocker)
    edit = Edit(cs, ce, b"`git reset --soft`")
    result = verify(original, [edit], ledger,
                    authorized_ranges=[{"start_byte": 0, "end_byte": len(original)}],
                    semantic_fn=_clean_stub)
    assert result["decision"] == "REJECT"
    assert any("protected" in f["code"] for f in result["findings"])


# --------------------------------------------------------------- CLI entry path (real command surface)
def _run_cli(tmp_path, doc: bytes, edits):
    src = tmp_path / "doc.md"
    src.write_bytes(doc)
    ef = tmp_path / "edits.json"
    ef.write_text(json.dumps([{"start_byte": e.start_byte, "end_byte": e.end_byte,
                               "replacement_b64": base64.b64encode(e.replacement).decode("ascii")}
                              for e in edits]))
    proc = subprocess.run([sys.executable, _SEAM, "run", "--path", str(src),
                           "--edits", str(ef), "--dry-run", "--declared-genre", "general"],
                          capture_output=True, text=True, cwd=_ROOT,
                          env={**os.environ, "SLOPSLAP_LIVE": ""})  # offline stub; general = no cadence suppression
    return proc


# tricolon-flagged docs (authorized ranges), reusing #27's proven-in-range content so the CLI test
# exercises the entry path without re-deriving diagnoses byte offsets by hand.
_GOLDEN_DOC = (b"# Overview\n\n"
               b"The platform is fast, reliable, and scalable.\n\n"
               b"Our approach is simple, elegant, and powerful.\n")
_NUM_DOC = b"The platform is fast, reliable, and scalable, serving 100 users daily.\n"


def test_cli_preserving_edit_exits_0(tmp_path):
    proc = _run_cli(tmp_path, _GOLDEN_DOC, [Edit(28, 32, b"quick")])  # "fast"->"quick", in an authorized range
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok" and out["semantic_mode"] == "offline_stub"
    assert (tmp_path / "doc.md").read_bytes() == _GOLDEN_DOC  # source untouched (dry-run)


def test_cli_invariant_violation_exits_2(tmp_path):
    i = _NUM_DOC.index(b"100")
    proc = _run_cli(tmp_path, _NUM_DOC, [Edit(i, i + 3, b"999")])  # weakens the number invariant
    assert proc.returncode == 2, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    vstage = [s for s in out["stages"] if s["stage"] == "verify"][0]
    assert vstage["status"] == "blocked" and vstage["code"] == "verify_not_shippable"


# --------------------------------------------------------------- doc-drift guard (red -> green)
def _suggest_mode_block() -> str:
    """The single canonical suggest-mode bullet in SKILL.md (anchored, not a corpus-wide scan)."""
    text = open(os.path.join(_ROOT, "skills", "slopslap", "SKILL.md"), encoding="utf-8").read()
    m = re.search(r"- \*\*suggest \(default\)\*\*.*?(?=\n<!-- anchor:|\n- \*\*apply)", text, re.S)
    assert m, "could not locate the suggest-mode bullet in SKILL.md"
    return m.group(0)


def test_skill_suggest_mode_not_model_reported():
    """#23 retires the model-reported claim: the suggest invariant-check is the deterministic verifier."""
    block = _suggest_mode_block()
    assert "model-reported" not in block, "SKILL.md suggest mode still calls the invariant-check model-reported"
