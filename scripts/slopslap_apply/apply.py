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
    except OSError as err:
        report.update(status="error", errors=[f"cannot read source: {err}"])
        return report

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

    # --- initial verify ---
    initial = verify_fn(original, all_edits)
    findings = initial.get("findings", [])
    if _has_unattributed_block(findings):
        report.update(status="blocked", mutated=False,
                      errors=["a non-revertable/unattributed finding blocks partial apply"])
        report["final_verification"] = initial.get("decision")
        return report

    # apply's hunk ids h0..hN align with the initial verify's (same sorted edits), so its
    # per-hunk attribution is authoritative for SELECTION. The re-verify below is used only for
    # its final ACCEPT decision (design R3), so its own hunk re-indexing over the subset is moot.
    hunk_ids = [_hunk_id(i) for i in range(len(all_edits))]
    groups = _components(hunk_ids, findings)
    blocked = _blocking_hunks(findings)
    active = set()
    for comp in groups:  # exclude any dependency group touching a blocked hunk
        if not any(h in blocked for h in comp):
            active.update(comp)

    subset = [e for i, e in enumerate(all_edits) if _hunk_id(i) in active]
    report["applied_hunks"] = sorted(active)
    report["withheld_hunks"] = sorted(set(hunk_ids) - active)

    reverify = verify_fn(original, subset)  # candidate built from the UNTOUCHED original
    report["verification_attempts"] = 2  # initial + re-verify
    report["final_verification"] = reverify.get("decision")

    if not subset:
        # nothing safe to apply: a no-op only if the ORIGINAL itself verifies acceptably
        report.update(status="no_op" if reverify.get("decision") == "ACCEPT" else "blocked",
                      mutated=False, final_digest=_sha256(original))
        return report
    if reverify.get("decision") != "ACCEPT":
        report.update(status="blocked", mutated=False,
                      errors=["selected subset does not re-verify ACCEPT (dependent hunk removed)"])
        return report

    candidate = apply_edits(original, subset)
    if candidate == original:
        report.update(status="no_op", mutated=False, final_digest=_sha256(original))
        return report

    if not write:
        report.update(status="applied", mutated=False, final_digest=_sha256(candidate),
                      note="write=False (dry run)")
        return report

    # --- pre-replace concurrency guard (R2) ---
    try:
        with open(source, "rb") as fh:
            live = fh.read()
    except OSError as err:
        report.update(status="blocked", errors=[f"re-read failed: {err}"])
        return report
    if _sha256(live) != report["original_digest"]:
        report.update(status="blocked", mutated=False,
                      errors=["source changed since read (concurrent edit); not clobbering"])
        return report

    # --- atomic replace ---
    tmp = source + f".slopslap.tmp.{os.getpid()}"
    try:
        st = os.stat(source)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat_mode(st))
        try:
            os.write(fd, candidate)
            if os.environ.get("SLOPSLAP_FSYNC") == "1":
                os.fsync(fd)  # opt-in crash durability; some sandboxes block on fsync
        finally:
            os.close(fd)
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
