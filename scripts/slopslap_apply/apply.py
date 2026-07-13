"""Backup-gated selective apply (design R2/R3/R5–R11 + peer consult).

apply-only-passing: only ACCEPT dependency-group hunks are applied, filtered while still in
original non-overlapping byte coordinates (composition delegated to apply_edits). A mandatory
verified backup is made FIRST; no mutation without it. A bounded monotonic re-verify loop
rebuilds each candidate from the untouched original. A pre-replace live-digest guard aborts on a
concurrent edit. The backup is never deleted on success.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import asdict
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_verification.editscript import Edit, apply_edits, parse_edits  # noqa: E402

from .backup import BackupConfig, BackupError, create_verified_backup  # noqa: E402

_BLOCKING = {"reject", "reject_global", "ask", "surface"}


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _edits(edits_input) -> List[Edit]:
    if edits_input and isinstance(edits_input[0], Edit):
        return list(edits_input)
    return parse_edits(edits_input or [])


def _hunk_id(i: int) -> str:
    return f"h{i}"


def _components(hunk_ids: List[str], findings: List[dict]) -> List[List[str]]:
    """Union hunks connected by a shared finding into dependency groups."""
    parent = {h: h for h in hunk_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for f in findings:
        hs = [h for h in f.get("implicated_hunk_ids", []) if h in parent]
        for a, b in zip(hs, hs[1:]):
            parent[find(a)] = find(b)
    comps: Dict[str, List[str]] = {}
    for h in hunk_ids:
        comps.setdefault(find(h), []).append(h)
    return list(comps.values())


def _blocking_hunks(findings: List[dict]) -> set:
    blocked = set()
    for f in findings:
        if f.get("disposition") in _BLOCKING:
            for h in f.get("implicated_hunk_ids", []):
                blocked.add(h)
    return blocked


def _has_unattributed_block(findings: List[dict]) -> bool:
    for f in findings:
        if f.get("disposition") in ("reject", "reject_global") and not f.get("implicated_hunk_ids"):
            return True
    return False


_DECISIONS = {"ACCEPT", "REJECT", "ASK", "SURFACE", "FIXTURE_ERROR"}


def _valid_result(res) -> bool:
    return (isinstance(res, dict) and res.get("decision") in _DECISIONS
            and isinstance(res.get("findings", []), list))


def _hnum(h: str):
    if isinstance(h, str) and h.startswith("h"):
        try:
            return int(h[1:])
        except ValueError:
            return None
    return None


def _bad_attribution(findings: List[dict], hunk_ids: List[str]) -> bool:
    """A blocking finding referencing an UNKNOWN hunk id (or only unknown ids) can't be
    attributed -> block partial apply (WF5-diff H3)."""
    known = set(hunk_ids)
    for f in findings:
        if f.get("disposition") in _BLOCKING:
            ids = f.get("implicated_hunk_ids", [])
            if any(h not in known for h in ids):
                return True
    return False


def _block(report: dict, msg: str) -> dict:
    report.update(status="blocked", mutated=False)
    report.setdefault("errors", []).append(msg)
    return report


def apply_selective(
    source_path: str,
    edits_input,
    verify_fn: Callable[[bytes, List[Edit]], dict],
    config: Optional[BackupConfig] = None,
    write: bool = True,
) -> dict:
    """Verify -> backup -> select ACCEPT groups -> re-verify loop -> atomic replace.

    verify_fn(original_bytes, edits) -> a ledger-verify result dict (with `decision`, `findings`,
    `hunks`). A candidate PASSES iff its verify decision == "ACCEPT" (design R3).
    """
    source = os.path.realpath(source_path)
    report: dict = {"status": None, "mutated": False, "source": source, "warnings": [], "errors": []}
    try:
        with open(source, "rb") as fh:
            original = fh.read()
        orig_stat = os.stat(source)  # capture identity (dev/ino/nlink) for the pre-replace guard (H5)
    except OSError as err:
        report.update(status="error", errors=[f"cannot read source: {err}"])
        return report

    # --- #21 hardening: fail-closed edge-case guards BEFORE any mutation (incl. the backup) ---
    # Hardlink: os.replace creates a NEW inode, so mutating a hardlinked file leaves the OTHER links
    # on the old bytes. Refuse, fail closed. (adv H4: re-checked at the pre-replace guard too, since
    # a second link can appear after this stat.)
    if orig_stat.st_nlink > 1:
        report.update(status="blocked",
                      errors=[f"refusing to mutate a hardlinked file ({orig_stat.st_nlink} links); "
                              f"atomic replace would orphan the other link(s)"])
        return report
    # Symlink: model C follows the link and replaces its TARGET (`source` is already realpath'd).
    # Record which concrete file was mutated so the caller sees it. The path-substitution race guard
    # is the dev/inode + content-sha re-check at the pre-replace boundary below — NOT O_NOFOLLOW,
    # which only pins the final open's last component and cannot bind the pathname-based os.replace.
    if os.path.islink(source_path):
        report["followed_symlink"] = f"{source_path} -> {source}"
    # Extended attributes (xattr/ACL/security labels) are NOT carried across the inode replacement.
    # Detect + warn loudly (not a hard block) so the loss is legible, never silent. (adv H3)
    _listxattr = getattr(os, "listxattr", None)
    if _listxattr is not None:
        try:
            if _listxattr(source):
                report["warnings"].append(
                    "extended attributes (xattr/ACL/security labels) will NOT be preserved across "
                    "the atomic replacement")
        except OSError as err:
            # a probe failure never blocks apply (warn-only, best-effort), but surface it rather
            # than swallow — a silent skip could hide a real xattr loss (Step-11 Low).
            report["warnings"].append(f"could not check extended attributes ({err}); "
                                      f"any xattr/ACL will NOT be preserved across the replacement")

    # sort into the SAME order ledger-verify labels hunks (by start,end), so h0..hN align.
    all_edits = sorted(_edits(edits_input), key=lambda e: (e.start_byte, e.end_byte))
    report["original_digest"] = _sha256(original)

    # --- mandatory backup FIRST ---
    try:
        backup = create_verified_backup(source, original, config)
    except BackupError as err:
        report.update(status="blocked", errors=[f"backup failed, refusing to mutate: {err}"])
        return report
    report["backup"] = {"path": backup.path, "metadata": backup.metadata_path,
                        "restore_command": backup.restore_command, "restore_argv": backup.restore_argv,
                        "containment": backup.containment}
    report["warnings"] += backup.warnings

    # --- initial verify (validated + exception-guarded; H4) ---
    try:
        initial = verify_fn(original, all_edits)
    except Exception as err:  # noqa: BLE001
        return _block(report, f"initial verifier raised: {err!r}")
    if not _valid_result(initial):
        return _block(report, "initial verify result malformed / missing decision")
    findings = initial.get("findings", [])
    hunk_ids = [_hunk_id(i) for i in range(len(all_edits))]
    if _has_unattributed_block(findings) or _bad_attribution(findings, hunk_ids):
        return _block(report, "non-revertable/unknown attribution blocks partial apply")

    groups = _components(hunk_ids, findings)
    blocked = _blocking_hunks(findings)  # original hunk ids from the initial verify

    # --- bounded monotonic elimination loop (design R7 / WF5-diff H1) ---
    final = None
    active: set = set()
    for attempt in range(len(groups) + 1):
        active = set()
        for comp in groups:  # a component is excluded if ANY member is blocked
            if not any(h in blocked for h in comp):
                active.update(comp)
        subset_indices = sorted(i for i in range(len(all_edits)) if _hunk_id(i) in active)
        subset = [all_edits[i] for i in subset_indices]
        try:
            res = verify_fn(original, subset)  # rebuild candidate from the UNTOUCHED original
        except Exception as err:  # noqa: BLE001
            return _block(report, f"re-verify raised: {err!r}")
        if not _valid_result(res):
            return _block(report, "re-verify result malformed")
        final = res
        report["verification_attempts"] = attempt + 2  # initial + this
        if res["decision"] == "ACCEPT":
            break
        if _has_unattributed_block(res.get("findings", [])):
            return _block(report, "unattributed failure during re-verify")
        # translate subset-relative hunk ids (h0..hk over the sorted subset) back to original ids
        newly = set()
        for f in res.get("findings", []):
            if f.get("disposition") not in _BLOCKING:
                continue
            for h in f.get("implicated_hunk_ids", []):
                j = _hnum(h)
                if j is None or not (0 <= j < len(subset_indices)):
                    return _block(report, "unknown hunk id in re-verify")
                newly.add(_hunk_id(subset_indices[j]))
        if newly <= blocked:  # no progress possible
            return _block(report, "could not converge on an ACCEPT subset")
        blocked |= newly
    else:
        return _block(report, "exceeded re-verify attempt bound")

    report["applied_hunks"] = sorted(active)
    report["withheld_hunks"] = sorted(set(hunk_ids) - active)
    report["final_verification"] = final["decision"] if final else None

    subset = [all_edits[i] for i in sorted(i for i in range(len(all_edits)) if _hunk_id(i) in active)]
    if not subset:
        report.update(status="no_op", mutated=False, final_digest=_sha256(original))
        return report

    candidate = apply_edits(original, subset)
    if candidate == original:
        report.update(status="no_op", mutated=False, final_digest=_sha256(original))
        return report
    if not write:
        report.update(status="applied", mutated=False, final_digest=_sha256(candidate),
                      note="write=False (dry run)")
        return report

    # --- atomic replace with a complete-write + read-back guard (H2). The live-source
    #     re-validation (identity/hardlink/content) runs IMMEDIATELY before os.replace — after the
    #     temp is fully staged — so the TOCTOU window to the atomic swap is minimal (adv-diff H1 /
    #     peer step 5), not widened across the whole write+fsync+read-back. ---
    tmp = source + f".slopslap.tmp.{os.getpid()}"
    try:
        # create with a SAFE default (0o600), write, then fchmod to the EXACT source mode just before
        # commit — the create-mode arg is umask-masked, so relying on it could ship a wrong (often
        # more-restrictive) mode while reporting success (adv H2). Setting the mode after the write
        # keeps the predictably-named temp at owner-only 0o600 while its bytes land. fchmod failure
        # fails closed: the temp is not yet swapped, so the outer except cleans it and aborts with the
        # source intact. os.fchmod is POSIX-only — a platform lacking it (Windows, which backup.py
        # DOES support) keeps the 0o600 default and warns, rather than raising an uncaught
        # AttributeError the OSError handlers would miss (Step-8a Medium).
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            _write_all(fd, candidate)  # loop until every byte lands (no short-write corruption)
            _fchmod = getattr(os, "fchmod", None)
            if _fchmod is not None:
                try:
                    _fchmod(fd, stat_mode(orig_stat))  # EXACT mode, not umask-masked
                except OSError as err:
                    raise OSError(f"fchmod (exact-mode preservation) failed: {err}") from err
            else:
                report["warnings"].append(
                    "exact-mode preservation unavailable on this platform (os.fchmod absent); "
                    "applied file has owner-only (0o600) mode")
            if os.environ.get("SLOPSLAP_FSYNC") == "1":
                os.fsync(fd)
        finally:
            os.close(fd)
        with open(tmp, "rb") as fh:  # read-back before committing
            if fh.read() != candidate:
                raise OSError("temp file content mismatch after write")
        # LAST-moment re-validation of the live source, tight to the atomic swap (adv-diff H1):
        # resolved-path identity, dev/inode, hardlink count, content digest must still match the
        # audited snapshot. A hardlink or concurrent edit that appeared during temp staging is caught
        # here rather than orphaning a link / clobbering a concurrent write.
        reason = _precommit_reason(source, orig_stat, report["original_digest"])
        if reason is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return _block(report, reason)
        os.replace(tmp, source)
        _fsync_parent(source, report["warnings"])
    except OSError as err:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        report.update(status="error", errors=[f"atomic replace failed: {err}; "
                                              f"restore with: {backup.restore_command}"])
        return report

    report.update(status="applied", mutated=True, final_digest=_sha256(candidate))
    return report


def _precommit_reason(source: str, orig_stat, original_digest: str) -> Optional[str]:
    """Re-validate the live source IMMEDIATELY before os.replace (peer sketch step 5): resolved-path
    identity, dev/inode, hardlink count, and content digest must still match the audited snapshot.
    Returns a block reason, or None if safe to commit. Called as tight to the atomic rename as
    possible so the TOCTOU window is minimal (adv-diff H1)."""
    live_path = os.path.realpath(source)
    if live_path != source:
        return "source symlink/path changed since read; not clobbering"
    try:
        live_stat = os.stat(live_path)
        with open(live_path, "rb") as fh:
            live = fh.read()
    except OSError as err:
        return f"re-read failed: {err}"
    if (live_stat.st_dev, live_stat.st_ino) != (orig_stat.st_dev, orig_stat.st_ino):
        return "source identity (dev/inode) changed since read; not clobbering"
    if live_stat.st_nlink > 1:  # adv H4: a hardlink created after the initial pre-backup stat
        return (f"source became hardlinked ({live_stat.st_nlink} links) since read; "
                f"not clobbering (would orphan the other link(s))")
    if _sha256(live) != original_digest:
        return "source changed since read (concurrent edit); not clobbering"
    return None


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    total = 0
    while total < len(data):
        n = os.write(fd, view[total:])
        if n <= 0:
            raise OSError("short write (zero progress)")
        total += n


def stat_mode(st) -> int:
    import stat as _stat
    return _stat.S_IMODE(st.st_mode)


def _fsync_parent(path: str, warnings: List[str]) -> None:
    # opt-in (some sandboxes block directory fsync); the backup is the recovery net regardless.
    if os.environ.get("SLOPSLAP_FSYNC") != "1":
        return
    try:
        dfd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError as err:
        warnings.append(f"parent dir fsync unsupported: {err}")
