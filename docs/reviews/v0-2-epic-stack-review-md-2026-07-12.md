# Adversarial Review — v0.2-epic-stack-review.md

- Date: 2026-07-12
- Artifact type: plan
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 5 (Critical 0, High 4, Medium 1, Low 0)

## Summary

The stack aims to connect the existing deterministic machinery to a live model-driven audit, verification, suggestion, and apply path. Its main risks are an unproven model-invocation dependency, a possibly absent end-to-end orchestration owner, and acceptance tests that can pass without demonstrating safe live behavior.

## Findings

### 1. [High] completeness · high confidence — Questions, item 4

> Missing work: is there an unlisted prerequisite — e.g. a single "live orchestration" seam that
>    actually invokes the SKILL end-to-end (the thing that makes audit/suggest run at all), without which
>    17–24 are components with no assembler?

The artifact itself identifies that no listed issue clearly owns assembly of the live path. If that seam is absent, completing the component issues will still leave the epic's model-in-the-loop goal unavailable to users and force a late integration issue or rework.

**Recommendation:** Add a dedicated live-orchestration issue immediately after the platform-feasibility proof. Define the command entry points, stage ordering, data passed between diagnosis/extractors/ledger/verification/suggestion/apply, error propagation, and an end-to-end dry-run acceptance test; make #23 and #21 depend on it.

### 2. [High] completeness · high confidence — The stack, issue #23

> #23 suggest→deterministic-verifier wiring + a live audit/suggest output-shape golden — suggest's
>    invariant-check is currently model-reported; wire it to the real verifier. Plus one live end-to-end
>    golden asserting the typed-diagnosis-record + focused-diff output shape.

The single issue mixes production verifier integration with an external-model golden, and its stated golden checks only output shape. It can pass while suggestions violate invariants, locality, protected spans, or semantic preservation, so it does not verify the safety behavior that the wiring is meant to provide.

**Recommendation:** Split #23 into verifier wiring and live end-to-end validation. Give the wiring issue deterministic tests for verifier input, verdict handling, and rejection behavior. Make the live test depend on orchestration plus #17–#20 and assert safety verdicts and blocked unsafe edits in addition to schema and diff shape.

### 3. [High] feasibility · high confidence — The stack, issue #17

> #17 semantic-verify — a real fresh-context Layer-3 `semantic_fn` (separate model invocation;
>    receives only original+revision+ledger), wired into `verify` + exercised.

This relies on an external model invocation but provides no evidence that the project's real plugin configuration can launch it, authenticate it, enforce fresh context, select a compatible model, or obtain the required structured result. #17 can therefore stall or require redesign after implementation begins.

**Recommendation:** Add a platform-feasibility prerequisite before #17 that proves one fresh-context invocation under the actual Claude Code plugin configuration, including invocation mechanism, permissions/authentication, model selection, request/response contract, timeout behavior, and a checked-in integration test or recorded fixture.

### 4. [High] scope · high confidence — The stack, issue #21

> 5. **#21 wire the apply command to the apply engine** (+ write-strategy hardening: hardlink fail-closed,
>    metadata policy, symlink no-follow, EXDEV abort, fsync-in-prod, rewrite the "in-place" spec prose to
>    "backup-first, staged, verified, atomic replace"). Engine is built+tested; command is disabled.

This combines user-facing command enablement with multiple filesystem-safety policies and a specification rewrite, but it does not define the metadata policy or acceptance behavior for each failure mode. Enabling the command before those policies are settled can expose partially hardened destructive writes; keeping it disabled until everything lands makes the issue an oversized integration bottleneck.

**Recommendation:** Split #21 into write-strategy hardening and apply-command enablement. Define exact metadata preservation, hardlink/symlink/EXDEV/fsync outcomes and failure-injection tests in the first issue; make command enablement depend on that issue, live orchestration, and an end-to-end verified dry run.

### 5. [Medium] correctness · high confidence — Pending corpus action

> fold the gathered corpus pairs into eval fixtures /
> judge-trial data / calibration corpus

Putting the same gathered pairs into calibration data and evaluation/judge-trial fixtures creates an unspecified train/test overlap. Thresholds can be tuned to the very examples later used to claim reliability, producing an optimistically biased acceptance result.

**Recommendation:** Create a separate corpus-integration issue before #25. Require provenance and license metadata, normalized direction labels, deduplication, and a fixed disjoint split for calibration versus held-out evaluation/judge trials; prohibit tuning against the held-out partitions.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._