# Adversarial Review — .rawgentic-21-branch.diff

- Date: 2026-07-13
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 3 (Critical 0, High 2, Medium 1, Low 0)

## Summary

The diff hardens a backup-and-replace engine, but its final filesystem checks are not atomic with replacement. Concurrent changes can bypass the new guards, and failed xattr inspection silently permits security metadata loss.

## Findings

### 1. [High] security · high confidence — scripts/slopslap_apply/apply.py, pre-replace guard and temp-staging boundary

> +    if live_stat.st_nlink > 1:  # adv H4: a hardlink created AFTER the initial pre-backup stat
> +        return _block(report, f"source became hardlinked ({live_stat.st_nlink} links) since read; "
> +                              f"not clobbering (would orphan the other link(s))")
> +    if _sha256(live) != report["original_digest"]:
> +        return _block(report, "source changed since read (concurrent edit); not clobbering")
> +
> +    # --- atomic replace with a complete-write + read-back guard (H2) ---
> +    tmp = source + f".slopslap.tmp.{os.getpid()}"

The supposed pre-replace validation occurs before the temporary file is opened, written, chmodded, synced, and verified. A hardlink or pathname/ancestor substitution during that interval is not checked again: a late hardlink can still be orphaned, while a substituted pathname can receive the replacement intended for another file. This invalidates the claim that mid-flight links cannot slip through.

**Recommendation:** In `apply_selective`, perform the final dev/inode/content/nlink validation after staging and read-back, immediately before `os.replace`. Pin the parent directory with a directory file descriptor and use dir-fd-relative stat/open/replace operations; if hostile concurrent directory mutation remains in scope, remove the absolute fail-closed claim and refuse paths in directories where that guarantee cannot be enforced.

### 2. [High] security · high confidence — scripts/slopslap_apply/apply.py, extended-attribute inspection

> +        except OSError:
> +            pass

Failure to enumerate extended attributes is silently treated as if no attributes exist. The replacement then proceeds and can remove ACLs or security labels without even the promised warning, directly contradicting the design's fail-loud and “never silent” claims.

**Recommendation:** Change the `os.listxattr` exception path in `apply_selective` to return `status="blocked"` or `status="error"` with the original `OSError`; permit continuation only through a separately explicit unsafe override that reports metadata preservation as unverified.

### 3. [Medium] internal-consistency · high confidence — docs/planning/2026-07-13-21-apply-write-strategy-hardening.md, §8 Security

> +link-semantics breakage), `O_NOFOLLOW` reduces symlink/path-substitution TOCTOU, EXDEV-abort prevents

The security section credits `O_NOFOLLOW` with reducing pathname races even though the approach and implementation explicitly drop that control. This records a security property the change does not provide and can cause command enablement to be approved under a false threat model.

**Recommendation:** Rewrite §8 Security to state that `O_NOFOLLOW` is not used, describe the actual dev/inode check and its residual post-check race, and align the acceptance tests with the resulting supported threat model.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._