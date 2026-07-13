"""#21 — apply write-strategy hardening (model C edge cases, failure-injection).

Each test asserts fail-closed behavior with the source left byte-identical (or, for the happy path,
correctly mutated). POSIX-only features (hardlinks, listxattr, umask) skip cleanly elsewhere.
"""
import base64
import errno
import os
import stat as _stat

import pytest

from slopslap_apply import apply as apply_mod
from slopslap_apply.apply import apply_selective
from slopslap_apply.backup import BackupConfig

ACCEPT = lambda o, ed: {"decision": "ACCEPT", "findings": [], "hunks": []}

_POSIX = os.name == "posix"
posix_only = pytest.mark.skipif(not _POSIX, reason="POSIX-only filesystem semantics")


def _e(s, e, r):
    return {"start_byte": s, "end_byte": e, "replacement_b64": base64.b64encode(r).decode()}


def _src(tmp_path, data=b"one two three\n"):
    p = tmp_path / "d.md"
    p.write_bytes(data)
    return p


def _bk(tmp_path):
    return BackupConfig(root=str(tmp_path / "bk"))


def _backup_count(tmp_path):
    d = tmp_path / "bk"
    return len([f for f in os.listdir(d) if f.endswith(".bak")]) if d.exists() else 0


# ---- test 1: hardlink fail-closed (pre-backup) ----
@posix_only
def test_hardlink_fails_closed_before_backup(tmp_path):
    src = _src(tmp_path)
    link = tmp_path / "d_link.md"
    os.link(str(src), str(link))  # st_nlink == 2
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "blocked" and r["mutated"] is False
    assert "hardlink" in " ".join(r["errors"]).lower()
    assert src.read_bytes() == b"one two three\n"          # source intact
    assert link.read_bytes() == b"one two three\n"          # other link intact
    assert _backup_count(tmp_path) == 0                      # no backup created (blocked before it)


# ---- test 2: hardlink TOCTOU — a 2nd link appears between the initial stat and the pre-replace re-stat ----
@posix_only
def test_hardlink_created_after_stat_caught_at_prereplace(tmp_path, monkeypatch):
    src = _src(tmp_path)
    link = tmp_path / "late_link.md"
    real_stat = os.stat
    state = {"n": 0}

    def fake_stat(path, *a, **k):
        st = real_stat(path, *a, **k)
        # the FIRST stat of the source (pre-backup guard) sees nlink==1; create the 2nd link right
        # after, so the pre-replace re-stat sees nlink==2 (the TOCTOU window adv H4 names).
        try:
            same = os.path.samestat(st, real_stat(str(src)))
        except OSError:
            same = False
        if same:
            state["n"] += 1
            if state["n"] == 1 and not link.exists():
                os.link(str(src), str(link))
        return st

    monkeypatch.setattr(apply_mod.os, "stat", fake_stat)
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] in ("blocked", "error") and r["mutated"] is False
    assert src.read_bytes() == b"one two three\n"


# ---- test 2b: hardlink created DURING temp staging (adv-diff H1) — caught by the last-moment
#      pre-commit re-check that now runs tight to os.replace, not before the temp write ----
@posix_only
def test_hardlink_during_temp_staging_caught(tmp_path, monkeypatch):
    src = _src(tmp_path)
    link = tmp_path / "staging_link.md"
    real_write_all = apply_mod._write_all

    def hook(fd, data):
        real_write_all(fd, data)
        if not link.exists():
            os.link(str(src), str(link))  # link appears while the temp is being staged

    monkeypatch.setattr(apply_mod, "_write_all", hook)
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "blocked" and r["mutated"] is False
    assert "hardlink" in " ".join(r["errors"]).lower()
    assert src.read_bytes() == b"one two three\n"          # not clobbered
    assert link.read_bytes() == b"one two three\n"          # the other link not orphaned
    assert not any(f.startswith("d.md.slopslap.tmp") for f in os.listdir(tmp_path))  # temp cleaned


# ---- test 3: exact mode via fchmod is load-bearing (umask would otherwise mask it) ----
@posix_only
def test_exact_mode_preserved_via_fchmod(tmp_path):
    src = _src(tmp_path)
    os.chmod(str(src), 0o644)
    old = os.umask(0o077)  # would mask group+other -> create-mode path yields 0o600, not 0o644
    try:
        r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    finally:
        os.umask(old)
    assert r["status"] == "applied" and r["mutated"] is True
    mode = _stat.S_IMODE(os.stat(str(src)).st_mode)
    assert mode == 0o644, f"expected 0o644 (fchmod), got {oct(mode)} (umask masked create-mode = no fchmod)"


# ---- test 4: fchmod failure -> fail closed (no wrong-mode file shipped) ----
@posix_only
def test_fchmod_failure_aborts(tmp_path, monkeypatch):
    src = _src(tmp_path)

    def boom(fd, mode):
        raise OSError(errno.EPERM, "fchmod denied")

    monkeypatch.setattr(apply_mod.os, "fchmod", boom)
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "error" and r["mutated"] is False
    assert src.read_bytes() == b"one two three\n"


# ---- test 4b: os.fchmod ABSENT (Windows analog) -> graceful degrade, not an uncaught AttributeError ----
def test_fchmod_absent_degrades_gracefully(tmp_path, monkeypatch):
    src = _src(tmp_path)
    monkeypatch.delattr(apply_mod.os, "fchmod", raising=False)  # simulate a platform without fchmod
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "applied" and r["mutated"] is True     # not a crash / uncaught AttributeError
    assert src.read_bytes() == b"ONE two three\n"
    assert any("os.fchmod absent" in w for w in r["warnings"]), r["warnings"]
    # no orphaned temp left behind
    assert not any(f.startswith("d.md.slopslap.tmp") for f in os.listdir(tmp_path))


# ---- test 5: EXDEV never copies over the live source ----
def test_exdev_replace_never_copies_over_live(tmp_path, monkeypatch):
    src = _src(tmp_path)

    def exdev(a, b):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(apply_mod.os, "replace", exdev)
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "error" and r["mutated"] is False
    assert src.read_bytes() == b"one two three\n"           # live source untouched (no copy-fallback)
    assert r["backup"]["restore_command"]                    # recovery net surfaced


# ---- test 6: symlink source followed to target + reported ----
@posix_only
def test_symlink_followed_and_reported(tmp_path):
    target = tmp_path / "real.md"
    target.write_bytes(b"one two three\n")
    link = tmp_path / "link.md"
    os.symlink(str(target), str(link))
    r = apply_selective(str(link), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "applied" and r["mutated"] is True
    assert target.read_bytes() == b"ONE two three\n"        # the TARGET was mutated
    assert "followed_symlink" in r and str(target) in r["followed_symlink"]


# ---- test 7: xattr-loss warning (not a hard block) ----
@posix_only
def test_xattr_loss_warns(tmp_path):
    if not hasattr(os, "listxattr") or not hasattr(os, "setxattr"):
        pytest.skip("xattr syscalls unavailable")
    src = _src(tmp_path)
    try:
        os.setxattr(str(src), "user.slopslap_test", b"1")
    except OSError:
        pytest.skip("filesystem rejects user xattrs")
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "applied" and r["mutated"] is True   # not a hard block
    assert any("xattr" in w.lower() for w in r["warnings"]), r["warnings"]


# ---- test 8: generic os.replace failure -> clean abort, backup preserved ----
def test_generic_replace_failure_clean_abort(tmp_path, monkeypatch):
    src = _src(tmp_path)

    def boom(a, b):
        raise OSError(errno.EACCES, "sharing violation")

    monkeypatch.setattr(apply_mod.os, "replace", boom)
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "error" and r["mutated"] is False
    assert src.read_bytes() == b"one two three\n"
    assert os.path.exists(r["backup"]["path"])


# ---- test 9: happy-path regression (guards don't break a normal apply) ----
def test_happy_path_still_works(tmp_path):
    src = _src(tmp_path)
    r = apply_selective(str(src), [_e(0, 3, b"ONE")], ACCEPT, _bk(tmp_path))
    assert r["status"] == "applied" and r["mutated"] is True
    assert src.read_bytes() == b"ONE two three\n"
    assert os.path.exists(r["backup"]["path"])
