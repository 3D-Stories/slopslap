# Adversarial Review — increment-4.diff

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 6 (Critical 0, High 5, Medium 1, Low 0)

## Summary

The change implements a ledger-backed verifier, but several promised gates are optional, incomplete, or vacuous on missing input. The most consequential paths can return ACCEPT without Layer 3, without invariant coverage, or without the stated region-scoped and attachment checks; malformed semantic output can also crash verification instead of failing closed.

## Findings

### 1. [High] completeness · high confidence — scripts/slopslap_verification/ledger.py — verify, Layer 1

> +    l1.append(G.protected_spans_intact(revision, edits, ledger.protected_spans_fixture()))
> +    l1.append(G.no_new_claim_atoms(original, revision, {"allowed_claim_atoms": []}))
> +    l1.append(G.markdown_structure(original, revision))
> +    if authorized_ranges is not None:
> +        l1.append(G.edit_locality(edits, {"editable_ranges": authorized_ranges}))

Layer 1 omits the promised region-scoped numbers, units, modality, and negation hard gates, and edit-locality silently disappears when `authorized_ranges` is omitted. An edit not represented by ledger entries can therefore avoid those deterministic checks and still reach ACCEPT, weakening the existing hard-gate layer the design says is reused unchanged.

**Recommendation:** In `verify`'s Layer 1 block, invoke every existing increment-1 hard gate, including the region-scoped number/unit/modality/negation checks. Make authorized ranges mandatory when edits exist, or store their authorization in the validated ledger and reject when neither source is available.

### 2. [High] correctness · high confidence — scripts/slopslap_verification/ledger.py — verify, Layer 2

> +        rev_extract = extract(revision[rs:re].decode("utf-8", errors="replace"))
> +        if rev_extract != entry.extracted:
> +            findings.append(_finding(2, "hard", "entry_weakened",

Layer 2 only compares an aggregate extraction from the entire mapped region. It implements neither inherited-ID candidate assignment nor the specified fingerprint/neighborhood unique matching, so an atom can move to a different proposition within the same region while the multiset remains equal. The verifier then reports survival even though the promised attachment invariant was broken.

**Recommendation:** Replace the region-wide equality check in Layer 2 with candidate extraction and matching by inherited ID, followed by the documented kind/atoms/neighborhood fingerprint. Require a unique match and return ASK for zero or multiple candidates unless a deterministic rule proves a drop.

### 3. [High] correctness · high confidence — scripts/slopslap_verification/ledger.py — normalize_semantic and verify Layer 3

> +    concerns = output.get("concerns") or []
> +    if not isinstance(concerns, list):
> +        return {"verdict": "ambiguous", "concerns": [], "note": "bad concerns"}
> +    return {"verdict": verdict, "concerns": concerns}

Semantic normalization validates only that `concerns` is a list; it does not validate each concern or its ranges. For example, `{"verdict":"real","concerns":["bad"]}` passes normalization and later executes `c.get(...)`, raising an uncaught exception outside the semantic-call try/except. `verify` therefore crashes instead of mapping malformed model output to ambiguous as promised.

**Recommendation:** Extend `normalize_semantic` to validate every concern as a closed-shape dictionary, validate field types, entry IDs, and bounded half-open coordinates, and return an ambiguous normalized result on any error. Keep all normalization and concern processing inside the fail-closed exception boundary.

### 4. [High] security · high confidence — scripts/slopslap_verification/ledger.py — build_ledger

> +    for ri, region in enumerate(manifest.get("invariant_regions", [])):
> +        s, e = region["start_byte"], region["end_byte"]
> +        region_text = original[s:e].decode("utf-8", errors="replace")
> +        for check in region.get("checks", []):
> +            if check not in _CHECK_KIND:
> +                continue

Missing `invariant_regions`, missing `checks`, and unknown check names are silently converted into fewer or zero ledger entries. Such a ledger passes `validate_ledger`, so Layer 2 becomes vacuous and `verify` can return ACCEPT after a clean semantic verdict or `allow_two_layer=True`, despite never checking the omitted invariants.

**Recommendation:** Change `build_ledger` to reject absent or malformed required manifest fields and unknown check names. Validate expected invariant coverage before returning a Ledger, and make `verify` reject a ledger whose recorded coverage does not match the manifest's declared regions and checks.

### 5. [High] security · high confidence — scripts/slopslap_verification/ledger.py — verify decision fold

> +    elif semantic_fn is None and not allow_two_layer:
> +        decision = "SURFACE"  # design R1: no L3 => not shippable by default
> +    else:
> +        decision = "ACCEPT"

The public `allow_two_layer` Boolean bypasses the Layer-3 shipping gate. When it is true and deterministic findings are absent, an unverified proposal receives `decision='ACCEPT'` and subsequently `proposal_status='ACCEPT'`; there is no enforcement limiting this path to tests or previews. A production caller can therefore accidentally or deliberately mark a rewrite shippable without adversarial semantic verification.

**Recommendation:** Remove `allow_two_layer` from the production `verify` API, or make two-layer results a distinct non-shippable decision/status such as `PREVIEW_ACCEPT` with `proposal_status='BLOCKED'`. Provide a test-only helper if deterministic tests need to assert two-layer outcomes.

### 6. [Medium] correctness · high confidence — scripts/slopslap_verification/ledger.py — hunk finding attribution

> +                if f["disposition"] in ("reject", "reject_global"):
> +                    h["decision"] = "REJECT"

Hunk decisions are changed only for rejection findings. A hunk implicated by an `ask` finding remains marked `ACCEPT` and `revertable=True`, even though the document decision is ASK and the hunk contains an unresolved invariant. A downstream per-hunk apply consumer can consequently retain the uncertain hunk.

**Recommendation:** In the hunk-attribution block, fold every intersecting finding using the same `REJECT > ASK > SURFACE > ACCEPT` precedence as the document. Mark ASK and SURFACE hunks non-applicable, and define their `revertable` behavior explicitly for the apply consumer.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._