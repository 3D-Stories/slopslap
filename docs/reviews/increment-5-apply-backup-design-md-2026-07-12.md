# Adversarial Review — increment-5-apply-backup-design.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 6 (Critical 0, High 2, Medium 4, Low 0)

## Summary

The artifact defines backup-gated selective application with iterative verification and atomic replacement. Its main risks are a non-atomic concurrency check, incomplete durability and confidentiality requirements for backups, and unproven cross-platform dependencies.

## Findings

### 1. [High] completeness · high confidence — Folded decisions, item 3

> Create from the already-read original buffer** (not re-read); write + `fsync`; verify size + sha256
>    against the original bytes; only THEN permit mutation.

The backup file is synced, but the containing directory entry is not required to be synced before mutation. A crash can therefore leave the source replacement durable while the supposedly mandatory backup filename was never durably recorded, defeating the stated recovery net. The sidecar's creation and durability are also outside the mutation gate.

**Recommendation:** Extend Folded decision 3 so the backup and sidecar are written with restrictive modes, individually flushed, atomically finalized, and followed by a backup-directory `fsync` before mutation is permitted. Define unsupported directory-sync behavior explicitly as either a surfaced warning with a documented weaker guarantee or a fail-closed condition.

### 2. [High] correctness · high confidence — Folded decisions, item 9

> Immediately before replacement, **re-read the live source and compare its digest
> to the original** — abort on mismatch (concurrent edit).

The digest check and `os.replace` are separate operations. A concurrent writer can modify the source after the check but before replacement; its changes will then be overwritten, and the backup cannot recover them because it contains the earlier original bytes.

**Recommendation:** Change Folded decision 9 to require an actual exclusion or conflict protocol spanning the final check and replacement, such as a project-defined lock honored by all writers. If arbitrary external writers must be supported, explicitly acknowledge that conditional replacement is unavailable and define post-replace identity checks plus a conflict-recovery path that preserves the displaced live file.

### 3. [Medium] ambiguity · high confidence — Folded decisions, items 7–8

> Bounded monotonic re-verify loop:** start from eligible groups; each attempt materializes a
>    candidate from the UNTOUCHED original bytes (never edit the previous candidate) and calls `verify_fn`;
>    on pass → break; else remove groups attributable to new REJECT/ASK and retry; ≤ (#groups + 1)
>    attempts.

The verifier acceptance contract is not defined: neither “pass” nor the later phrase “verifies acceptably” is mapped to concrete fields or allowed combinations of ACCEPT, REJECT, ASK, `revertable`, global findings, and verifier errors. Implementations can therefore mutate for different verifier outputs while all claiming to follow this design.

**Recommendation:** Add a verifier-result truth table to Folded decisions 7–8 defining the exact predicate for final acceptance, how transport/internal errors are represented, and which result combinations block mutation.
**Ambiguity:** The terminal verification predicate is not specified in terms of the structured verifier result.

### 4. [Medium] correctness · high confidence — Folded decisions, items 4 and 9

> Atomic replace:** same-directory temp write, preserve mode, `fsync`, `os.replace`, fsync the parent
>    dir where supported.

Source symlink handling is unspecified. Applying this sequence to a symlink path normally replaces the directory entry rather than mutating its target, so a requested edit can destroy the symlink while leaving the intended source file unchanged. The earlier `symlink ⇒ abort` text is scoped to in-tree backup containment and does not define source handling.

**Recommendation:** In Folded decision 9, specify whether source symlinks are rejected or resolved. If resolved, bind backup identity, digest checks, temp-file placement, metadata preservation, and replacement to the resolved target and revalidate its identity before replacement.
**Ambiguity:** The artifact does not say whether the source path may be a symlink or which object is intended to be replaced.

### 5. [Medium] feasibility · high confidence — Folded decisions, items 1, 2, 4, and 9

> Backup root:** explicit slopslap config first; else `$XDG_STATE_HOME/slopslap/backups` (Unix, when
>    set), `~/Library/Application Support/slopslap/backups` (macOS), `%LOCALAPPDATA%\slopslap\backups`
>    (Windows), `~/.local/state/slopslap/backups` (Unix fallback).

The Linux/macOS/Windows promise relies on filesystem semantics and APIs including exclusive creation, file and directory `fsync`, atomic `os.replace`, permission preservation, canonical-path behavior, and Git subprocess execution. The artifact cites no project capability/manifest configuration, exact-object-kind call site, or spike proving these operations are permitted by this project's runtime, sandbox, supported filesystems, and CI. The phrase “where supported” also permits directory-sync loss to occur without a required surfaced warning.

**Recommendation:** Add a Platform feasibility section containing evidence from the actual project runtime and capability configuration plus spikes for each supported OS/filesystem and the optional Git path. Define detectable fallbacks and require every skipped durability operation or unavailable Git capability to appear in `warnings` or `errors`; narrow the supported-platform claim where proof is absent.

### 6. [Medium] security · high confidence — Folded decisions, items 1–3

> Backup root:** explicit slopslap config first; else `$XDG_STATE_HOME/slopslap/backups` (Unix, when
>    set), `~/Library/Application Support/slopslap/backups` (macOS), `%LOCALAPPDATA%\slopslap\backups`
>    (Windows), `~/.local/state/slopslap/backups` (Unix fallback). Config accepts ONLY an absolute
>    external path OR the explicit `.slopslap/backups` in-tree override.

No directory or file permission requirement protects copied source content. In particular, an absolute configured directory can be shared or permissively created, exposing both the source bytes and the sidecar's full source path to other users.

**Recommendation:** Add a confidentiality requirement to Folded decisions 1–3: reject unsafe existing directories, create private directories and files with explicit owner-only permissions where supported, avoid relying solely on process umask, and surface a warning or error when equivalent ACL protection cannot be verified.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._