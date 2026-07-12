# Increment 5 design brief — #apply-backup (backup-gated apply + per-hunk selective rollback)

Context: slopslap's **apply** mode mutates the source file in place, on explicit request, and is
**gated by a mandatory pre-mutation backup** — the universal safety net (works for git AND non-git AND
dirty files), so a verify-miss is always recoverable. Per-hunk selective rollback layers ON TOP of the
backup. This consumes the #ledger-verify verifier (its `hunks[]` + `revertable`). Spec:
`docs/planning/2026-07-12-slopslap-reconciled-spec.md` (§Output modes apply, §MVP cut). Reuse the
increment-1 edit-map + the increment-4 verify; don't re-implement.

## Deliverables
- `scripts/slopslap_apply/backup.py` — the mandatory pre-mutation backup.
- `scripts/slopslap_apply/apply.py` — selective apply (apply only passing hunks; revert failing
  hunks/dependency groups), returning a structured report.

## Backup (spec §apply; WF5 #4)
- **Default: a timestamped copy in a user-local state dir OUTSIDE the repo** (the plugin's state dir,
  e.g. `$XDG_STATE_HOME/slopslap/backups/` or `~/.local/state/slopslap/backups/`), so original prose can
  never be swept into a commit. Git-independent.
- If a project overrides to an in-tree `.slopslap/backups/`, the implementation MUST first create AND
  **verify an effective ignore rule** (via `git check-ignore`), detect an already-tracked backup path
  (`git ls-files`), and **fail closed (no backup ⇒ no mutation)** if containment can't be guaranteed —
  an in-tree dir is NOT git-ignored merely by living in the tree.
- Print the restore path + a one-line restore command; keep the last N backups.

## Selective apply (spec §MVP; byte-offset edit-map)
- Take the original bytes + the edit script + the #ledger-verify result. Apply **only the ACCEPT hunks**;
  do NOT apply REJECT/ASK hunks. A non-revertable finding (unattributed global) blocks partial apply →
  apply nothing.
- Reuse the byte-offset edit-map (increment-1 `editscript`); applying a subset of hunks is just
  `apply_edits` over the surviving hunks (still in original coordinates, non-overlapping).
- After a selective apply, **re-verify** the resulting revision (the spec's "revert failing hunk then
  rerun verification").

## Questions for the peer
1. **Backup location + cross-platform** — XDG state dir vs a config value; robust default on
   Linux/macOS/Windows; git-independent naming (collision-safe timestamped names).
2. **In-tree containment** — the exact `git check-ignore` + `git ls-files` sequence that fails closed,
   and what "verified ignore rule" means when the repo has no `.gitignore` yet.
3. **Selective apply semantics** — apply-only-passing vs apply-all-then-revert-failing; which is safer
   given byte-offset shifts, and how to define a dependency group (a ledger entry spanning several hunks
   ⇒ revert them together).
4. **Re-verify loop** — after selective apply, re-run verify; what if the reduced set STILL fails (a
   surviving hunk depended on a reverted one)? Converge or block?
5. **Return shape** — what apply returns so a caller (and the eval-run) can report applied/reverted
   hunks, the backup path, and the restore command; and how the backup remains the net even if selective
   rollback has a bug.

## Folded decisions — post peer-consult (gpt-5.6-sol, `docs/reviews/peer-increment-5-apply-backup-design-2026-07-12.md`)

1. **Backup root:** explicit slopslap config first; else `$XDG_STATE_HOME/slopslap/backups` (Unix, when
   set), `~/Library/Application Support/slopslap/backups` (macOS), `%LOCALAPPDATA%\slopslap\backups`
   (Windows), `~/.local/state/slopslap/backups` (Unix fallback). Config accepts ONLY an absolute
   external path OR the explicit `.slopslap/backups` in-tree override.
2. **Naming (git-independent):** UTC timestamp + nanoseconds/nonce + a stable hash of the canonical
   source path + the basename. **Exclusive create (`O_EXCL`)** so a collision retries, never overwrites.
   A sidecar `.json` records source path, creation time, byte length, content sha256.
3. **Create from the already-read original buffer** (not re-read); write + `fsync`; verify size + sha256
   against the original bytes; only THEN permit mutation. A backup failure / digest mismatch /
   unverifiable destination **aborts** (no mutation).
4. **In-tree containment** fails closed: locate the git worktree; refuse if `git ls-files
   --error-unmatch <candidate>` succeeds or `git ls-files <backup-dir>` reports tracked artifacts;
   create a unique probe and require `git check-ignore -q --no-index <probe>` == 0; remove the probe.
   Status 1 / git error / path escape / symlink / tracked ⇒ abort. **No auto-`.gitignore` edit** — if the
   dir isn't already ignored, abort and tell the user to add `/.slopslap/backups/` (editing ignore
   config is itself a mutation and needs explicit authorization).
5. **apply-only-passing** (NOT apply-all-then-revert): filter edits while they remain in original
   non-overlapping byte coords and delegate composition to `apply_edits` — deterministic, no offset
   translation.
6. **Dependency groups:** hunks mentioned by the same finding union into connected components; a
   component is eligible only when ALL findings touching it are ACCEPT; any REJECT/ASK on a member
   excludes the whole component. Missing/unknown/contradictory attribution ⇒ non-revertable ⇒ block
   partial apply.
7. **Bounded monotonic re-verify loop:** start from eligible groups; each attempt materializes a
   candidate from the UNTOUCHED original bytes (never edit the previous candidate) and calls `verify_fn`;
   on pass → break; else remove groups attributable to new REJECT/ASK and retry; ≤ (#groups + 1)
   attempts. Unattributable failure / no progress / inconsistent verifier ⇒ block, no mutation.
8. **Empty surviving set** = a no-op only if the original verifies acceptably, else blocked — distinguish
   "nothing safe to apply" from a successful mutation.
9. **Atomic replace:** same-directory temp write, preserve mode, `fsync`, `os.replace`, fsync the parent
   dir where supported. Immediately before replacement, **re-read the live source and compare its digest
   to the original** — abort on mismatch (concurrent edit). The backup is NEVER deleted on success and
   remains the recovery net even if grouping / apply / replace logic is defective.
10. **Retention** is best-effort AFTER the new backup verifies: keep newest N per source identity, never
    prune the just-created backup, sort by sidecar metadata, non-fatal on error.
11. **Return report:** `{status, mutated, source, original_digest, final_digest, backup{path, metadata,
    restore_command, restore_argv}, groups, applied_hunks, withheld_hunks (with reasons),
    verification_attempts, final_verification, warnings, errors}`. Restore command is shell-quoted +
    platform-specific; structured paths returned too so callers need not parse it.

## Post-review resolutions — WF5 on the apply-backup design (`docs/reviews/increment-5-apply-backup-design-md-2026-07-12.md`, 0 Crit / 2 High / 4 Med, all confirmed)

- **R1 (H1) — backup durability.** The backup file AND its sidecar are written with owner-only perms,
  fsync'd, and the **backup directory is fsync'd** before any mutation is permitted. Where directory
  fsync is unsupported, a `warning` is surfaced (documented weaker guarantee), not silently skipped.
- **R2 (H2) — concurrency.** There is no cross-process lock in the MVP, so the check→replace window
  can't be fully closed. Mitigation: immediately before `os.replace`, **re-read the live source and abort
  if its digest ≠ the original we backed up** (a concurrent edit is not clobbered). The sub-millisecond
  window between that read and `os.replace` is a **documented limitation**; the durable original-byte
  backup remains the recovery boundary regardless.
- **R3 (M3) — acceptance truth table.** A candidate "passes" the re-verify loop **iff `verify_fn`
  returns `decision == "ACCEPT"`**. `REJECT`/`ASK`/`SURFACE` do not pass. A verifier exception or a
  result missing `decision` ⇒ block, no mutation. "the original verifies acceptably" (empty surviving
  set) uses the same predicate on the unedited original.
- **R4 (M4) — source symlinks.** The source path is `realpath`-resolved; backup identity, digest checks,
  temp-file placement, and the atomic replace all bind to the **resolved target** (so a symlink is
  followed, not destroyed). The resolved identity is revalidated before replacement.
- **R5 (M5) — platform.** Fully exercised on **Linux** (this host). macOS/Windows paths use the same
  stdlib primitives (`os.open O_EXCL`, `os.fsync`, `os.replace`) with best-effort fallbacks; any skipped
  durability op or unavailable git capability is surfaced in `warnings`. The supported-platform claim is
  narrowed accordingly.
  - **Implementation note (build):** `os.fsync` (file AND directory) is **opt-in via `SLOPSLAP_FSYNC=1`**
    (default OFF) because some sandboxes/filesystems intermittently BLOCK on it — a hang isn't catchable
    by `except OSError`. Correctness (the backup exists + is readable) is proven by **read-back
    verification**, not fsync; fsync only adds crash-durability. When off, a `warnings` entry surfaces the
    weaker guarantee. Real deployments set `SLOPSLAP_FSYNC=1`.
- **R6 (M6) — confidentiality.** Backup dirs are created `0o700` and files `0o600` (source bytes + the
  sidecar's source path stay owner-private). An existing backup dir that is group/world-writable is
  **rejected**; if equivalent protection can't be verified, a `warning` is surfaced.

## Out of scope
The rewriter (model), the live eval (eval-run consumes this), wiring the apply command prompt to the
engine (a follow-up doc step). The backup is mandatory and fail-closed; no mutation without it.
