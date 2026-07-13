# Adversarial Review — 2026-07-13-21-apply-write-strategy-hardening.md

- Date: 2026-07-13
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 7 (Critical 0, High 4, Medium 3, Low 0)

## Summary

The design hardens atomic pathname replacement, but several stated guarantees are not achieved by the proposed checks. The principal risks are silent loss of security metadata, TOCTOU gaps around hardlinks and symlinked path components, and platform capabilities that are inferred rather than demonstrated for the project’s actual runtime configuration.

## Findings

### 1. [High] correctness · high confidence — Section 6, Symlink source failure mode

> `O_NOFOLLOW` on the concrete-path opens guards against a component/target swap mid-run.

`O_NOFOLLOW` protects only the final pathname component of the individual open; it does not pin ancestor components, and it does not bind the later pathname-based `os.replace` to the object that was checked. A parent-directory substitution after verification can therefore redirect the commit despite the claimed guard.

**Recommendation:** Replace this claim in Section 6 with the actual limited guarantee. For component-swap resistance, anchor operations to verified directory descriptors and use dir-fd-relative open/stat/replace operations where supported, with an explicit fail-closed fallback when that capability is unavailable.

### 2. [High] internal-consistency · high confidence — Section 6, Error handling & failure modes

> - `os.fchmod` failure (rare) → non-fatal warning (the content is correct; mode is best-effort), never blocks a verified apply.

This contradicts the stated exact-mode policy. Because the initial create mode is umask-maskable, proceeding after fchmod fails can replace the live file with a more restrictive and operationally incorrect mode while reporting a successful verified apply.

**Recommendation:** Change Section 6 so an `os.fchmod` failure aborts before `os.replace`, cleans the temp, and reports status="error". Reserve non-fatal behavior only for metadata explicitly declared optional.

### 3. [High] security · high confidence — Section 2, Metadata (owner/ACL/xattr/times)

> **documented policy:** model C replaces the inode → ownership best-effort (only if privileged; failure non-fatal + warned), ACL/xattr/timestamps/flags NOT preserved (named limitation in the report + spec)

A successful apply can change the owner and unconditionally discard access-control or security metadata. Files protected by ACLs or security xattrs can therefore acquire different access semantics after replacement; documenting and warning about that does not prevent the security change.

**Recommendation:** Change the Metadata policy in Sections 2 and 6 to fail closed when ownership or security-relevant ACLs/xattrs cannot be restored and verified. Alternatively, explicitly restrict apply to files without such metadata, detect that condition before backup, and return status="blocked".

### 4. [High] security · high confidence — Section 3, Approach

> Ordering (peer sketch step 1):
> resolve + stat the source, capture `st_nlink`; **reject hardlinked files (`st_nlink > 1`) before the
> backup** (fail closed, no mutation).

The one-time link-count check does not establish fail-closed hardlink behavior under concurrent mutation. A second hardlink can be created after this stat but before replacement; the identity guard can still pass because device and inode are unchanged, after which replacement silently leaves the new link on the old inode.

**Recommendation:** In Section 3, add an `fstat` link-count recheck immediately before commit and explicitly document the remaining race. If concurrent directory mutation is in the threat model, require an exclusive trusted-directory condition or a platform-specific mechanism that makes the check-and-replace guarantee enforceable; otherwise narrow the stated guarantee.

### 5. [Medium] completeness · high confidence — Section 7, test 2

> 2. **Exact mode preservation** — source `chmod 0o640` under a non-restrictive umask; after a real apply the mutated file mode == 0o640 (proves `fchmod`, not umask-masked create-mode).

A non-restrictive umask makes the initial `os.open(..., 0o640)` produce mode 0o640 even if `fchmod` is absent, so this test does not prove the new behavior and can pass with the original bug unchanged.

**Recommendation:** Change test 2 in Section 7 to apply under a restrictive umask such as `0o077` while expecting the final mode to remain `0o640`. Add a separate injected-`fchmod`-failure test that verifies commit is aborted under the corrected failure policy.

### 6. [Medium] feasibility · high confidence — Section 4, Platform / external dependencies

> feasibility: verified via existing-call-site — `scripts/slopslap_apply/apply.py` already uses `os.open(O_WRONLY|O_CREAT|O_EXCL)` (apply.py:238), `os.replace` (apply.py:248), `os.stat`/dev+ino (apply.py:129,230), and `scripts/slopslap_apply/backup.py` uses the same family; `st_nlink` and `os.fchmod` are stdlib `os` on the same POSIX surface. `O_NOFOLLOW` is POSIX-only → accessed as `getattr(os, "O_NOFOLLOW", 0)` so a Windows build degrades to 0 (no-op flag) rather than `AttributeError`.

Adjacent calls from the same module do not prove that the newly required `fchmod`, `st_nlink`, `O_NOFOLLOW`, or ownership-changing operation work under this project's actual OS, sandbox, and CI configuration. The artifact cites no capability/manifest evidence, exact existing call site, or spike for them; it also admits that Windows silently disables `O_NOFOLLOW`, without surfacing that loss of protection in the report.

**Recommendation:** Expand Section 4 with evidence from the project's actual capability/CI configuration or a targeted spike for every new operation, including the ownership API. Add a `nofollow_enforced` report field and warning, plus a test asserting the warning when the flag is unavailable; define unsupported platforms as blocked if no-follow is required.
**Ambiguity:** The provided artifact does not identify the project's permitted OS, filesystem, sandbox capabilities, or CI matrix.

### 7. [Medium] feasibility · high confidence — Section 2, fsync delta

> **prod-requirement documented** (prod MUST set `SLOPSLAP_FSYNC=1`; the opt-in default is a sandbox workaround, read-back is the correctness net not the durability net)

The design does not cite a production capability or deployment configuration that actually sets this variable, and it leaves the default off. Implementing only documentation therefore permits production applies to run without the durability requirement, with no stated assertion that surfaces the misconfiguration.

**Recommendation:** Add the production configuration source to Section 4 and an acceptance test proving it sets `SLOPSLAP_FSYNC=1`. If production cannot be reliably identified, make durability an explicit command/config mode and fail loudly when a production invocation lacks it.
**Ambiguity:** No production manifest, launcher, or environment configuration is included in the artifact.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._