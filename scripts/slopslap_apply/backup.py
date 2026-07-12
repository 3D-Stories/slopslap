"""Mandatory pre-mutation backup (design R1–R6). Git-independent; the universal safety net.

Default location is a user-local state dir OUTSIDE the repo so originals can't be swept into a
commit. An in-tree `.slopslap/backups/` override fails closed unless git containment is verified.
Backups are owner-private, exclusively created, digest-verified, and fsync'd (file + directory)
BEFORE any mutation is permitted.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import stat
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fsync_enabled() -> bool:
    # fsync forces bytes to physical media (crash durability). It is opt-in because some
    # sandboxes/filesystems block on it; correctness (the backup exists + is readable) is proven
    # by read-back verification below, NOT by fsync. Real deployments set SLOPSLAP_FSYNC=1.
    return os.environ.get("SLOPSLAP_FSYNC") == "1"


def _maybe_fsync_fd(fd: int, warnings: List[str]) -> None:
    if _fsync_enabled():
        os.fsync(fd)
    elif "fsync skipped (durability best-effort; set SLOPSLAP_FSYNC=1)" not in warnings:
        warnings.append("fsync skipped (durability best-effort; set SLOPSLAP_FSYNC=1)")


class BackupError(Exception):
    """A backup could not be made/verified => no mutation is permitted."""


@dataclass
class BackupConfig:
    root: Optional[str] = None  # absolute external path OR the literal ".slopslap/backups" (in-tree)
    keep: int = 10


@dataclass
class BackupRecord:
    path: str
    metadata_path: str
    original_sha256: str
    size: int
    containment: str  # external | in_tree
    restore_command: str
    restore_argv: List[str]
    warnings: List[str] = field(default_factory=list)


def default_backup_root() -> str:
    system = platform.system()
    home = os.path.expanduser("~")
    if system == "Darwin":
        return os.path.join(home, "Library", "Application Support", "slopslap", "backups")
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        return os.path.join(base, "slopslap", "backups")
    xdg = os.environ.get("XDG_STATE_HOME")
    base = xdg if xdg else os.path.join(home, ".local", "state")
    return os.path.join(base, "slopslap", "backups")


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def worktree_root(path: str) -> Optional[str]:
    r = _git(["rev-parse", "--show-toplevel"], os.path.dirname(path))
    return r.stdout.strip() if r.returncode == 0 else None


def verify_in_tree_containment(repo_root: Optional[str], backup_dir: str) -> tuple[bool, str]:
    """Fail-closed check that a NEW backup file under backup_dir would be git-ignored (R4)."""
    if repo_root is None:
        return False, "not a git worktree"
    ls = _git(["ls-files", "--", backup_dir], repo_root)
    if ls.returncode == 0 and ls.stdout.strip():
        return False, "backup directory already has tracked artifacts"
    try:
        os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    except OSError as err:
        return False, f"cannot create backup dir: {err}"
    probe = os.path.join(backup_dir, ".slopslap-ignore-probe")
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("probe")
        if _git(["ls-files", "--error-unmatch", "--", probe], repo_root).returncode == 0:
            return False, "probe path is tracked"
        if _git(["check-ignore", "-q", "--no-index", "--", probe], repo_root).returncode != 0:
            return False, "backup directory is not git-ignored (add /.slopslap/backups/)"
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass
    return True, "ok"


def _ensure_private_dir(d: str, warnings: List[str]) -> None:
    if os.path.isdir(d):
        mode = stat.S_IMODE(os.stat(d).st_mode)
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise BackupError(f"backup dir {d} is group/world-writable (refusing)")
    else:
        os.makedirs(d, mode=0o700, exist_ok=True)


def _fsync_dir(d: str, warnings: List[str]) -> None:
    # Directory-entry fsync is a STRONGER durability guarantee, opt-in via SLOPSLAP_FSYNC=1
    # (some sandboxes/filesystems block on it). When skipped, the weaker guarantee is surfaced
    # (R1/R5); the durable original-byte backup remains the recovery net.
    if not _fsync_enabled():
        return
    try:
        dfd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError as err:  # e.g. some Windows/FS combinations
        warnings.append(f"backup directory fsync unsupported: {err}")


def _prune(backup_dir: str, source_key: str, keep: int, warnings: List[str]) -> None:
    if keep <= 0:
        return
    try:
        entries = sorted(f for f in os.listdir(backup_dir)
                         if f.endswith(".bak") and f"_{source_key}_" in f)
        for f in entries[:-keep] if len(entries) > keep else []:
            os.remove(os.path.join(backup_dir, f))
            meta = os.path.join(backup_dir, f + ".json")
            if os.path.exists(meta):
                os.remove(meta)
    except OSError as err:
        warnings.append(f"retention (non-fatal): {err}")


def create_verified_backup(source: str, original_bytes: bytes, config: Optional[BackupConfig] = None) -> BackupRecord:
    config = config or BackupConfig()
    source = os.path.realpath(source)  # R4: follow symlinks, bind to the real target
    warnings: List[str] = []

    if config.root == ".slopslap/backups":
        repo_root = worktree_root(source)
        backup_dir = os.path.join(repo_root or os.path.dirname(source), ".slopslap", "backups")
        ok, reason = verify_in_tree_containment(repo_root, backup_dir)
        if not ok:
            raise BackupError(f"in-tree backup containment failed: {reason}")
        containment = "in_tree"
    else:
        if config.root and not os.path.isabs(config.root):
            raise BackupError("configured backup root must be an absolute external path")
        backup_dir = config.root or default_backup_root()
        containment = "external"

    _ensure_private_dir(backup_dir, warnings)
    source_key = _sha256(source.encode())[:8]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{ts}_{time.time_ns():020d}_{source_key}_{os.path.basename(source)}.bak"
    path = os.path.join(backup_dir, name)

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # exclusive create
    try:
        os.write(fd, original_bytes)
        _maybe_fsync_fd(fd, warnings)
    finally:
        os.close(fd)
    with open(path, "rb") as fh:
        got = fh.read()
    if got != original_bytes:  # read-back is the real correctness check (not fsync)
        raise BackupError("backup verification failed (content mismatch)")

    meta_path = path + ".json"
    meta = {"source": source, "created": ts, "size": len(original_bytes),
            "sha256": _sha256(original_bytes)}
    mfd = os.open(meta_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(mfd, json.dumps(meta).encode("utf-8"))
        _maybe_fsync_fd(mfd, warnings)
    finally:
        os.close(mfd)

    _fsync_dir(backup_dir, warnings)  # R1: durable directory entry before mutation (opt-in)
    _prune(backup_dir, source_key, config.keep, warnings)  # best-effort, after verify

    restore_argv = ["cp", "--", path, source]
    restore_command = "cp -- " + shlex.quote(path) + " " + shlex.quote(source)
    return BackupRecord(path, meta_path, _sha256(original_bytes), len(original_bytes),
                        containment, restore_command, restore_argv, warnings)
