# Adversarial Review — .rawgentic-adv-diff-82.patch

- Date: 2026-07-15
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 2 (Critical 0, High 0, Medium 1, Low 1)

## Summary

The diff adds regex-based buzzword and borrowed-authority extraction to the no-new-claims gate. The main risk is an unverified ordering assumption in authority-phrase matching; the added hard-atom regression test also does not cover what it claims.

## Findings

### 1. [Medium] correctness · low confidence — scripts/slopslap_verification/atoms.py, `_AUTHORITY_RE` construction

> +_AUTHORITY_RE = re.compile(
> +    r"\b(?:" + "|".join(r"\s+".join(re.escape(w) for w in p.split()) for p in VAGUE_ATTRIBUTION) + r")\b",
> +    re.IGNORECASE,
> +)

Authority alternatives are not sorted longest-first, unlike `CORPORATE_BUZZWORDS`. If `VAGUE_ATTRIBUTION` contains overlapping phrases and a shorter phrase precedes a longer one, the regex can match only the shorter prefix; when that shorter phrase already exists in the original, introducing the longer phrase can produce no set delta and pass the gate. Whether the current table overlaps is unverifiable because its contents are absent from the artifact.

**Recommendation:** Change `_AUTHORITY_RE` construction in `atoms.py` to sort normalized `VAGUE_ATTRIBUTION` phrases by descending length before joining them, and add a test where the original contains a shorter authority phrase and the revision introduces an overlapping longer phrase.
**Ambiguity:** The failure depends on ordering and overlap in `VAGUE_ATTRIBUTION`, whose definition is not included in the provided diff.

### 2. [Low] completeness · high confidence — tests/test_gates.py, `test_no_new_claim_atoms_fail_per_hard_kind`

> +def test_no_new_claim_atoms_fail_per_hard_kind():
> +    # #82 AC1: each HARD atom kind is individually caught, reason names the atom.
> +    man = {"allowed_claim_atoms": []}
> +    orig = b"The service handles requests."
> +    cases = {
> +        "date": b"The service handles requests since 2024-01-15.",
> +        "url": b"The service handles requests (see https://example.com/bench).",
> +        "citation": b"The service handles requests [1].",
> +        "threshold": b"The service handles requests in at most 5 ms.",
> +    }
> +    for kind, rev in cases.items():
> +        r = G.no_new_claim_atoms(orig, rev, man)
> +        assert not r.passed, kind
> +        assert r.evidence and any(kind in cat for cat in r.evidence[0]), (kind, r.evidence)

The test claims to exercise every hard-atom kind, but omits the `number` kind explicitly listed in the changelog. Its evidence assertion also checks only a category key, not that the reason names the atom as the comment claims. A regression that loses plain-number detection or returns empty/category-only evidence would escape this test.

**Recommendation:** Add a standalone `number` case that is not also a date, URL, citation, or threshold, and change each assertion to verify that the expected extracted atom appears in the evidence value.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._