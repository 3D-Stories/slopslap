# Adversarial Review — .rawgentic-adv-diff-84.patch

- Date: 2026-07-15
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 3 (Critical 0, High 1, Medium 2, Low 0)

## Summary

The change adds a two-layer replacement precheck and a model-authored alternatives contract, but the diff does not enforce that contract at the review-payload boundary. Several invalid or unverified alternatives can therefore reach the UI despite the stated fail-closed behavior.

## Findings

### 1. [High] security · high confidence — scripts/slopslap_review/findings.py, `precheck_replacement` return path

> +    return {"status": status, "decision": decision,
> +            "proposal_status": result.get("proposal_status"),
> +            "semantic_status": result.get("semantic_status"), "reason": reason}

The new precheck only returns advisory data; it does not assign `claim_status`, attach the result to an alternative, or prove that it was run. No changed caller invokes it while building the review payload. Consequently, a model-authored candidate can omit the precheck or supply its own non-banned claim status and still reach the UI, bypassing the advertised no-new-claims gate until the later apply verifier.

**Recommendation:** Change `build_review_payload` to invoke `precheck_replacement` itself for every alternative using the authoritative document and finding span, overwrite rather than trust model-supplied precheck/claim-status fields, and reject alternatives without a successful server-derived result. Add a test showing an unprechecked claim-adding alternative cannot be serialized or served.

### 2. [Medium] ambiguity · high confidence — skills/slopslap/SKILL.md, `anchor:alternatives-authoring`; scripts/slopslap_review/findings.py

> +    else:
> +        status = "blocked"
> +        reason = "; ".join(f"{f.get('code')}: {f.get('message')}" for f in result.get("findings", [])) \
> +            or f"verifier decision {decision}"
> +it — a `blocked` verdict whose reason names `no_new_claim_atoms` sets that alternative's
> +`claim_status: banned`.**

Every non-ACCEPT verifier outcome becomes `blocked`, but the authoring contract bans only a blocked result whose formatted reason contains `no_new_claim_atoms`. It gives no disposition for other deterministic failures or for a no-new-claims rejection whose human-readable reason lacks that token. Such a candidate may remain enabled in the UI and then fail only when the user tries to apply it.

**Recommendation:** In the alternatives-authoring contract and payload builder, define every `status == "blocked"` result as banned or omit it entirely. Preserve structured finding codes in the return value and use those codes only to explain the block, not to decide whether the block is enforced.
**Ambiguity:** The artifact does not define how claim status is assigned for blocked verdicts caused by anything other than `no_new_claim_atoms`.

### 3. [Medium] internal-consistency · medium confidence — skills/slopslap/SKILL.md and tests/test_review_stage.py, `test_precheck_replacement_banned_and_pass`

> +compose alternatives from claims and lexemes the original span already carries, never new ones.
> +    # introduce a buzzword ABSENT from the whole doc ("world-class"; the doc already carries
> +    # "best-in-class", whose reuse is allowed by design)

The contract defines the allowance as span-local, while the new test describes reuse in document-wide terms and never asserts that an allowed claim atom originates inside the selected span. A document-wide implementation could therefore pass this test while allowing claims to be moved laterally between unrelated spans, contrary to the stated rule.

**Recommendation:** Rewrite `test_precheck_replacement_banned_and_pass` to place a claim atom elsewhere in the document but outside the candidate span and assert that introducing it into the replacement is blocked. Also explicitly state whether the claim-atom allowance is span-local or document-wide and make the verifier implement that scope.
**Ambiguity:** The provided diff does not expose the verifier's claim-atom scope or the contents of `_DOC`, so the current implementation's locality cannot be confirmed.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._