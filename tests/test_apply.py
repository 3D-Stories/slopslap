"""Backup-gated selective apply: apply-only-passing, block paths, concurrency guard."""

import base64
import os

from slopslap_apply.apply import apply_selective
from slopslap_apply.backup import BackupConfig


def _e(s, e, r):
    return {"start_byte": s, "end_byte": e, "replacement_b64": base64.b64encode(r).decode()}


ACCEPT = lambda o, ed: {"decision": "ACCEPT", "findings": [], "hunks": []}


def test_apply_happy_mutates_and_backs_up(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"one two three\n")
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, BackupConfig(root=str(tmp_path / "bk")))
    assert r["status"] == "applied" and r["mutated"] is True
    assert src.read_bytes() == b"ONE two three\n"
    assert os.path.exists(r["backup"]["path"])


def test_apply_selective_withholds_blocked_hunk(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"one two three\n")

    def vf(o, ed):
        if len(ed) >= 2:  # full set -> reject the second hunk
            return {"decision": "REJECT",
                    "findings": [{"disposition": "reject", "implicated_hunk_ids": ["h1"]}], "hunks": []}
        return {"decision": "ACCEPT", "findings": [], "hunks": []}

    r = apply_selective(str(src), [_e(0, 3, b"ONE"), _e(8, 13, b"THREE")], vf,
                        BackupConfig(root=str(tmp_path / "bk")))
    assert r["applied_hunks"] == ["h0"] and r["withheld_hunks"] == ["h1"]
    assert src.read_bytes() == b"ONE two three\n"  # only h0 applied


def test_apply_blocks_on_unattributed_finding(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"one two\n")
    vf = lambda o, ed: {"decision": "REJECT",
                        "findings": [{"disposition": "reject_global", "implicated_hunk_ids": []}], "hunks": []}
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], vf, BackupConfig(root=str(tmp_path / "bk")))
    assert r["status"] == "blocked" and r["mutated"] is False
    assert src.read_bytes() == b"one two\n"  # unchanged
    assert os.path.exists(r["backup"]["path"])  # backup still made (the net)


def test_apply_backup_failure_blocks_no_mutation(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"x\n")
    # in-tree backup in a non-repo -> backup fails -> refuse to mutate
    r = apply_selective(str(src), [_e(0, 1, b"Y")], ACCEPT, BackupConfig(root=".slopslap/backups"))
    assert r["status"] == "blocked" and r["mutated"] is False
    assert src.read_bytes() == b"x\n"


def test_apply_concurrency_guard(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"one two\n")

    def vf(o, ed):
        src.write_bytes(b"CONCURRENT\n")  # simulate a concurrent writer during verify
        return {"decision": "ACCEPT", "findings": [], "hunks": []}

    r = apply_selective(str(src), [_e(0, 3, b"ONE")], vf, BackupConfig(root=str(tmp_path / "bk")))
    assert r["status"] == "blocked"
    assert "concurrent" in " ".join(r["errors"]).lower()
    assert src.read_bytes() == b"CONCURRENT\n"  # concurrent work not clobbered


def test_apply_dry_run_does_not_write(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"one two\n")
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT,
                        BackupConfig(root=str(tmp_path / "bk")), write=False)
    assert r["status"] == "applied" and r["mutated"] is False
    assert src.read_bytes() == b"one two\n"


def test_apply_all_blocked_is_no_op_or_blocked(tmp_path):
    src = tmp_path / "d.md"
    src.write_bytes(b"one two\n")

    def vf(o, ed):
        # reject the only hunk on the full set; empty subset -> ACCEPT (original verifies)
        if ed:
            return {"decision": "REJECT",
                    "findings": [{"disposition": "reject", "implicated_hunk_ids": ["h0"]}], "hunks": []}
        return {"decision": "ACCEPT", "findings": [], "hunks": []}

    r = apply_selective(str(src), [_e(0, 3, b"ONE")], vf, BackupConfig(root=str(tmp_path / "bk")))
    assert r["status"] == "no_op" and r["mutated"] is False
    assert src.read_bytes() == b"one two\n"
