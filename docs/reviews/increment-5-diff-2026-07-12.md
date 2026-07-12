# Adversarial Review — increment-5.diff

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 6 (Critical 0, High 5, Medium 1, Low 0)

## Summary

The change implements backup-gated selective file mutation, but several validation and write paths do not fail closed as designed. Invalid verifier attribution can permit rejected edits, and a short write can replace the source with incomplete data.

## Findings

### 1. [High] completeness · high confidence — scripts/slopslap_apply/apply.py, re-verification

> +    reverify = verify_fn(original, subset)  # candidate built from the UNTOUCHED original
> +    report["verification_attempts"] = 2  # initial + re-verify
> +    report["final_verification"] = reverify.get("decision")
> +
> +    if not subset:
> +        # nothing safe to apply: a no-op only if the ORIGINAL itself verifies acceptably
> +        report.update(status="no_op" if reverify.get("decision") == "ACCEPT" else "blocked",
> +                      mutated=False, final_digest=_sha256(original))
> +        return report
> +    if reverify.get("decision") != "ACCEPT":
> +        report.update(status="blocked", mutated=False,
> +                      errors=["selected subset does not re-verify ACCEPT (dependent hunk removed)"])
> +        return report

The promised bounded monotonic re-verification loop is not implemented. There is exactly one subset verification, and any attributable new rejection blocks the entire operation rather than removing the newly failing dependency group and retrying. Consequently, a remaining safe subset is not applied, defeating the stated selective rollback behavior.

**Recommendation:** Replace this single re-verification branch with the specified loop: rebuild from the untouched original, validate each result, remove every group attributable to new blocking findings, retry up to `#groups + 1`, and block only on unattributed failure, inconsistency, or no progress.

### 2. [High] correctness · high confidence — scripts/slopslap_apply/apply.py, atomic replace

> +        os.write(fd, candidate)
> +        if os.environ.get("SLOPSLAP_FSYNC") == "1":
> +            os.fsync(fd)  # opt-in crash durability; some sandboxes block on fsync
> +        finally:
> +            os.close(fd)
> +        os.replace(tmp, source)

A single `os.write` is not guaranteed to write the complete candidate. If it returns a short count without raising, the code closes and atomically replaces the source with the truncated temporary file, corrupting the source despite the candidate having passed verification.

**Recommendation:** In `apply.py` under `# --- atomic replace ---`, replace the single `os.write` with a loop that advances until every candidate byte is written, treating zero progress as an error. Read back and hash the completed temporary file against `candidate` before `os.replace`.

### 3. [High] correctness · high confidence — scripts/slopslap_apply/apply.py, `_components` and initial verification handling

> +    for f in findings:
> +        hs = [h for h in f.get("implicated_hunk_ids", []) if h in parent]
> +        for a, b in zip(hs, hs[1:]):
> +            parent[find(a)] = find(b)

Unknown implicated hunk IDs are silently discarded. A blocking finding attributed only to an unknown ID is therefore considered attributed, blocks no real component, and can allow all edits to be applied if the subsequent verifier returns ACCEPT. This contradicts the stated rule that missing or unknown attribution must block partial apply.

**Recommendation:** Validate every finding's `implicated_hunk_ids` against the complete initial hunk-ID set before `_components` or `_blocking_hunks`. Return `blocked` for missing, unknown, duplicate-contradictory, or malformed attribution instead of filtering it out.

### 4. [High] correctness · high confidence — scripts/slopslap_apply/apply.py, initial verify

> +    initial = verify_fn(original, all_edits)
> +    findings = initial.get("findings", [])
> +    if _has_unattributed_block(findings):

The initial verifier result's required `decision` is never validated. A result with no decision, or an initial `REJECT`/`ASK`/`SURFACE` without a recognized blocking finding, proceeds to selection and can mutate when the second verification says ACCEPT. This directly violates R3's requirement that a missing decision block without mutation.

**Recommendation:** Immediately after the initial `verify_fn` call, validate that the result is a dictionary with a recognized `decision` and well-formed findings. Return `blocked` unless the decision and findings form a permitted, internally consistent selection result; also catch verifier exceptions and return a structured blocked report.

### 5. [High] security · high confidence — scripts/slopslap_apply/apply.py, pre-replace concurrency guard

> +    try:
> +        with open(source, "rb") as fh:
> +            live = fh.read()
> +    except OSError as err:
> +        report.update(status="blocked", errors=[f"re-read failed: {err}"])
> +        return report
> +    if _sha256(live) != report["original_digest"]:
> +        report.update(status="blocked", mutated=False,
> +                      errors=["source changed since read (concurrent edit); not clobbering"])
> +        return report
> +
> +    # --- atomic replace ---
> +    tmp = source + f".slopslap.tmp.{os.getpid()}"

The code rechecks only content, not the resolved source identity required by R4. If the resolved pathname is replaced or redirected to another equal-content object after the initial resolution, the digest guard passes and `os.replace` overwrites that different object. The backup still refers to the original resolved source identity, so restoration can target the wrong boundary as well.

**Recommendation:** Capture the resolved path plus stable identity information such as device/inode at the initial read, then immediately before replacement re-run `realpath`, open without following newly introduced symlinks where supported, and compare identity as well as content. Abort if either the resolved path or object identity changed.

### 6. [Medium] correctness · high confidence — scripts/slopslap_apply/backup.py, restore metadata

> +    restore_argv = ["cp", "--", path, source]
> +    restore_command = "cp -- " + shlex.quote(path) + " " + shlex.quote(source)

The restore metadata is always POSIX `cp` syntax even though the design requires platform-specific commands and explicitly claims Windows handling. On a normal Windows installation this command and argv are unusable, so the reported recovery procedure fails on a supported path.

**Recommendation:** In `backup.py`, construct restore metadata by platform: retain `cp --` for POSIX and return a PowerShell `Copy-Item -LiteralPath ... -Force` command and corresponding executable argv on Windows. Add a Windows-specific unit test for quoting and argv shape.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._