"""#29 — apply-command enablement: the seam's write path is un-fenced and reachable.

#27 fenced write=True (dry-run only until the hardening #21 landed). #21 is merged, so #29 enables
real mutation via an explicit `apply` CLI subcommand. `run` stays dry-run-only (safe default). Every
mutation is still backup-gated + verifier-gated (the #21/#27 machinery); these tests prove the write
path actually mutates on ACCEPT and stays fail-closed on block/backup-failure.
"""
import base64
import json
import os
import subprocess
import sys

from slopslap_assemble.assemble import assemble
from slopslap_apply.backup import BackupConfig

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SEAM = os.path.join(_ROOT, "scripts", "slopslap_assemble", "assemble.py")

_GOLDEN = (b"# Overview\n\n"
           b"The platform is fast, reliable, and scalable.\n\n"
           b"Our approach is simple, elegant, and powerful.\n")
_NUM = b"The platform is fast, reliable, and scalable, serving 100 users daily.\n"


def _clean(o, r, lc):
    return {"verdict": "clean", "concerns": []}


def _edits_file(tmp_path, edits):
    ef = tmp_path / "edits.json"
    ef.write_text(json.dumps([{"start_byte": s, "end_byte": e,
                               "replacement_b64": base64.b64encode(r).decode("ascii")}
                              for s, e, r in edits]))
    return ef


# ---- library: write=True actually mutates the file (fence removed) ----
def test_assemble_write_true_mutates_and_backs_up(tmp_path):
    from slopslap_verification.editscript import Edit
    src = tmp_path / "doc.md"
    src.write_bytes(_GOLDEN)
    run = assemble(str(src), [Edit(28, 32, b"quick")], declared_genre="general",
                   semantic_fn=_clean, write=True, apply_config=BackupConfig(root=str(tmp_path / "bk")))
    assert run.status == "ok", [(s.stage, s.status, s.code) for s in run.stages]
    ap = [s for s in run.stages if s.stage == "apply"][0]
    assert ap.status == "ok" and ap.data["mutated"] is True   # a REAL write, not dry-run
    assert src.read_bytes() == _GOLDEN.replace(b"fast", b"quick")   # file on disk actually changed
    assert os.path.exists(ap.data["backup"]["path"])                # backup made


# ---- library: an invariant violation still blocks even with write=True (no mutation) ----
def test_assemble_write_true_blocks_violation_no_mutation(tmp_path):
    from slopslap_verification.editscript import Edit
    src = tmp_path / "num.md"
    src.write_bytes(_NUM)
    i = _NUM.index(b"100")
    run = assemble(str(src), [Edit(i, i + 3, b"999")], declared_genre="general",
                   semantic_fn=_clean, write=True, apply_config=BackupConfig(root=str(tmp_path / "bk")))
    vstage = [s for s in run.stages if s.stage == "verify"][0]
    assert vstage.status == "blocked"
    assert src.read_bytes() == _NUM                                 # unchanged — violation blocked


# ---- library: backup failure fails closed (no mutation) even on an ACCEPT ----
def test_assemble_write_true_backup_failure_fails_closed(tmp_path):
    from slopslap_verification.editscript import Edit
    src = tmp_path / "doc.md"
    src.write_bytes(_GOLDEN)
    # a relative (non-absolute, non-".slopslap/backups") root is rejected by create_verified_backup
    run = assemble(str(src), [Edit(28, 32, b"quick")], declared_genre="general",
                   semantic_fn=_clean, write=True, apply_config=BackupConfig(root="relative_bad_root"))
    ap = [s for s in run.stages if s.stage == "apply"][0]
    assert ap.status in ("blocked", "failed") and ap.data.get("mutated") in (False, None)
    assert src.read_bytes() == _GOLDEN                              # no mutation without a backup


# ---- CLI: the `apply` subcommand performs a real write; exit 0 ----
def _cli(tmp_path, argv, doc):
    src = tmp_path / "doc.md"
    src.write_bytes(doc)
    ef = _edits_file(tmp_path, [(28, 32, b"quick")])
    proc = subprocess.run([sys.executable, _SEAM, *argv, "--path", str(src), "--edits", str(ef),
                           "--declared-genre", "general"],
                          capture_output=True, text=True, cwd=_ROOT,
                          env={**os.environ, "SLOPSLAP_LIVE": ""})
    return proc, src


def test_cli_apply_subcommand_mutates(tmp_path):
    proc, src = _cli(tmp_path, ["apply"], _GOLDEN)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    ap = [s for s in out["stages"] if s["stage"] == "apply"][0]
    assert ap["status"] == "ok" and ap["data"]["mutated"] is True
    assert src.read_bytes() == _GOLDEN.replace(b"fast", b"quick")   # real mutation via the command surface


# ---- adv-diff H1: a real write on a non-live semantic layer surfaces a deterministic-only warning ----
def test_write_true_offline_warns_deterministic_only(tmp_path):
    from slopslap_verification.editscript import Edit
    from slopslap_assemble.assemble import live_semantic_fn
    src = tmp_path / "doc.md"
    src.write_bytes(_GOLDEN)
    # live_semantic_fn() offline == the clean stub tagged semantic_mode="offline_stub"
    run = assemble(str(src), [Edit(28, 32, b"quick")], declared_genre="general",
                   semantic_fn=live_semantic_fn(), write=True,
                   apply_config=BackupConfig(root=str(tmp_path / "bk")))
    ap = [s for s in run.stages if s.stage == "apply"][0]
    assert ap.status == "ok" and ap.data["mutated"] is True
    assert any("deterministic layers only" in w.lower() for w in ap.warnings), ap.warnings


# ---- CLI: `run` stays dry-run only — never mutates, even now that apply exists ----
def test_cli_run_still_dry_run_only(tmp_path):
    proc, src = _cli(tmp_path, ["run"], _GOLDEN)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert src.read_bytes() == _GOLDEN                              # run never mutates
