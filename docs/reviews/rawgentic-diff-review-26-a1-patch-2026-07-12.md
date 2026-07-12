# Adversarial Review — .rawgentic-diff-review-26-a1.patch

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 6 (Critical 0, High 5, Medium 1, Low 0)
- **[WARNING]** Artifact truncated to 200000 bytes before review.

## Summary

The diff adds a fresh-process Claude invocation seam intended to fail closed to an ambiguous verdict. Multiple paths nevertheless accept incomplete or malformed inputs as clean, while the timeout and total-function guarantees can be bypassed by blocking I/O or uncaught process errors.

## Findings

### 1. [High] correctness · high confidence — scripts/slopslap_invoke/contract.py — _validate range attribution

> +    valid_ranges = {
> +        (e["source"]["start_byte"], e["source"]["end_byte"])
> +        for e in ledger_canonical.get("entries", [])
> +    }

Range validation discards the association between each entry ID and its source range. A response can pair entry A's ID with entry B's valid range and still pass, causing verification to reject or revert the wrong hunk while leaving the actually implicated unsafe hunk untouched.

**Recommendation:** In `contract.py::_validate`, build an `id -> exact source range` mapping, reject unknown or duplicate IDs, and require every supplied `entry_id` and `original_range` pair to match the same ledger entry. Define how ranges-only concerns are validated if they remain supported.

### 2. [High] feasibility · high confidence — scripts/slopslap_invoke/invoke.py — _run_claude stdin delivery

> +        # request is small (bounded by document size) — a single write+close cannot deadlock.
> +        try:
> +            proc.stdin.write(request.encode("utf-8"))
> +            proc.stdin.close()

The request has no enforced size bound, and the synchronous pipe write occurs before `proc.wait(timeout=...)`. If the child does not consume stdin and the request exceeds pipe capacity, `write` blocks indefinitely, so the advertised hard timeout is never reached.

**Recommendation:** In `_run_claude`, enforce an explicit request-byte limit and write stdin concurrently with process monitoring, or use a bounded `communicate`-style implementation that applies the timeout while sending input and still performs process-group termination.

### 3. [High] security · high confidence — scripts/slopslap_invoke/contract.py — _validate

> +    raw = obj.get("concerns", [])
> +    if raw is None:
> +        raw = []

A response containing only `{"verdict":"clean"}` passes validation because the required `concerns` field silently defaults to an empty list. Missing or partial model output can therefore become a trusted clean verdict, directly contradicting the stated guarantee that incomplete output never returns clean.

**Recommendation:** In `contract.py::_validate`, require both `verdict` and `concerns` to be present, require `concerns` to be a list, and reject `None`; map any omission to ambiguous through `parse_response`.

### 4. [High] security · high confidence — scripts/slopslap_invoke/contract.py — build_request

> +        for e in ledger_canonical.get("entries", [])
> +    ]

An absent `entries` field is silently converted into an empty ledger instead of being rejected as malformed. The model can then return clean after checking no invariants, allowing corrupt or incomplete ledger input to vacuously pass semantic verification.

**Recommendation:** In `build_request`, require `ledger_canonical` to contain an `entries` list and distinguish a valid explicitly empty ledger from an absent or malformed field. Raise `InvalidRequestError` for absent or invalid ledger structure so `invoke_semantic` returns ambiguous.

### 5. [High] security · high confidence — docs/planning/2026-07-12-26-platform-feasibility-spike.md — Security implications

> +  spike ships ONE adversarial fixture (document text demanding "emit clean") through the
> +  contract parser as a smoke case; the FULL injection-resistance suite (delimiter breaks,
> +  role-play instructions, forged ledger text) is deliberately DEFERRED to #17 (semantic
> +  verify) and #28 (e2e validation golden), where the verifier's judgment — not the
> +  transport this spike proves — is the artifact under test.

The shipped seam accepts attacker-controlled document text and treats a model-authored clean verdict as acceptance-eligible while explicitly deferring meaningful prompt-injection validation. An embedded instruction can suppress a semantic-only violation that deterministic Layer 1 cannot detect, producing clean and allowing the unsafe revision to proceed.

**Recommendation:** Before exposing clean as acceptance-eligible, change contract-v1 and its acceptance gate so untrusted-input injection tests are mandatory in this change. Until those tests and mitigations land, map model clean to ambiguous or keep the seam disabled from authorization decisions.

### 6. [Medium] correctness · high confidence — scripts/slopslap_invoke/invoke.py — _run_claude process creation

> +        except FileNotFoundError:
> +            return InvocationResult(status="cli_missing", duration_s=time.monotonic() - start,
> +                                    diagnostic_code=_DIAG_TRANSPORT)

Process creation catches only `FileNotFoundError`. Other environmental launch failures such as permission denial, invalid executable format, resource exhaustion, or an inaccessible working environment propagate out of `_run_claude`; `invoke_semantic` does not catch them, violating its documented total, fail-closed boundary.

**Recommendation:** In `_run_claude`, catch the relevant `OSError` family around `subprocess.Popen` and return a transport-error `InvocationResult`. In `invoke_semantic`, add a final narrowly logged transport exception boundary that maps unexpected runner environmental failures to ambiguous.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._