# Adversarial Review — 2026-07-12-30-corpus-integration.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 6 (Critical 0, High 5, Medium 1, Low 0)

## Summary

The design aims to create a provenance-controlled corpus, licensed routing, authored fixtures, and deterministic calibration/held-out separation. Its central separation model is internally ambiguous, and several enforcement and compatibility claims are not demonstrated by the artifact.

## Findings

### 1. [High] ambiguity · high confidence — Approach 5

> **5. Fixed disjoint split** — a deterministic partition of manifest items into `calibration`
> vs `held_out` by a stable hash of `item_id`

The design uses `calibration` both as an artifact lane and as one side of a separate split, without defining how the two dimensions interact. It is unclear whether only calibration-lane records are split, whether fixture/judge-reference records can enter either partition, or whether a calibration-lane item can be assigned held-out. This can produce incorrect training/evaluation routing and force rework in #25 and #28.

**Recommendation:** In Approach 5, define the split domain and output schema explicitly—for example, make `usage_lane` and `split_partition` separate fields, enumerate which lanes are eligible for splitting, and state exactly which partition #25 and #28 consume.
**Ambiguity:** The relationship between the lane enum and the calibration/held-out partition is not specified.

### 2. [High] correctness · high confidence — Approach 5

> The split
> function is pure + tested for disjointness and stability; #25 fits thresholds on `calibration`
> and reports on `held_out`, and a test enforces the two partitions never intersect.

Disjointness by manifest item or `item_id` does not guarantee that the same gathered pair cannot occur in both partitions. The schema supplies no canonical-content identity or uniqueness constraint, so duplicate records, aliases, or separately identified variants of the same source content can hash into different partitions while the set-intersection test still passes. That defeats the design's stated train/test-overlap goal.

**Recommendation:** In Approach 1 and 5, define a canonical example or pair identifier derived from normalized content hashes and lineage; validate its uniqueness; split on that identifier; and test that content hashes and lineage groups are disjoint across partitions, not merely item IDs.

### 3. [High] feasibility · high confidence — Approach 4

> matching
> the existing `tests/fixtures/eval/<name>/{fixture.json,original.md}` structure so the eval
> loader + `verify()` exercise them unchanged:

The design assumes the existing loader and `verify()` can represent and execute all proposed cases—including an authorized assertion-to-question transformation, selective semicolon protection, seam-local editing, and an expected hard failure—but provides no exact call site, fixture-schema evidence, or spike. From the supplied text, compatibility with the project's actual fixture contract is unverified; implementation may require loader or verifier changes despite the single-PR assessment calling the work additive.

**Recommendation:** Add a Platform / external dependencies feasibility subsection citing the exact loader and `verify()` call sites and required fixture keys for each case, or record a spike result. If changes are required, list the affected existing modules under File changes and revise the Multi-PR assessment.

### 4. [High] internal-consistency · high confidence — Approach 1–2

> artifact_lane
> (fixture|judge_reference|calibration|inspiration)

The schema permits exactly one `artifact_lane`, but routing later permits an item to be used in multiple lanes (`fixture` and/or `calibration`). An implementer must either violate the schema, duplicate the item, or silently choose one use, undermining provenance and overlap controls.

**Recommendation:** In Approach 1 and 2, replace `artifact_lane` with a defined multi-value `artifact_lanes[]`, or explicitly require one manifest record per item-lane assignment with a stable canonical item identity and uniqueness rules.

### 5. [High] security · high confidence — Security implications

> only `fixture`/`calibration`-lane items carry verbatim text, and ONLY when
>   `redistribution` permits (MIT / CC BY-SA with attribution).

The stated licensing invariant is not backed by a specified validation test. The only described automated assertion covers the inverse case—no committed verbatim file for `inspiration` items—so a fixture or calibration item can still carry verbatim content when `redistribution` is false, `allowed_uses` excludes that lane, or required attribution is absent. That can commit improperly redistributable material.

**Recommendation:** In Security implications and `tests/test_corpus_manifest.py`, require machine-enforced rules that any item with committed verbatim content has `redistribution` explicitly permitting it, `allowed_uses` containing every assigned lane, a recognized license, and nonempty required attribution/license-notice fields; fail closed otherwise.

### 6. [Medium] feasibility · high confidence — Platform / external dependencies

> platform_apis: none

This declaration is incomplete relative to the design's reliance on the project's eval loader and `verify()` framework contract. The artifact contains no capability/configuration evidence, feature-flag check, exact-object-kind call site, or spike establishing that these fixture forms and expected-rejection assertions work under the real project configuration.

**Recommendation:** Replace `platform_apis: none` with an explicit internal-framework dependency entry for the eval loader and `verify()`, including exact call-site/schema evidence and any relevant configuration or feature flags; otherwise label compatibility as unverified and add a prerequisite spike.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._