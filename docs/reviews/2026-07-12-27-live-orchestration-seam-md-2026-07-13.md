# Adversarial Review — 2026-07-12-27-live-orchestration-seam.md

- Date: 2026-07-13
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 4 (Critical 0, High 2, Medium 2, Low 0)

## Summary

The design defines an audit–verify–apply seam with deterministic envelopes, dry-run acceptance tests, and a live semantic invocation path. Its principal risks are an incomplete TOCTOU defense, a contradictory exit-code taxonomy, and underspecified failure aggregation around semantic calls.

## Findings

### 1. [High] correctness · high confidence — §4.2 Stage ordering + what flows between stages

> `verify_fn` passed to `apply_selective` is `ledger.verify` **bound** with this run's ledger +
> authorized_ranges + semantic_fn (a closure `lambda original, edits: verify(original, edits, ledger,
> authorized_ranges=..., semantic_fn=...)`), so apply re-verifies against the live original each
> attempt (apply's re-verify loop rebuilds from untouched original — the closure must not capture a
> stale revision).

The verifier closure accepts the live `original` but applies the ledger, offsets, protected spans, and authorization ranges from the earlier audited snapshot without checking that `original` still has `source_sha256`. A file changed after the seam's initial digest check but before `apply_selective` reads it can therefore be verified against stale policy data. The later concurrent-edit guard only establishes that the file has not changed since apply read it; the shown `apply_selective` signature receives no audited digest against which to compare it.

**Recommendation:** In §4.2, change the bound verifier to first require `sha256(original) == AuditResult.source_sha256` and return a typed digest-mismatch failure before calling `ledger.verify`. Also require the replace-time guard to compare the target's resolved path identity and digest directly against the audited values, not merely against apply's entry-time snapshot, and add a test that mutates the file after the run-boundary check but before apply reads it.

### 2. [High] internal-consistency · high confidence — §4.3 Overall status + exit-code mapping

> | failed | contract/input codes: `invalid_edits`, `path_mismatch`, `digest_mismatch`, bad CLI args, unreadable/non-UTF-8 input (`genre_error`, `diagnosis_error` on decode) | 3 |
> | failed | execution codes: `protected_span_error`/`diagnosis_error` (parser unavailable), `ledger_build_error`, `semantic_invocation_failed`, `apply` report `status=="error"` | 4 |
> 
> Each `code` slug is statically assigned to exactly one class in the implementation (a
> `_EXIT_CLASS` dict) — no runtime judgment.

`diagnosis_error` is assigned to both exit 3 and exit 4 even though `_EXIT_CLASS` is keyed only by the code slug and each slug is claimed to have exactly one class. One of decode failure or parser-unavailable failure will consequently receive the wrong exit code, and the proposed table-driven test cannot encode the stated behavior.

**Recommendation:** In §4.3, split `diagnosis_error` into distinct stable codes such as `diagnosis_decode_error` mapped to exit 3 and `diagnosis_parser_unavailable` mapped to exit 4. Update the StageResult vocabulary, §6 failure cases, `_EXIT_CLASS`, and case 12 accordingly.

### 3. [Medium] ambiguity · high confidence — §7 Typed invocation outcome

> The seam's `live_semantic_fn`
> passes a per-run sink; after `verify` returns, a sink status ≠ `ok` reclassifies the verify stage to
> `failed`/`code="semantic_invocation_failed"` while the verdict inside verify stays fail-closed
> ambiguous (defense-in-depth, unchanged).

A mutable per-run dictionary records only one `invocation_status`, but the design does not establish that `verify` invokes `semantic_fn` exactly once or define aggregation if it invokes it repeatedly. A later successful invocation could overwrite an earlier timeout or parse failure, silently losing the failure and violating the fail-loud requirement.

**Recommendation:** In §7, specify the semantic-call cardinality. If more than one call is possible, replace the scalar dictionary field with an append-only outcome list or a sticky worst-status accumulator that can never revert from failure to `ok`; assert a fail-then-success sequence still produces `semantic_invocation_failed`.
**Ambiguity:** The artifact does not state how many times `ledger.verify` may call `semantic_fn` or whether the sink assignment is overwrite-only.

### 4. [Medium] correctness · high confidence — §10 Testing / acceptance, case 4

> verify `blocked` (full verify_result preserved in
>    `data`), apply `aborted` with `upstream_not_ok`, `mutated=False`, file untouched, **and no backup
>    created** (verify blocks before apply is ever invoked — the no-artifact assertion is valid HERE,
>    unlike case 3).

This acceptance case requires `mutated=False` while also requiring that apply is never invoked and is represented by an aborted stage. Under the declared contract, an aborted stage has no apply report, so there is no `mutated` field to assert. Implementers must either fabricate an apply report for an operation that did not run or make the test contradict its stated assertion.

**Recommendation:** In §10 case 4, replace the `mutated=False` assertion with `apply StageResult.status == "aborted"`, `apply StageResult.data is None`, and a direct byte-for-byte source-file assertion. Reserve `mutated=False` for cases where an actual apply report exists.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._