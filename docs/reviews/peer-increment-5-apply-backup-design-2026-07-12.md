# Peer Consult — increment-5-apply-backup-design.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Implement a transactional, backup-first apply pipeline. `backup.py` resolves a platform-appropriate state directory or validates an explicit in-tree override, creates an immutable collision-safe copy of the exact original bytes, prunes old backups only after the new backup is durable, and returns restoration metadata. `apply.py` consumes the existing byte-coordinate edit script and verifier result, rejects partial application when any finding is non-revertable, groups hunks by verification dependency, selects only groups whose findings are ACCEPT, applies their edits directly to the original bytes, and re-runs the existing verifier before any source-file replacement. If verification fails, iteratively remove every attributable failing dependency group and re-verify; if failure is unattributed, ambiguous, non-revertable, or convergence stalls, write nothing. Commit the final bytes with a same-directory temporary file plus atomic replacement, while retaining the external backup as the authoritative recovery mechanism.

## Key decisions

- Default backup root: honor an explicit slopslap backup configuration first; otherwise use `$XDG_STATE_HOME/slopslap/backups` on Unix when set, `~/Library/Application Support/slopslap/backups` on macOS, `%LOCALAPPDATA%\slopslap\backups` on Windows, and `~/.local/state/slopslap/backups` as the Unix fallback. Configuration should accept only an absolute external path or the explicit project-relative `.slopslap/backups` override.
- Name backups without relying on git identity: combine a filesystem-safe UTC timestamp with nanoseconds or a random nonce, a stable hash of the canonical source path, and the source basename. Use exclusive creation so collisions retry rather than overwrite. Store enough sidecar metadata to identify source path, creation time, byte length, and content hash.
- Create the backup from the already-read original byte buffer used by apply, not by re-reading later. Flush and fsync the backup file, verify its size and cryptographic digest against the original bytes, and only then permit mutation. A backup failure, verification mismatch, or unverifiable destination aborts the operation.
- For an in-tree override, first locate the git worktree root and require a functioning git repository. Refuse if `git ls-files --error-unmatch -- <candidate-backup-path>` succeeds, or if `git ls-files -- <backup-directory>` reports any tracked backup artifacts. Create the backup directory and a unique probe file, then run `git check-ignore -q --no-index -- <probe>`; only exit status 0 proves the effective rules ignore a newly created backup. Remove the probe afterward. Status 1, git errors, paths outside the discovered worktree, symlink escapes, or tracked candidates fail closed.
- If no `.gitignore` exists, containment is established by adding a narrowly scoped root rule such as `/.slopslap/backups/` to the repository’s exclude mechanism chosen by the project, then verifying it with the probe and `git check-ignore`. Merely writing a rule is insufficient. Because editing ignore configuration is itself a mutation, perform it as an explicit containment setup step and verify it before creating the source backup; if policy does not authorize changing ignore configuration, abort and require the user to configure it.
- Use apply-only-passing semantics. Applying all edits and reversing rejected edits introduces offset translation and rollback failure modes; filtering edits while they remain in original, non-overlapping byte coordinates is deterministic and delegates composition to the existing `apply_edits`.
- Represent dependency groups explicitly. Each hunk has a stable `hunk_id`; every ledger finding identifies its affected hunk IDs. Union hunks mentioned by the same finding, plus any declared edit-script dependency edges, into connected components. A component is eligible only when all findings touching it are ACCEPT. REJECT or ASK on any member excludes the entire component. Missing, unknown, or contradictory hunk attribution is treated as non-revertable and blocks partial apply.
- Re-verification is a bounded monotonic elimination loop: begin with eligible groups, materialize a candidate from the untouched original bytes, and verify it. Remove all groups attributable to new REJECT/ASK findings, then rebuild from the original and verify again. Never edit the previous candidate in place. Stop successfully when verification passes; stop with no source mutation if a failure cannot be attributed, if no additional group can be removed, if verifier results are inconsistent, or after at most the number of groups plus one verification attempts.
- An empty surviving set is a valid no-op only if verification of the original revision is acceptable; otherwise return blocked. This distinguishes ‘nothing safe to apply’ from a successful mutation.
- Replace the source only after the final candidate passes verification. Write a temporary file in the source directory, preserve required mode/metadata, flush and fsync it, atomically replace the source, and fsync the parent directory where supported. The backup is never deleted on success and remains usable if grouping, edit application, or replacement logic is defective.
- Retention is best-effort only after the new backup is verified. Keep the newest N backups per source identity, never prune the just-created backup, and report pruning warnings without weakening the backup gate.
- Return a structured report containing status, source path, whether mutation occurred, original and final digests, backup metadata, restore command, initially accepted/excluded hunks, dependency groups, applied hunks, reverted or withheld hunks with reasons, verification attempts and final result, and warnings/errors. Restore commands must be safely shell-quoted and platform-specific; structured source/backup paths should also be returned so callers need not parse the command.

## Risks

- `git check-ignore` can be misleading for tracked files unless paired with `git ls-files`; symlinks and path canonicalization can also escape the intended ignored directory.
- Automatically modifying `.gitignore` may be an unexpected repository change. Prefer a preconfigured ignore rule or an explicitly authorized setup operation, and surface any ignore-file mutation separately.
- Verifier attribution may be incomplete or unstable across reduced candidates. Fail closed whenever a finding cannot be mapped unambiguously to dependency groups.
- A passing subset may still alter semantics not represented by ledger findings. The final verifier is necessary but cannot exceed the verifier’s coverage; the durable original-byte backup remains the recovery boundary.
- Atomic replacement semantics, permission preservation, file locking, and restore-command quoting differ across operating systems. Platform-specific helpers and failure-injection tests are needed.
- Concurrent source changes between initial read and replacement could overwrite user work. Compare the live source digest to the original digest immediately before replacement and abort on mismatch.
- Retention or cleanup bugs could remove useful recovery points. Scope pruning by stable source identity, sort from metadata rather than filenames alone, and make cleanup non-fatal.
- A crash after ignore-rule setup but before backup creation can leave a benign repository change; a crash after atomic replacement still leaves the already-fsynced backup.

## Sketch

backup.py:
- `BackupConfig(root: Path | None, keep: int)`
- `BackupRecord(path, metadata_path, original_sha256, size, restore_argv, restore_command, containment)`
- `resolve_backup_root(source, config) -> external | in_tree`
- `verify_in_tree_containment(repo_root, backup_dir, candidate)`:
  1. canonicalize paths; reject escapes/symlinks
  2. require git worktree
  3. reject tracked directory artifacts and candidate via `git ls-files`
  4. create unique probe inside destination
  5. require `git check-ignore -q --no-index -- probe` == 0
  6. remove probe; otherwise abort
- `create_verified_backup(source, original_bytes, config) -> BackupRecord`: exclusive create, write/fsync, hash/size check, metadata write, then best-effort retention.

apply.py:
- `ApplyReport(status, mutated, source, original_digest, final_digest, backup, groups, applied_hunks, withheld_hunks, verification_attempts, final_verification, warnings, errors)`
- `apply_selective(source, original_bytes, edit_script, initial_verify, verify_fn, backup_config)`:
  1. validate edit coordinates, hunk IDs, non-overlap, verifier schema, and source digest
  2. create and verify mandatory backup
  3. if any non-revertable/unattributed finding: return `blocked` with backup, no mutation
  4. build dependency components; exclude components touched by ASK/REJECT
  5. loop: build candidate as `apply_edits(original_bytes, edits_for(active_groups))`; verify candidate; on pass break; otherwise remove attributable failing groups; on no progress/unattributed failure return `blocked`, no mutation
  6. if candidate equals original: return `no_op`
  7. confirm live source digest still equals original digest
  8. durable same-directory temp write and atomic replace
  9. return `applied` report with the backup path and restore command such as `cp -- <backup> <source>` on POSIX or a PowerShell `Copy-Item -LiteralPath ... -Force` command on Windows.

---
_Peer proposal (report-only). Synthesize at your discretion._
