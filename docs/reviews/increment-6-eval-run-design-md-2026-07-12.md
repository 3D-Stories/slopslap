# Adversarial Review — increment-6-eval-run-design.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 7 (Critical 0, High 3, Medium 4, Low 0)

## Summary

The artifact proposes a deterministic benchmark based on frozen, authored edit scripts, with live-model and judge runs treated as separate provenance. Its central proof claim exceeds what that benchmark establishes, and several execution dependencies and pass-two semantics remain unverified or internally unresolved.

## Findings

### 1. [High] consistency · high confidence — Context, Deliverables, and Folded decisions 4–5

> **humanizer = a declared, versioned transformation POLICY** applied consistently doc-wide WITHOUT
>    consulting slopslap's expected failures; its natural collateral edits are preserved (invariants are not
>    specially protected for the benchmark). It is labeled **representative/emulated** (the upstream tool's
>    live model output isn't run deterministically) — comparison language stays at "the documented
>    representative transformation," not a product-level claim.

This limitation conflicts with the opening success criterion that slopslap “BEATS/ties `humanizer`.” A locally authored policy that is neither executed by nor validated against the upstream product supports only a comparison with that policy. Implemented as written, the headline and DONE assertion will make an unsupported product-level benchmark claim.

**Recommendation:** Replace every `humanizer` beats/ties success statement, including the Context and pytest outcome, with “documented humanizer-inspired emulation policy,” or add a pinned upstream version plus representative recorded runs that validate the emulation before permitting product-level language.

### 2. [High] correctness · high confidence — Context and Folded decision 1

> This increment RUNS the eval loop to prove slopslap works (contract §7 DONE): slopslap clears the
> decision-rule HARD GATES on all 3 canonical fixtures, ABSTAINS on the clean-document controls, repairs
> the real `tests/fixtures/kukakuka-prd.md` with ZERO invariant violations, and BEATS/ties `humanizer` on
> the programmatic hard gates.

Frozen, manually authored outputs can prove that those particular edits pass the deterministic mechanics, but cannot prove that the stated engine produces those edits or that “slopslap works.” The artifact later acknowledges that arbitrary future Opus sessions are not covered, so CI can declare contract §7 DONE even if the live engine cannot reproduce any successful repair.

**Recommendation:** Change the opening success claim and Out of scope conclusion to say that the increment validates frozen demonstrated outputs and deterministic mechanics only. If contract §7 requires engine efficacy, add a separately specified live-engine evaluation with recorded inputs, model identity, raw outputs, capability verification, and an explicit pass criterion.

### 3. [High] internal-consistency · high confidence — Folded decisions 1, 2, and 8

> **Idempotence:** the 2nd pass RE-RUNS candidate generation on the already-repaired text (not stale
> offsets); slopslap's generator keys on the harm CONTENT, so a repaired doc yields an empty edit list.

Pass two operates on bytes different from the frozen fixture, but the design also requires every candidate to be bound to its exact input digest and describes candidates as frozen per-fixture edit scripts. It never defines a second-pass candidate artifact, digest, or deterministic generation algorithm. An implementation will either reject pass two for a digest mismatch, bypass the binding, or introduce an unfrozen generator that contradicts the claimed replay model.

**Recommendation:** In Folded decisions 1, 2, and 8, define pass two explicitly: either commit a separately SHA-256-bound empty candidate for each expected pass-one output, or specify a deterministic candidate-generation function whose input/output and digest validation apply identically on both passes. Update `candidates.py` and the results schema accordingly.
**Ambiguity:** The artifact does not say whether pass-two candidates are committed artifacts or dynamically generated records.

### 4. [Medium] completeness · high confidence — Context and Folded decision 11

> 11. **pytest INVOKES the evaluator** (not trusting committed files): all 3 slopslap canonicals clear every
>     hard gate; all controls abstain with no byte change; kukakuka invariant_violations == 0; 2nd-pass edits
>     empty; the beats/ties rule vs humanizer holds.

The artifact does not enumerate the hard gates, thresholds, canonical/control fixture identities, or expected gate result fields; it delegates those load-bearing definitions to referenced material outside the provided design. Consequently, the assertion that no gate is weakened and the DONE test's completeness are unverifiable from this artifact, and implementers cannot tell whether the test exercised the full decision rule.

**Recommendation:** Add a Primary decision-rule table listing every fixture, control, hard-gate identifier, threshold, expected disposition, and result-object field, with exact runner/verifier entry points. Make the pytest iterate over that declared inventory and assert that no expected gate is absent.
**Ambiguity:** The design names the outcomes but does not contain the decision-rule inventory needed to establish that they are complete.

### 5. [Medium] feasibility · high confidence — Engine (contract §4)

> The rewriter is **the session's Claude tier (Opus 4.8) at high effort** — I author slopslap's repairs by
> applying `skills/slopslap/SKILL.md`'s judgment. **Fable 5 = bonus-if-API; no Fable API access confirmed
> → flag `OWNER-VERIFY (Fable API)` and proceed on Opus.**

The design assumes this project can select the named Claude tier and high-effort mode, but cites no capability or manifest entry, exact-object-kind call site, feature flag, or successful spike proving that this configuration is available. Confirming that Fable is unavailable does not establish that Opus 4.8 is permitted. The provenance demonstration can therefore fail to run or silently use a different model/configuration.

**Recommendation:** Add an Engine capability subsection citing the project capability/manifest entry or a recorded spike for the exact Claude model and effort setting. Require the provenance record to assert and surface the returned model identity and effort configuration, and fail the demonstration if they differ.

### 6. [Medium] feasibility · high confidence — Question 4 and Folded decisions 9–10

> **LLM-judge = SECONDARY, recorded, non-gating:** trials through the shipped scaffold with prompts,
>    anonymized order + order-reversal, judge identity/version, raw responses, aggregation committed. Kept
>    OUTSIDE the primary DONE computation.

No capability file, exact judge call site, or spike proves that either proposed judge can be invoked under the project's configuration. The design also gives the judge no required execution-status assertion, so authentication, sandbox, quota, or model-selection failures could leave absent or stale recorded trials while the primary evaluator still reports DONE without surfacing the failed secondary evaluation.

**Recommendation:** Add a judge execution-status field with `attempted`, `completed`, exact model identity, timestamp, and surfaced error. Cite a capability/manifest entry or recorded spike for the chosen judge, and require artifact rendering to display a conspicuous `NOT RUN` or `FAILED` state rather than accepting a missing/stale judge payload.

### 7. [Medium] feasibility · medium confidence — Deliverables

> - A pytest that RE-RUNS the eval and asserts the DONE outcomes (reproducible + gated).

The artifact relies on pytest as the gating framework but provides no project configuration, dependency declaration, test-discovery path, CI invocation, or spike establishing that this test will run in the real environment. The test may exist without being installed or discovered, leaving the claimed CI gate inactive.

**Recommendation:** Extend Deliverables with the exact pytest file path, dependency/config entry, and CI command or workflow call site that executes it. Add a CI assertion demonstrating that the evaluator test is collected and cannot be skipped silently.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._