# Adversarial Review — .rawgentic-plan-26.md

- Date: 2026-07-12
- Artifact type: plan
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 5 (Critical 0, High 2, Medium 3, Low 0)

## Summary

The plan builds a validated Claude CLI invocation seam, then attempts to prove the external platform assumptions with a live spike and integrate the resulting verdicts. Its main risk is that load-bearing CLI feasibility is tested only after substantial implementation, while several security and acceptance gates lack deterministic pass criteria.

## Findings

### 1. [High] feasibility · high confidence — Task 3 sequencing

> ### Task 3: live spike — pin lockdown argv, record fixture, fill Evidence

The live proof of the external CLI, its load-bearing flags, isolation behavior, and real invocation occurs only after Tasks 1 and 2 implement and commit the contract and runner. If the installed CLI, project authentication/configuration, or lockdown flags do not work as assumed, the preceding API and subprocess implementation will require rework; the platform-feasibility spike therefore does not gate the design it is meant to validate.

**Recommendation:** Move the live flag/configuration probe to Task 1 and make its recorded pass evidence a prerequisite for implementing the contract and runner. Explicitly require a successful invocation under the project's actual authentication and configuration before freezing the public API or subprocess arguments.

### 2. [High] security · high confidence — Task 3 GREEN

> pin ONE lockdown argv via positive denial (sentinel file + machine-observable trace: attempted tool call denied / zero tool results / token absent)

The slash-separated observations do not define whether all three are required or any one is sufficient. “Zero tool results” and “token absent” can occur because the model never attempted the prohibited action, so they do not by themselves prove that tool access was denied; accepting either as positive denial could falsely certify an ineffective lockdown.

**Recommendation:** In Task 3, define one mandatory pass condition: the trace must show an attempted prohibited tool operation and an explicit platform denial, while independently confirming no sentinel creation and no sentinel-token disclosure. State that non-attempt, zero results alone, or token absence alone is inconclusive and fails the spike.
**Ambiguity:** The slash notation leaves the required conjunction and acceptable evidence unclear.

### 3. [Medium] ambiguity · high confidence — Task 4 RED→GREEN

> RED→GREEN: each verdict through normalize_semantic + verify() asserting decision (real→REJECT, ambiguous→SURFACE, clean→ACCEPT-eligible/shippable gating)

The clean-verdict expectation is not an executable oracle: “ACCEPT-eligible/shippable gating” names multiple possible states without specifying the exact verify() result or the conditions controlling it. An implementer must choose behavior, and the test can be declared green under incompatible interpretations.

**Recommendation:** In Task 4, replace “ACCEPT-eligible/shippable gating” with an explicit decision table listing the exact verify() output for clean under every relevant gate state, including which additional conditions produce ACCEPT versus a non-shippable result.
**Ambiguity:** The expected clean decision and its gate inputs are not defined.

### 4. [Medium] completeness · high confidence — Task 5 verification

> verification: whole suite (test_scaffold version assert green); README count-claims true

“README count-claims true” does not identify the claims, their authoritative sources, or a command/test that verifies them. This acceptance criterion cannot be reproduced from the plan, so inaccurate README counts can still pass the stated gate.

**Recommendation:** In Task 5, enumerate each README count claim and its source-of-truth path or calculation, then name an automated test or exact verification command that compares the documented values to those sources.

### 5. [Medium] security · high confidence — Task 3 GREEN

> sanitize + commit fixture; fill design-doc Evidence section (argv, CLI version, duration, denial trace excerpts, inherited-env remainder)

The plan commits model/CLI output and environment evidence but provides no sanitization rules or automated secret check. Tokens, credentials, usernames, home paths, or sensitive inherited variable values could therefore enter the repository despite the informal “sanitize” step.

**Recommendation:** Expand Task 3 with an explicit fixture/evidence sanitization contract: store environment variable names only, redact paths and identifiers, prohibit credential values and raw prompts where sensitive, and add an automated denylist/secret-scan test that must pass before committing the fixture and Evidence section.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._