# Adversarial Review — increment-4-ledger-verify-design.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 7 (Critical 1, High 3, Medium 3, Low 0)

## Summary

The design defines a ledger-backed, three-layer verifier and per-hunk decision output, but its acceptance rule permits shipping after only two layers. Several canonicalization, extraction, edit-map, and hunk-attribution contracts remain too underspecified to implement consistently or verify against the project's actual configuration.

## Findings

### 1. [Critical] internal-consistency · high confidence — Folded decisions 7–8

> all preservation passing + (L3 clean OR semantic_fn omitted) → ACCEPT.

The verifier returns ACCEPT when Layer 3 was not run, contradicting both the stated three-layer verification goal and “A rewrite you do not verify is a rewrite you do not ship.” Because requiring Layer 3 is merely optional for callers, an omitted semantic_fn can produce an ACCEPT proposal that is treated as shippable without adversarial semantic verification.

**Recommendation:** Change Folded decision 8 so an omitted semantic_fn produces SURFACE or a distinct non-shippable decision by default. Require an explicit policy input authorizing two-layer acceptance, and ensure proposal_status remains BLOCKED whenever semantic_status is not_run.

### 2. [High] completeness · high confidence — Folded decision 1

> **canonical serialization**
>    (sorted keys + sorted entries) yields a stable `ledger_sha256`.

This does not define byte-canonical JSON. It omits protected_spans ordering, JSON separators and whitespace, Unicode normalization/escaping, number encoding, trailing newline behavior, and whether ledger_sha256 is excluded from the hashed value. Independent implementations can serialize the same ledger differently and produce incompatible hashes.

**Recommendation:** In `references/invariant-ledger.md`, specify the exact canonical byte algorithm: UTF-8 and Unicode policy, field and array ordering for every array, JSON escaping, separators, numeric representation, newline policy, and the precise object hashed. Add canonical input/output/hash vectors.

### 3. [High] completeness · high confidence — Folded decision 4

> re-extract the entry's kind-shape and compare by inherited id else
>    fingerprint+neighborhood

Neither each kind's extracted shape nor the fingerprint, neighborhood boundary, normalization, and comparison rules are defined. A revision-side extraction also cannot inherently possess the original stable id unless the mapping procedure assigns it. Implementations can therefore disagree on survival, weakening, attachment, and ambiguity, producing different ship decisions for the same rewrite.

**Recommendation:** Add a per-kind table to the Layer 2 contract defining the extracted schema, deterministic extractor, normalization, equality/weakening test, neighborhood window, fingerprint construction, and the exact rule that assigns an inherited id. Kinds without such a rule must return ASK explicitly.

### 4. [High] correctness · high confidence — Folded decisions 7 and 9

> Concern: `{code,message,entry_ids?,original_ranges?,revision_ranges?}`.

All attribution fields are optional, yet apply mode depends on per-hunk attribution. A valid Layer 3 `real` concern may contain only code and message, leaving no defined way to populate implicated_hunk_ids or decide which hunk or dependency group to revert. The next increment must either revert nothing despite REJECT or revert unrelated passing work.

**Recommendation:** Make at least one machine-resolvable attribution form mandatory for `real` concerns, or define unattributed `real` findings as global and mark every hunk non-revertable so apply mode blocks without partial application. Specify this mapping in Folded decisions 7 and 9.

### 5. [Medium] ambiguity · high confidence — Folded decision 1

> Validation rejects
>    unknown fields, bad enum values, duplicate ids, invalid/overlapping ranges, and hashes inconsistent
>    with the original bytes.

The scope of the overlapping-range prohibition is undefined. Auto-derived invariants naturally can overlap—for example, a number, modal, or exception inside a condition—so applying the prohibition to entries would reject legitimate ledgers, while applying it only to protected spans establishes a materially different rule.

**Recommendation:** Amend Folded decision 1 to state separately which overlap relationships are legal for entries and protected_spans, including containment, identical ranges, partial overlap, and adjacency.
**Ambiguity:** “invalid/overlapping ranges” does not identify which range collections or overlap forms it governs.

### 6. [Medium] feasibility · high confidence — Folded decision 10

> extend the edit-map to return `(interval_or_None, status)`
>     where status ∈ `{unchanged, modified, deleted, ambiguous}`;

The artifact assumes the existing edit-map can be extended to this contract but provides no current signature, exact-object-kind call site, capability/configuration evidence, or spike result. It is therefore unverifiable from the provided text that `editscript.map_offset`/`map_region` exists in the required form or can represent multi-hunk mappings without breaking increment-1 consumers.

**Recommendation:** Add a cited exact call site or spike result showing the current edit-map types and multi-hunk behavior, then specify whether this is a backward-compatible new API or a migration. Define how one source interval maps to multiple disjoint revision intervals rather than only `interval_or_None`.

### 7. [Medium] feasibility · high confidence — Folded decision 7

> `semantic_fn(original, revision, ledger_view) ->
>    {verdict:'real'|'ambiguous'|'clean', concerns:[{code,message,entry_ids?,original_ranges?,revision_ranges?}]}`.

This externally injected callable has no demonstrated compatibility with the project's runtime configuration and no timeout, cancellation, resource, or isolation contract. Exception handling does not cover a callable that hangs indefinitely, so verify may never return and the failure cannot be surfaced as ambiguous.

**Recommendation:** Extend the Layer 3 interface with an enforced timeout/cancellation boundary and a surfaced diagnostic for timeout or invocation failure. Cite a project-configured call site or spike proving the callable can be invoked under the actual sandbox, CI, feature-flag, and dependency configuration.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._