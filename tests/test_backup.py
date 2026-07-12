"""Mandatory pre-mutation backup: verified copy, private perms, containment, retention."""

import os
import stat
import subprocess

import pytest

from slopslap_apply.backup import BackupConfig, BackupError, create_verified_backup


def test_backup_creates_verified_private_copy(tmp_path):
    src = tmp_path / "doc.md"
    src.write_bytes(b"hello world\n")
    rec = create_verified_backup(str(src), b"hello world\n", BackupConfig(root=str(tmp_path / "bk")))
    assert os.path.exists(rec.path)
    assert open(rec.path, "rb").read() == b"hello world\n"
    assert os.path.exists(rec.metadata_path)
    assert rec.restore_command.startswith("cp -- ")
    assert rec.containment == "external"
    assert stat.S_IMODE(os.stat(rec.path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.dirname(rec.path)).st_mode) == 0o700
    assert any("fsync skipped" in w for w in rec.warnings)  # opt-in durability surfaced


def test_relative_external_root_rejected(tmp_path):
    with pytest.raises(BackupError):
        create_verified_backup(str(tmp_path / "d.md"), b"x", BackupConfig(root="relative/path"))


def test_world_writable_backup_dir_rejected(tmp_path):
    d = tmp_path / "bk"
    d.mkdir()
    os.chmod(d, 0o777)
    with pytest.raises(BackupError):
        create_verified_backup(str(tmp_path / "d.md"), b"x", BackupConfig(root=str(d)))


def test_retention_keeps_last_n(tmp_path):
    root = str(tmp_path / "bk")
    src = str(tmp_path / "doc.md")
    for i in range(5):
        create_verified_backup(src, f"v{i}\n".encode(), BackupConfig(root=root, keep=2))
    baks = [f for f in os.listdir(root) if f.endswith(".bak")]
    assert len(baks) == 2


def test_in_tree_fails_closed_outside_repo(tmp_path):
    # tmp is not a git repo -> in-tree containment can't be verified -> fail closed
    with pytest.raises(BackupError):
        create_verified_backup(str(tmp_path / "d.md"), b"x", BackupConfig(root=".slopslap/backups"))


def test_in_tree_fails_closed_when_not_ignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    src = repo / "doc.md"
    src.write_bytes(b"hi\n")
    # no .gitignore rule for .slopslap/backups -> not ignored -> fail closed
    with pytest.raises(BackupError):
        create_verified_backup(str(src), b"hi\n", BackupConfig(root=".slopslap/backups"))


def test_in_tree_succeeds_with_gitignore(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("/.slopslap/backups/\n")
    src = repo / "doc.md"
    src.write_bytes(b"hi\n")
    rec = create_verified_backup(str(src), b"hi\n", BackupConfig(root=".slopslap/backups"))
    assert rec.containment == "in_tree"
    assert os.path.exists(rec.path)
    # the backup must not be a tracked file
    r = subprocess.run(["git", "check-ignore", "-q", "--", os.path.relpath(rec.path, repo)], cwd=repo)
    assert r.returncode == 0
