# Adversarial Review — .rawgentic-29-branch.diff

- Date: 2026-07-13
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 4 (Critical 0, High 3, Medium 1, Low 0)

## Summary

The change enables real file mutation through both the CLI and library seams. It introduces a default semantic fail-open, contradicts its claimed single mutation path, leaves the untrusted-target delimiter escapable, and does not establish its no-mutation guarantee for execution failures.

## Findings

### 1. [High] correctness · high confidence — commands/apply.md, final paragraph

> +Offline (default, `SLOPSLAP_LIVE` unset) the Layer-3 adversarial semantic verdict is a clean stub, so
> +a green apply proves the deterministic layers (numbers/units/modality/negation/conditions/protected
> +spans) held; set `SLOPSLAP_LIVE=1` for a real semantic pass.

Real mutation is enabled while the semantic layer defaults to an unconditional clean result. An edit within an authorized range that preserves the listed syntactic invariants but changes meaning can therefore receive exit 0 and replace the source without any adversarial semantic verification, despite the earlier claim that the 3-layer verifier must pass.

**Recommendation:** Change apply mode to fail closed unless Layer 3 returns a real semantic verdict. Require `SLOPSLAP_LIVE=1` or an explicitly supplied non-stub semantic verifier when `write=True`; reserve the clean stub for `run` only, and add a test proving mutating apply rejects stub mode.

### 2. [High] internal-consistency · high confidence — commands/apply.md, How to apply step 3; scripts/slopslap_assemble/assemble.py run_candidate

> +3. **Apply for real** with the explicit `apply` subcommand (this is the ONLY mutating path):

The stated single mutation boundary is false: the changed `assemble(..., write=True)` and `run_candidate(..., write=True)` library seams also mutate, as the new tests explicitly demonstrate. In-process callers can bypass the supposedly mandatory explicit `apply` subcommand and trigger writes through a boolean parameter.

**Recommendation:** Either make mutation capability private to the `apply` CLI handler and remove or reject public `write=True` calls, or revise commands/apply.md and the parser comments to disclose every mutating entry point and require an explicit capability/token at the library boundary.

### 3. [High] security · medium confidence — commands/apply.md, target interpolation block

> +<<<SLOPSLAP_TARGET
> +$ARGUMENTS
> +SLOPSLAP_TARGET

Raw untrusted arguments are interpolated between a predictable, unescaped closing marker. A multiline argument containing `SLOPSLAP_TARGET` can appear to terminate the data region and place following attacker-controlled text outside it, undermining the prompt boundary immediately before a file-mutating workflow.

**Recommendation:** In commands/apply.md, replace raw marker interpolation with a length-delimited or encoded argument representation that cannot contain the terminator; alternatively validate `$ARGUMENTS` as a single pathname and reject newlines or marker tokens before using it.

### 4. [Medium] completeness · medium confidence — scripts/slopslap_assemble/assemble.py, run_candidate exception handler

> +    except Exception as err:  # noqa: BLE001 - the seam never raises past a stage (§4.3)
> +        apply_stage = StageResult("apply", "failed", "apply_error",
> +                                  f"apply raised {type(err).__name__}", data=None,

The newly mutating wrapper converts every engine exception into an execution-failure result without checking whether replacement already occurred or restoring the backup. Because the apply engine implementation is absent from the artifact, the documented guarantee that exit 4 means nothing mutated is unverifiable; an exception after replacement could report failure with `data=None` while leaving the source changed.

**Recommendation:** In run_candidate, have apply_selective return or raise structured commit-state information, then verify the source state and restore from the verified backup on any post-commit exception. Add a fault-injection test that raises after pathname replacement and proves exit 4 leaves the original bytes restored.
**Ambiguity:** The provided diff does not include apply_selective, so whether it can raise after mutation cannot be determined from the artifact.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._