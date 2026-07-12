# Adversarial Review — increment-2-scaffold-design.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 5 (Critical 0, High 2, Medium 3, Low 0)

## Summary

The artifact defines a safety-oriented Claude Code plugin scaffold whose correctness depends heavily on automatic discovery, always-on skill loading, and prose-level command contracts. The largest risks are unproven platform behavior and structural tests that can pass while required safety rules or command behavior are absent.

## Findings

### 1. [High] completeness · high confidence — Folded decision 8 — Scope floor

> **Scope floor = structural + safety-concept-presence tests** (manifest valid + version 0.1.0; skill/command frontmatter parse; required files exist; SKILL.md contains keystone + anti-slap + the three separate categories + apply-is-backup-gated).

The stated safety-floor test checks only a subset of the artifact's declared irreducible core. It does not require the protected-span default-deny rule, preservation invariants, five-step loop, typed-record fields, category-specific remedies, ratings, mode contracts, diagnosis cap, prohibitions, or the canonical keystone sentence in each command. The increment can therefore pass its acceptance tests while omitting most of the safety behavior the design says must never be skipped.

**Recommendation:** Expand Folded decision 8 into an explicit assertion matrix covering every item listed as irreducible in Folded decision 6, plus the canonical keystone sentence in each command and the apply/voiceprint refusal contracts. Prefer exact identifiers or parsed contract fixtures over loose substring presence checks.

### 2. [High] feasibility · high confidence — Proposed design — Progressive disclosure

> **Progressive disclosure.** SKILL.md (always loaded) carries the load-bearing judgment that must never
>   be skipped: keystone rule, the loop, the SEPARATE tell-categories + permitted responses, the two
>   ratings, protected-span default-deny, behavioral limits (≤3 diagnoses/500w; idempotence; the
>   anti-slap first instruction).

The safety architecture assumes SKILL.md is always loaded, but the artifact provides no project capability/manifest evidence, exact command-to-skill invocation, or spike proving that Claude Code loads this skill for every command under the project's real configuration. If auto-loading does not occur, the thin commands can execute without the keystone rule, protected-span policy, typed diagnoses, or behavioral limits.

**Recommendation:** In Proposed design, replace the bare “always loaded” assumption with the exact supported invocation mechanism for each command and cite a project-local capability/manifest entry, exact-object-kind working call site, or scaffold spike. Add a structural test that resolves every command to `skills/slopslap/SKILL.md` and fails visibly when loading cannot be confirmed.

### 3. [Medium] ambiguity · high confidence — Folded decision 3 — apply fails closed

> **apply fails closed in MVP:** states mutation is unavailable (backup gate not built), performs **no implicit audit**, points explicitly to `/slopslap:suggest $ARGUMENTS`. No silent fallback (would mislead automation about whether a mutation happened).

The design specifies human-readable refusal text but not the command's machine-observable failure semantics, such as a non-success status or structured result. Automation may receive a successfully completed command containing refusal prose and still record the requested mutation as successful—the exact misleading outcome this decision intends to prevent.

**Recommendation:** In Folded decision 3 and `commands/apply.md`, define a stable failure contract: a non-success command status if the platform supports it, otherwise a mandatory structured sentinel such as `status: mutation_unavailable`, plus an assertion or surfaced log proving that no write occurred. Add that contract to the structural or command-shape tests.

### 4. [Medium] feasibility · high confidence — Deliverables — references/engine.md

> `references/engine.md` (default best-available Claude at high
>   effort; Fable 5 = bonus-if-API).

The design depends on selecting a “best-available Claude” model, a high-effort setting, and optionally Fable 5, but supplies no capability file, feature flag, sandbox configuration, exact model-selection call site, or spike proving that a Claude Code plugin can control those choices in this project. An implementer cannot determine whether this is executable policy or merely advisory text, so runtime behavior may silently use a different engine or effort level.

**Recommendation:** In `references/engine.md` deliverable requirements, define whether engine selection is enforceable or advisory. For enforceable settings, cite the exact project capability/config and require a surfaced assertion or log of the selected model and effort; otherwise state explicitly that the plugin cannot select them and remove them as runtime guarantees.

### 5. [Medium] internal-consistency · high confidence — Folded decisions 1 and 8; Deliverables — tell-taxonomy.md

> Every diagnosis is a typed record:
>    `{category (exactly one of: emptiness | laundering | simulation | lexical_structural | voice_discontinuity | epistemic_distortion), evidence_span, demonstrated_harm + reader/requirement impact, editorial_harm rating, diagnosis_confidence rating, permitted_response}`.

The canonical diagnosis contract defines six categories, while the deliverables and safety test repeatedly require “the 3 categories” or “the three separate categories.” It is therefore unclear whether the taxonomy has three top-level classes, six record values, or whether only three of the six must be preserved by tests. Implementations and fixtures can consequently disagree on valid category values.

**Recommendation:** In Folded decision 1, define an explicit hierarchy if three categories are top-level groupings, including the mapping of all six record values. Otherwise change every “3 categories” and “three separate categories” occurrence, including the structural-test requirement, to “six categories” and enumerate the same six identifiers.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._