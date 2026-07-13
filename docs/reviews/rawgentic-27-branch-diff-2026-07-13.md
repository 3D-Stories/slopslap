# Adversarial Review — .rawgentic-27-branch.diff

- Date: 2026-07-13
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 3 (Critical 1, High 2, Medium 0, Low 0)

## Summary

The change adds an audit–verify–apply orchestration seam, but its public API bypasses the advertised dry-run restriction, trusts caller-constructed authorization artifacts, and reports offline stub verification indistinguishably from live semantic verification. These paths can permit mutation or produce a misleading exit-0 result without the intended policy evidence.

## Findings

### 1. [Critical] security · high confidence — scripts/slopslap_assemble/assemble.py — run_candidate/apply invocation

> +def run_candidate(audit: AuditResult, edits, *, semantic_fn=None, write: bool = False,
> +                  apply_config=None) -> RunResult:
> +        report = apply_selective(src, parsed, _bound_verify, config=apply_config, write=write)

The public API accepts `write=True` and forwards it directly to the mutation engine, despite the change's repeated claim that this version is dry-run only until the #29 apply flip. Any in-process caller can bypass that deferred gate and mutate the source now, so the implementation does not enforce its own no-mutation release boundary.

**Recommendation:** In `scripts/slopslap_assemble/assemble.py`, remove the public `write` parameter from `run_candidate` and `assemble` for v0.1.8 and pass `write=False` unconditionally. Add a test asserting that no exposed API can request mutation; introduce `write` only with the #29 gate.

### 2. [High] correctness · high confidence — scripts/slopslap_assemble/assemble.py — live_semantic_fn and CLI run path

> +    if os.environ.get("SLOPSLAP_LIVE") == "1":
> +        import functools
> +
> +        from slopslap_invoke.invoke import invoke_semantic
> +        bound = functools.partial(invoke_semantic, model=model, timeout_s=timeout_s,
> +                                  status_sink=sink)
> +
> +        def fn(original, revision, ledger_canonical):
> +            return bound(original, revision, ledger_canonical)
> +    else:
> +        def fn(original, revision, ledger_canonical):
> +            return {"verdict": "clean", "concerns": []}

The default production CLI silently substitutes a hardcoded clean semantic verdict when `SLOPSLAP_LIVE` is absent. The emitted `RunResult` contains no semantic execution-mode field, so an offline deterministic-only run can return the same status and exit 0 as a real semantic pass. Machine consumers can therefore treat an unperformed security/policy layer as completed successfully.

**Recommendation:** Change `live_semantic_fn` and the CLI so absent live mode either produces a typed blocked/failed result or requires an explicit `--offline-deterministic-only` opt-in. Add `semantic_mode: live|offline_stub` to the verify stage and top-level JSON, and reserve the documented shippable exit 0 for live semantic verification unless the caller explicitly requests the weaker deterministic verdict class.

### 3. [High] security · high confidence — scripts/slopslap_assemble/assemble.py — run_candidate authorization handling

> +    authorized = None if audit.authorization["state"] == "locality_unverified" \
> +        else audit.authorization["ranges"]
> +    try:
> +        verify_result = verify(original, parsed, audit.ledger,
> +                               authorized_ranges=authorized, semantic_fn=semantic_fn)

`run_candidate` trusts authorization ranges and the ledger supplied inside a caller-constructed `AuditResult` without re-deriving or authenticating them. A caller can construct or replace the frozen dataclass with whole-document ranges and an empty ledger for the same source digest, bypassing demonstrated-harm locality and invariant protections while the function synthesizes an `audit` stage marked `ok`.

**Recommendation:** At the `run_candidate` API boundary, do not accept policy-bearing `AuditResult` objects from callers as trusted. Re-audit the bound source to reconstruct and compare authorization, protected spans, invariant regions, and ledger digest, or issue an opaque authenticated audit handle from `audit_document` and reject altered/unrecognized aggregates with an invalid-contract failure.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._