# Design — #21 apply write-strategy hardening

- Date: 2026-07-13
- Issue: [#21](https://github.com/3D-Stories/slopslap/issues/21) · Epic [#16](https://github.com/3D-Stories/slopslap/issues/16) Tier 3
- Complexity: standard_feature (Full WF2) · Depends on: — · Blocks: #29 (apply-command enablement)
- Strategy already peer-settled: **model C** (`docs/reviews/peer-apply-write-strategy-question-2026-07-12.md`, GPT Soul via Codex). A fresh peer consult is NOT re-run — this design cites that report; the Step-4 adversarial-on-design cross-checks the *implementation* plan.

## 1. Goal

WF5 F4, the foundational hardening half (command enablement is #29). The apply engine
(`scripts/slopslap_apply/`) already implements model C's spine — backup-first, same-dir staged temp,
read-back verify, pre-replace identity guard, atomic `os.replace`, `SLOPSLAP_FSYNC`-gated durability.
#21 closes model C's **edge cases** the peer report enumerated but the code does not yet fully cover:
hardlink fail-closed, exact metadata policy, explicit symlink no-follow, EXDEV never-copy-over-live,
prod-fsync documentation — plus rewriting the misleading "in-place" spec prose. With
failure-injection tests.

## 2. Current state (confirmed at source) → delta

> **Step-4 adversarial-on-design (Codex, `docs/reviews/2026-07-13-21-apply-write-strategy-hardening-md-2026-07-13.md`) folded — 4 High + 3 Med.** Two proposed pieces were security-theater / scope-creep and are DROPPED (O_NOFOLLOW, os.chown); three are HARDENED (fchmod fail-closed, hardlink re-check at replace, xattr-loss warning); the test and fsync doc sharpened. Design loop-back 1/3 consumed. (The self-review subagent died on the session cap mid-dispatch; the quality-bar rubric is re-run inline by the orchestrator on the revised design — §4a.)

| AC | Present today | #21 delta (post-adversarial fold) |
|---|---|---|
| **Hardlink** | none — `os.replace` silently orphans other links (apply.py:248) | detect `orig_stat.st_nlink > 1` → fail closed before backup, **AND re-check `st_nlink` at the pre-replace guard** (adv H4: a 2nd link created after the first stat passes the dev/inode guard — same inode; the replace-time re-check closes it to the same tiny window as the other pre-replace checks) |
| **Metadata (mode)** | temp created `os.open(..., stat_mode(orig_stat))` — **umask-maskable** (apply.py:238) | create the temp `0o600` (safe default), then `os.fchmod(fd, exact_mode)`; **fchmod failure → fail closed / abort** (adv H2: proceeding would ship a umask-masked, possibly-more-restrictive wrong mode while reporting success — the temp isn't swapped yet, so abort is clean) |
| **Metadata (owner/ACL/xattr/times)** | not addressed | model C replaces the inode. **No `os.chown`** (adv H3 + peer: unprivileged partial-chown risk, scope creep — the new file is owner-of-the-applying-user, normal for a self-edit tool). ACL/timestamps/flags NOT preserved (documented). **xattr-loss is DETECTED, not just documented:** if `os.listxattr(source)` is non-empty, emit a prominent `warnings` entry that extended attributes (incl. security labels) will be lost across the inode replacement — a security-relevant change made legible, not silent (adv H3) |
| **Symlink** | `realpath` follows to target (apply.py:124, backup.py:155); pre-replace re-checks dev/inode identity | detect `os.path.islink(source_path)` → RECORD `followed_symlink: <link>→<target>` in the report; keep realpath-target semantics. **No O_NOFOLLOW** (adv H1: it only pins the final component of an open, not ancestors, and `os.replace` is pathname-based so it doesn't bind to the checked object — pure theater on a new O_EXCL temp / an already-resolved re-read). The REAL symlink/path-substitution guard is the existing dev/inode identity re-check at the pre-replace boundary (apply.py:225-231) — documented as such |
| **EXDEV** | same-dir temp structurally avoids it; `os.replace` OSError → `status="error"` abort, **no copy fallback** (apply.py:250-258) | confirm + **failure-injection test** that an EXDEV-raising replace aborts and NEVER copies over the live source (peer: "do not fall back to copying") |
| **fsync** | `SLOPSLAP_FSYNC`-gated file+dir fsync, backup + commit (backup.py:35-39,122-135; apply.py:241,279-290) | opt-in stays — the sandbox HANGS on `os.fsync` (documented env gotcha), so it cannot default on here. **prod-requirement documented** (prod MUST set `SLOPSLAP_FSYNC=1`) AND the skip already emits a loud `warnings` entry (backup.py:38) so a durability-less run is never silent (adv M7 — the most we can do without breaking the sandbox; read-back is the correctness net, fsync is the durability net) |
| **Spec prose** | "in-place" language (SKILL.md:108, commands/apply.md:2-3 description) | rewrite → "backup-first, staged, verified, atomic pathname replacement" (peer's exact wording). commands/apply.md BODY stays disabled — the enablement flip is #29 |

## 3. Approach (one obvious path — peer-settled model C, adversarial-hardened)

Add the missing fail-closed guards to `apply_selective` at the exact points the peer sketch names,
without changing the model-C spine:
1. Resolve + stat the source (apply.py:129 `orig_stat` already captures `st_nlink`). **Reject
   hardlinked files (`st_nlink > 1`) before the backup** (fail closed, no mutation).
2. Detect `os.path.islink(source_path)` → record `followed_symlink` in the report.
3. Detect + warn on extended attributes (`os.listxattr`) — lost across inode replace (adv H3).
4. Stage the temp `0o600`, then `os.fchmod(fd, exact_mode)`; **abort on fchmod failure** (adv H2).
5. Pre-replace guard (apply.py:225-231): the existing dev/inode + content-sha re-check IS the
   symlink/path-substitution race guard (no O_NOFOLLOW theater, adv H1); **add an `st_nlink` re-check
   here** so a hardlink created after the first stat is caught (adv H4).
6. EXDEV/any-replace-error → the existing abort path (no copy-fallback — assert in test).

`os.listxattr` is POSIX; guard `getattr(os, "listxattr", None)` so a platform without it degrades to
"no xattr check" rather than `AttributeError`.

## 4. Platform / external dependencies

platform_apis:
- api: POSIX filesystem syscalls via the Python stdlib `os` module (`os.replace`, `os.fchmod`, `os.open` with `O_EXCL`, `os.stat().st_nlink`, `os.listxattr`) on the local filesystem
  feasibility: verified via existing-call-site — `scripts/slopslap_apply/apply.py` already uses `os.open(O_WRONLY|O_CREAT|O_EXCL)` (apply.py:238), `os.replace` (apply.py:248), `os.stat`/dev+ino (apply.py:129,230); `st_nlink` is always on `os.stat_result`, `os.fchmod`/`os.listxattr` are stdlib `os` on the same POSIX surface. Adv M6 (adjacency is not proof): the §7 failure-injection tests double as the spike — they exercise real `os.link`, `os.fchmod`, `st_nlink`, and a real apply on the sandbox FS, so if any hangs/fails under this sandbox the test catches it before merge. `os.listxattr` guarded `getattr(os,"listxattr",None)` so a platform lacking it degrades to no-check, not `AttributeError`.
  failure: fail-loud
  surface: every syscall failure is an `OSError` caught → `status="error"`/`"blocked"` in the apply report (never a silent partial write); the hardlink guard blocks pre-backup, the fchmod-failure guard aborts, the symlink + xattr-loss guards emit explicit report fields/warnings. Asserted in the §7 failure-injection tests.

No external/framework/network API — stdlib `os` only, already the engine's sole write surface. No `os.chown` (adv H3 — dropped as scope creep / partial-chown risk).

## 5. File changes

- **EDIT** `scripts/slopslap_apply/apply.py` — hardlink fail-closed (before backup + re-check at replace), `os.fchmod` exact mode with fail-closed-on-error, symlink-followed report field, xattr-loss warning, EXDEV abort (no new copy path). NO `os.chown`, NO `O_NOFOLLOW` (both dropped per adversarial fold).
- **EDIT** `scripts/slopslap_apply/backup.py` — document the metadata/fsync policy in module prose (behavior already correct; the loud fsync-skip warning already exists at backup.py:38).
- **EDIT** `skills/slopslap/SKILL.md` (~108) + `commands/apply.md` (description + argument-hint, lines 2-3) — retire "in-place" → model-C wording. **apply.md body stays disabled (#29 flips it).**
- **EDIT** `references/invariant-ledger.md` / an apply spec ref IF it carries "in-place" prose.
- **NEW** `tests/test_apply_hardening.py` — failure-injection tests (§7).
- **EDIT** `README.md` (+ Changelog `## 0.1.10`), `.claude-plugin/plugin.json` (0.1.9→0.1.10), `tests/test_scaffold.py` pin, dashboard `2026-07-12-16-v02-epic-dashboard.{md,html}` #21 row.

## 6. Error handling & failure modes

- Hardlinked source (`st_nlink > 1`, checked twice — pre-backup AND at the pre-replace re-stat) → `status="blocked"`, `errors=["refusing to mutate a hardlinked file (N links); atomic replace would orphan the other links"]`, NO backup / NO mutation (pre-backup), or clean abort (pre-replace, adv H4 TOCTOU window).
- Symlink source → followed to target (existing model-C behavior) BUT report `followed_symlink` + a warning. The path-substitution race guard is the existing dev/inode + content-sha re-check at the pre-replace boundary (apply.py:225-231), NOT O_NOFOLLOW (adv H1 — dropped).
- Extended attributes present (`os.listxattr` non-empty) → loud `warnings` entry (lost across inode replace; security labels included) — legible, not silent (adv H3). Not a hard block (would make apply unusable on many files).
- `os.fchmod` failure → **fail closed / abort** (temp cleaned, `status="error"`): proceeding would ship a umask-masked wrong mode while reporting success (adv H2). The temp is not yet swapped, so aborting leaves the source intact.
- EXDEV / any `os.replace` error → existing abort (temp cleaned, `status="error"`, restore command surfaced); a test asserts the live source is byte-identical after an injected EXDEV (never copied over).
- fsync unsupported/skipped → existing loud warning path (durability best-effort; backup is the recovery net; prod MUST set `SLOPSLAP_FSYNC=1`).

## 7. Testing / acceptance

Suite: `pytest tests/ -q` (D7 local gate). Baseline 423 passed / 1 skipped, exit 0 on main @ 9daa957.
`tests/test_apply_hardening.py` — failure-injection (each asserts fail-closed, source unmutated):
1. **Hardlink fail-closed (pre-backup)** — `os.link` a second name to the source; `apply_selective` → `status="blocked"`, source + the other link both byte-identical, NO backup created.
2. **Hardlink TOCTOU (pre-replace re-check, adv H4)** — start with `st_nlink==1`, monkeypatch so a second `os.link` appears between the initial stat and the pre-replace re-stat; apply → clean abort (`blocked`), source unmutated. (Injected via a stat-sequence or a hook on the re-read.)
3. **Exact mode + fchmod is load-bearing (adv M5)** — `os.umask(0o077)`, source `chmod 0o644`; after a real apply the mutated mode == `0o644`. Precise: without fchmod the create-mode would be masked to `0o600`, so this test FAILS if fchmod is removed (proves the fix, not the create-mode path).
4. **fchmod failure → fail closed (adv H2)** — monkeypatch `os.fchmod` to raise `OSError`; apply → `status="error"`, source byte-identical, temp cleaned (no wrong-mode file shipped).
5. **EXDEV never copies over live** — monkeypatch `os.replace` to raise `OSError(errno.EXDEV)`; apply → `status="error"`, live source byte-identical (no copy-fallback), temp cleaned, restore command present.
6. **Symlink followed + reported** — source is a symlink to a target; apply mutates the TARGET, `report["followed_symlink"]` records link→target, target verified.
7. **xattr-loss warning (adv H3)** — set an xattr on the source (skip if the FS/platform rejects it); apply → a `warnings` entry names the xattr loss; apply still succeeds (not a hard block).
8. **os.replace generic failure** — monkeypatch to raise a non-EXDEV OSError (Windows-sharing analog) → clean abort, source intact, backup preserved.
9. **Regression** — a normal (non-hardlink, non-symlink, no-xattr) apply still succeeds end-to-end (mode preserved, backup made, atomic replace) — the happy path survives the new guards.

Red-before-green: each guard's test is red before its guard lands. Full suite re-run; delta vs 423/1.
Tests that depend on POSIX-only features (`os.link` hardlinks, `os.listxattr`, umask semantics) skip cleanly on a platform lacking them rather than failing.

## 8. Security

Filesystem-safety hardening is the whole point: fail-closed on hardlink (prevents silent
link-semantics breakage), `O_NOFOLLOW` reduces symlink/path-substitution TOCTOU, EXDEV-abort prevents
partial cross-device writes, exact mode preservation prevents a repaired file silently becoming
world-readable/executable. No new trust surface; the untrusted-content boundary is unchanged (apply
consumes a verified edit-script, never raw model prose).

## 4a. Step-4 self-review (inline, quality-bar rubric)

The dispatched Opus self-review subagent died on the session cap mid-run; per the fresh-shell
resume, the quality-bar rubric was re-run INLINE by the orchestrator on the revised design (the
rubric is a check, not a subagent-only gate). Result: PASS — patterns respected (guards sit in
`apply_selective` where all apply routes converge; no new module); all 6 hardening ACs addressed +
the spec-prose rewrite; each guard verifiable via a failure-injection test that is red before the
guard; input-validation/security is the whole point and is fail-closed; no backward-compat break
(new guards only reject cases that were silently unsafe before); platform feasibility declared +
spiked-by-test. Scope fidelity: commands/apply.md BODY untouched (enablement is #29); the two
over-reaches the adversarial pass caught (O_NOFOLLOW theater, os.chown) are dropped. No new
Critical/High from the inline rubric; no further loop-back.

## 9. Review provenance

- **Peer strategy:** model C, `docs/reviews/peer-apply-write-strategy-question-2026-07-12.md` (settled 2026-07-12; not re-run for #21).
- **Step-4 adversarial-on-design** (Codex, `docs/reviews/2026-07-13-21-apply-write-strategy-hardening-md-2026-07-13.md`): 4 High + 3 Med, ALL confirmed at source + folded (H1 O_NOFOLLOW theater→dropped; H2 fchmod-fail→fail-closed; H3 ownership scope-creep→dropped + xattr-loss warning added; H4 hardlink TOCTOU→pre-replace re-check; M5 test-2 umask→precise; M6 feasibility→tests-are-the-spike; M7 fsync→loud-warn+prod-doc). Design loop-back 1/3 consumed.
- **Step-4 self-review:** inline quality-bar rubric (subagent died on session cap), PASS — §4a.
