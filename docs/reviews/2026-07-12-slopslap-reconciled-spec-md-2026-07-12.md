# Adversarial Review — 2026-07-12-slopslap-reconciled-spec.md

- Date: 2026-07-12
- Artifact type: spec
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 8 (Critical 0, High 4, Medium 4, Low 0)

## Summary

The artifact specifies a prose-repair plugin with guarded edits, invariant-based verification, Markdown-aware scanning, and staged voiceprint support. Several load-bearing contracts remain contradictory or insufficiently defined, particularly coordinates, evaluation acceptance, capability output, and backup containment.

## Findings

### 1. [High] completeness · high confidence — Evals

> **LLM-judge (blinded A/B vs humanizer
> AND vs original-unchanged, must cite spans):** meaning preservation; unsupported-claim
> introduction; actor/responsibility preservation; unresolved-intent stays visible;
> editorial-cost reduction; voice distance from samples; genre fitness; edit locality/justification;
> seeded defect fixed WITHOUT normalizing surrounding distinctive prose.

The evaluation lists judgment dimensions but defines no scale, aggregation method, trial count, tie handling, or pass threshold. Consequently, the requirements to beat `humanizer`, allow unchanged originals to win, and select among model tiers cannot produce a reproducible acceptance decision and will likely require redesign after results arrive.

**Recommendation:** Add an `Evaluation decision rule` subsection defining per-dimension scoring, hard-failure overrides, number of blinded trials, aggregation and tie rules, fixture-level thresholds, and the exact criterion for beating each baseline and selecting an engine.

### 2. [High] correctness · high confidence — Scanner dependency — Machine-readable capability contract

> emits `{status:"capability_unavailable", format:"markdown", capability:"markdown_commonmark",
>   metrics:null}` + a stderr notice + a dedicated advisory-skip exit code

The specified machine-readable payload is not valid JSON because its property names are unquoted. A caller implementing the contract literally will fail JSON parsing precisely on the capability-unavailable path and may treat an advisory skip as a scanner defect.

**Recommendation:** Replace the Scanner dependency payload with valid JSON: `{"status":"capability_unavailable","format":"markdown","capability":"markdown_commonmark","metrics":null}`, and define its schema and exact exit-code value.

### 3. [High] internal-consistency · high confidence — Invariant ledger

> Each entry: id, kind, source{start_line,end_line,text_hash}, the extracted content
> (subject/predicate/object/modality/qualifiers as applicable), preservation, confidence.
> Plus protected_spans[] with offsets + sha256.
> **Canonical coordinates (round-3 fix):** ALL positions — ledger sources, protected-span
> offsets, authorized edit ranges, post-edit proposition matching — use **original-byte
> offsets** as the single canonical system

The ledger schema represents source locations as line numbers, while the canonical-coordinate rule requires every ledger source position to use original-byte offsets. Implementing the declared schema leaves verification and selective rollback without the required byte coordinates, risking attribution or rollback of the wrong passage after length-changing edits.

**Recommendation:** Change the Invariant ledger schema to define `source{start_byte,end_byte,text_hash}`. If line numbers are needed for display, add them as explicitly derived, non-canonical fields and define byte indexing and encoding.

### 4. [High] security · high confidence — Output modes — apply

> **Takes a mandatory pre-mutation backup FIRST** — a timestamped sidecar in a local
>   `.slopslap/backups/` (git-ignored so it never leaks), prints the restore path + a
>   one-line restore command, keeps the last N.

Placing copies inside the working tree does not make them git-ignored, and the spec defines no step that creates or verifies an ignore rule. In a repository without a matching rule, a broad add or archive operation can disclose original prose, contradicting the claim that backups never leak.

**Recommendation:** In Output modes / apply, require the implementation to create and verify an effective ignore rule before writing a backup, fail closed if it cannot, and detect already-tracked backup paths. Prefer a user-local backup directory outside the repository for the strongest containment, and replace “never leaks” with a precise guarantee.

### 5. [Medium] ambiguity · high confidence — Scanner dependency — Capability-gate by input format

> **Capability-gate by input format.** The plain-text path is stdlib-only and always
>   available. Markdown is EITHER parsed by a conforming CommonMark parser OR reported
>   unavailable — Markdown input is NEVER routed through the plain-text path

No scanner interface or deterministic rule identifies an input as `text` versus `markdown`. Extensionless content, stdin, and prose containing incidental Markdown syntax can therefore be routed differently by different implementations, including into the expressly forbidden plain-text fallback.

**Recommendation:** Add a Scanner input contract with a mandatory `format: "text" | "markdown"` field or equivalent CLI flag. Define any extension-based default explicitly and require ambiguous stdin/input to fail with a format-required status.
**Ambiguity:** The required routing behavior is clear, but the source of the format classification is absent.

### 6. [Medium] ambiguity · high confidence — Scanner `scan_prose.py` — paragraph cadence similarity

> paragraph cadence similarity (10-feature clipped vector → weighted Manhattan → similarity=1−dist;
> flag only if both paras eligible AND similarity>0.88 AND ≥1 other repetition signal);

The ten features, clipping bounds, normalization, weights, and definition of the additional repetition signal are unspecified. These choices directly determine `dist` and whether the 0.88 threshold fires, so the metric cannot be implemented or fixture-tested consistently.

**Recommendation:** In `scanner-metrics.md` requirements, enumerate the ten features, their normalization and clipping bounds, every Manhattan weight, eligibility minimums, and the exact set of signals satisfying the additional-signal gate.
**Ambiguity:** The formula names its structure and threshold but omits the parameters needed to calculate it.

### 7. [Medium] ambiguity · high confidence — Verification

> ## Verification — 3 layers, NOT one self-check; rewriter never verifies itself

The artifact does not define what constitutes a separate verifier: another prompt in the same context, a fresh context using the same model, a distinct agent, or a different model. Implementations can therefore claim compliance while allowing the rewrite pass or its reasoning to bias the purported adversarial check.

**Recommendation:** Add a Verification isolation contract defining separate invocation/context requirements, what information the verifier may receive, whether model identity must differ, and which component owns the final accept/reject decision.
**Ambiguity:** “Separate pass” and “never verifies itself” do not identify the required isolation boundary.

### 8. [Medium] completeness · high confidence — Scanner dependency — Extraction tests

> Bare-URL exclusion is not uniform in core CommonMark —
>   state whether a tested parser extension or a post-tokenization rule supplies it.

This is an unresolved design instruction rather than a settled requirement. Bare URLs are nevertheless declared excluded scanner regions, so implementations can disagree about eligible text and produce different metric counts and locations.

**Recommendation:** Resolve this sentence in Scanner dependency by naming the exact parser extension and configuration or specifying the post-tokenization bare-URL algorithm, then bind that choice to explicit extraction fixtures.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._