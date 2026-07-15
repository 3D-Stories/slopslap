# Adversarial Review — .rawgentic-adv-diff-81.patch

- Date: 2026-07-15
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 3 (Critical 0, High 0, Medium 3, Low 0)

## Summary

The change adds optional de-claim alternatives and records alternative provenance in decisions and feedback. The validation is not enforced at the payload boundary, and the provenance path accepts or silently drops invalid identifiers, allowing malformed UI data and inaccurate ledger records.

## Findings

### 1. [Medium] completeness · high confidence — scripts/slopslap_review/review.py, build_review_payload

> +                # #81: emitted ONLY when present so alternative-less payloads stay byte-identical
> +                **({"alternatives": f.alternatives} if f.alternatives is not None else {}),

`build_review_payload` emits alternatives verbatim without calling the newly added `validate_alternatives`. Consequently, malformed model output—such as duplicate IDs, invalid claim statuses, or non-list data—can reach the review UI despite the stated shape guard. Whether another, unshown model-lane boundary performs this validation is unverifiable from the provided diff.

**Recommendation:** In `build_review_payload`, call `validate_alternatives(f.alternatives)` whenever the value is not `None` and reject the payload with a typed error if problems are returned. Add tests that malformed alternatives cannot be emitted.
**Ambiguity:** The provided diff does not show the future model-lane producer, so validation there cannot be confirmed or ruled out.

### 2. [Medium] correctness · high confidence — scripts/slopslap_review/schema.py, validate_decisions

> +            elif action != "edit":
> +                # #81: an alternative pick IS an edit (its text seeds the replacement) — on any
> +                # other action the label has no referent, so it is rejected like `replacement`.
> +                problems.append(at + "alternative is only allowed with user_action 'edit'")

Decision validation checks only that `alternative` is a non-empty string attached to an edit; it never verifies that the identifier exists in the referenced finding's `alternatives` list. A stale or fabricated identifier therefore passes validation and is written as provenance, corrupting the learning ledger's attribution.

**Recommendation:** Extend `validate_decisions` with the review findings or an allowed-alternative-ID map, and reject each decision whose `alternative` is not present on its `finding_id`. Apply the same check at the finish/action boundary and add unknown-ID and wrong-finding-ID tests.

### 3. [Medium] correctness · high confidence — scripts/slopslap_review/review.py, decisions_from_actions

> +        if action == "edit" and act.get("alternative"):
> +            # #81: provenance label of an alternative-seeded edit (edit-only per schema)
> +            entry["alternative"] = act["alternative"]

The truthiness check erases a present but invalid falsey `alternative` before schema validation. For example, an empty string or `False` supplied by a client becomes an ordinary edit with no alternative field, so the validator cannot reject it and provenance is silently lost instead of the malformed action failing closed.

**Recommendation:** In `decisions_from_actions`, test for key presence (`"alternative" in act`) and copy the value into the decision whenever supplied, then run `validate_decisions` so invalid values are rejected. Make the analogous presence-based change in `append_feedback`, and add a test that a submitted empty alternative causes an error rather than disappearing.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._