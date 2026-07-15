# Adversarial Review — .rawgentic-adv-diff-83.patch

- Date: 2026-07-15
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 4 (Critical 0, High 0, Medium 4, Low 0)

## Summary

The diff adds client-side rendering and selection of de-claim alternatives, plus base64 decoding for proposed rewrites. Several malformed-input paths fail open or silently discard provenance, and the claimed server-side enforcement is not demonstrated by the supplied artifact.

## Findings

### 1. [Medium] completeness · high confidence — README.md, 0.12.0 changelog

> +  the edit's provenance (`decisions[].alternative`, bound server-side to what the finding actually
> +  offered per #81). Selection authorizes nothing — Finish is the decision, the verifier the gate.

The security-relevant claim that the server binds an alternative to what was offered and that the verifier remains the final gate is unverifiable from the provided diff. The new tests only search rendered page source for strings; none submits a selected alternative and demonstrates rejection of a forged ID, a mismatched replacement, an unrecognized status, or a corrupt proposal.

**Recommendation:** Add an end-to-end review-stage test that posts decisions through the actual finish handler and proves forged IDs, IDs belonging to another finding, mismatched alternative text, invalid statuses, and corrupt proposed rewrites are rejected. If that enforcement is outside this artifact, remove or qualify the server-binding claim in the 0.12.0 changelog until the enforcing code and test are included.
**Ambiguity:** The referenced #81 implementation is not included, so its current server-side checks cannot be assessed from this artifact.

### 2. [Medium] correctness · high confidence — scripts/slopslap_review/review.py, decisions()

> +      if(a.alternative)d.alternative=a.alternative;   // #83: provenance of an alternative-seeded edit

Truthiness-based serialization silently removes an empty alternative ID. That turns an invalid alternative-seeded edit into an ordinary unprovenanced edit instead of carrying the invalid value to server-side validation, bypassing the artifact's stated provenance binding and contradicting the adjacent test expectation that an empty value must be carried and rejected.

**Recommendation:** In `decisions()`, test for property presence rather than truthiness, for example with `Object.prototype.hasOwnProperty.call(a, 'alternative')`, and serialize the value even when empty so server validation rejects it. Also refuse alternatives with missing or empty IDs when constructing their buttons.

### 3. [Medium] correctness · high confidence — scripts/slopslap_review/review.py, b64dec() and proposed-rewrite rendering

> +function b64dec(s){ try{ return decodeURIComponent(escape(atob(s))); }catch(e){ return null; } }

Malformed base64 or invalid UTF-8 is converted to `null` without surfacing an error or disabling the finding's actions. The page therefore renders no proposed replacement and can leave the reviewer acting on a card whose actual proposal could not be decoded—a silent fail-open review path.

**Recommendation:** Change `b64dec` and the proposed-rewrite rendering block to mark the finding invalid when decoding fails, display an explicit payload error, and disable apply/edit submission for that finding until a valid proposal is available.

### 4. [Medium] security · high confidence — scripts/slopslap_review/review.py, alternatives rendering block

> +      const isBanned = a.claim_status === 'banned';

The selection guard rejects only the exact string `banned`. A missing, misspelled, differently cased, or future `claim_status` falls into the selectable path, so corrupt or unrecognized alternatives are presented as approved choices despite the UI claiming every choice was pre-checked. The verifier might reject the resulting edit later, but the client-side safety classification itself fails open.

**Recommendation:** In the alternatives rendering block, allow only an explicit enum of recognized selectable statuses (`none`, `scoped`, and `kept` if intended). Disable or reject every alternative whose status is absent or unrecognized, and validate that `id` and `text` have the required types before installing the click handler.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._