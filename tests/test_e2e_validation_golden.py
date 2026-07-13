"""#28 — live audit/suggest end-to-end validation golden (SAFETY, not just shape).

Drives the REAL command surface (`assemble.py audit` + `assemble.py run`) end-to-end — a real session
on a fixture — and asserts the full SAFETY contract, not merely output shape: a safe candidate is
ACCEPTed, and every class of UNSAFE edit is BLOCKED (invariant weakening, protected-span violation,
locality violation). The deterministic layers own these verdicts, so the golden is meaningful offline;
a `SLOPSLAP_LIVE`-gated case asserts the live semantic layer blocks a meaning-change (skipped without
a model). Complements #27's library-level seam tests by exercising the CLI on a real eval fixture.
"""
import base64
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SEAM = os.path.join(_ROOT, "scripts", "slopslap_assemble", "assemble.py")
_FIXTURE = os.path.join(_ROOT, "tests", "fixtures", "eval", "normative-spec", "original.md")

# a controlled doc whose FLAGGED (tricolon) sentence also carries a number invariant, a modality, and
# a protected inline-code span — so an in-authorized-range edit can violate each property precisely.
_DOC = (b"# Overview\n\n"
        b"The platform is fast, reliable, and scalable, serving 100 users; it must never drop a "
        b"request; see `config.yaml`.\n")


def _cli(argv):
    return subprocess.run([sys.executable, _SEAM, *argv], capture_output=True, text=True,
                          cwd=_ROOT, env={**os.environ, "SLOPSLAP_LIVE": ""})


def _edits_file(tmp_path, edits):
    ef = tmp_path / "e.json"
    ef.write_text(json.dumps([{"start_byte": s, "end_byte": e,
                               "replacement_b64": base64.b64encode(r).decode("ascii")}
                              for s, e, r in edits]))
    return str(ef)


def _run(tmp_path, doc, edits, genre="general"):
    src = tmp_path / "d.md"
    src.write_bytes(doc)
    proc = _cli(["run", "--path", str(src), "--edits", _edits_file(tmp_path, edits),
                 "--declared-genre", genre])
    return proc, src


def _stage(out, name):
    return [s for s in out["stages"] if s["stage"] == name][0]


# ---- SHAPE: a real audit of a real fixture yields a well-formed diagnosis record ----
def test_audit_fixture_shape():
    proc = _cli(["audit", "--path", _FIXTURE])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    audit = _stage(out, "audit")["data"]
    assert audit["genre"] in ("spec", "general", "prd", "personal")
    assert audit["audit_status"] in ("clean", "flagged")
    assert audit["authorization"]["state"] in ("authorized", "reject_all", "locality_unverified")
    # ledger serialized as {canonical, sha256}, protected spans found (the `429`/`Retry-After`/backticks)
    assert "sha256" in audit["ledger"] and isinstance(audit["ledger"]["canonical"], dict)
    assert len(audit["protected_spans"]) >= 1
    assert out["run_id"] and "source_sha256" in audit


# ---- SAFETY: a safe in-range invariant-preserving repair is ACCEPTed, source untouched ----
def test_safe_repair_accepted(tmp_path):
    i = _DOC.index(b"fast, reliable, and scalable")
    proc, src = _run(tmp_path, _DOC, [(i, i + len(b"fast, reliable, and scalable"), b"reliable")])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert _stage(out, "verify")["data"]["decision"] == "ACCEPT"
    assert _stage(out, "apply")["data"]["mutated"] is False           # dry-run
    assert src.read_bytes() == _DOC                                   # source untouched


# ---- SAFETY: each UNSAFE edit class is BLOCKED (the core of #28) ----
def test_number_weakening_blocked(tmp_path):
    i = _DOC.index(b"100")
    proc, _ = _run(tmp_path, _DOC, [(i, i + 3, b"999")])              # in-range, changes a number invariant
    assert proc.returncode == 2, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    v = _stage(out, "verify")["data"]
    assert v["decision"] == "REJECT" and any(f["code"] == "entry_weakened" for f in v["findings"])


def test_modality_flip_blocked(tmp_path):
    i = _DOC.index(b"must never")
    proc, _ = _run(tmp_path, _DOC, [(i, i + len(b"must never"), b"may")])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    v = _stage(json.loads(proc.stdout), "verify")["data"]
    # pin the finding code (not just REJECT) so the block can't be satisfied by an incidental
    # edit_locality if range-derivation ever degrades — self-contained like the number test (review Med)
    assert v["decision"] == "REJECT" and any(f["code"] == "entry_weakened" for f in v["findings"])


def test_protected_span_edit_blocked(tmp_path):
    i = _DOC.index(b"`config.yaml`")
    proc, _ = _run(tmp_path, _DOC, [(i, i + len(b"`config.yaml`"), b"`prod.yaml`")])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    v = _stage(json.loads(proc.stdout), "verify")["data"]
    assert v["decision"] == "REJECT" and any("protected" in f["code"] for f in v["findings"])


def test_locality_violation_blocked(tmp_path):
    i = _DOC.index(b"Overview")                                       # the heading — outside any authorized range
    proc, _ = _run(tmp_path, _DOC, [(i, i + len(b"Overview"), b"Summary!")])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    v = _stage(json.loads(proc.stdout), "verify")["data"]
    assert v["decision"] == "REJECT" and any(f["code"] == "edit_locality" for f in v["findings"])


# ---- SAFETY (live): the semantic layer blocks a meaning-change when a real model runs ----
@pytest.mark.skipif(os.environ.get("SLOPSLAP_LIVE") != "1", reason="requires a live model (SLOPSLAP_LIVE=1)")
def test_live_semantic_blocks_meaning_change(tmp_path):
    # a syntactically-safe edit that changes MEANING should be caught by the live Layer-3 semantic
    # verdict even though the deterministic layers pass. (Exercised only with a real model.)
    i = _DOC.index(b"fast, reliable, and scalable")
    src = tmp_path / "d.md"
    src.write_bytes(_DOC)
    ef = _edits_file(tmp_path, [(i, i + len(b"fast, reliable, and scalable"), b"slow and unreliable")])
    proc = subprocess.run([sys.executable, _SEAM, "run", "--path", str(src), "--edits", ef,
                           "--declared-genre", "general"], capture_output=True, text=True, cwd=_ROOT,
                          env={**os.environ, "SLOPSLAP_LIVE": "1"})
    out = json.loads(proc.stdout)
    assert _stage(out, "verify")["data"]["semantic_status"] != "clean"  # a real model flags the meaning change
    assert proc.returncode != 0
