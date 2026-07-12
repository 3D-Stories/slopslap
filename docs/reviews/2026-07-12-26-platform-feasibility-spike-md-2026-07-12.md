# Adversarial Review — 2026-07-12-26-platform-feasibility-spike.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 6 (Critical 0, High 3, Medium 3, Low 0)

## Summary

The artifact proposes a closed Python wrapper around a fresh Claude CLI process for semantic verification. Its main risks are that the isolation proof can false-pass, the real plugin-platform capability remains pending, and several contract details contradict each other.

## Findings

### 1. [High] completeness · medium confidence — Design — Fresh-context enforcement, items 2–4

> 2. Payload-only input: prompt contains ONLY the three request fields + instructions.
>   3. Tool lockdown: no-tools invocation mode (exact flag semantics verified live in the
>      spike; pinned in argv; asserted by tests) — the fresh session cannot read repo files,
>      transcripts, or rewriter artifacts.
>   4. Empty temp cwd — no ambient project context to discover.

The isolation bundle addresses the working directory and model tools but does not address inherited environment variables, user-level Claude configuration, hooks, plugins, MCP configuration, or other home-directory context. Therefore the claim that the payload is the session's whole input is not established; ambient configuration could inject context or access rewriter artifacts despite the empty cwd.

**Recommendation:** Expand Fresh-context enforcement with an explicit child-environment and configuration policy. Enumerate inherited variables and configuration locations, sanitize all non-authentication state, disable hooks/plugins/MCP and user/project instruction loading using exact live-proven controls, and add evidence that these controls work in the actual plugin-launched process. Otherwise narrow the isolation claim to new conversation-session isolation only.
**Ambiguity:** The provided text does not include the project's capability files, user-level CLI configuration, or exact CLI behavior under the plugin runtime.

### 2. [High] correctness · high confidence — Design — Fresh-context enforcement, item 5

> PASS = the response demonstrates denial/absence (no
>      sentinel token present, tool access refused).

The denial result is based on model-authored text, so it does not prove that tool access was unavailable. A session with working tools can simply decline to call them or claim they were refused, allowing the spike to pass while repository or host access remains possible and invalidating the fresh-context guarantee.

**Recommendation:** Change the Positive denial test section to require machine-observable evidence from the CLI envelope or execution trace: assert an attempted tool call and its platform-generated denial, assert zero successful tool results, and independently assert the sentinel token never appears. Do not accept assistant prose as proof of denial.

### 3. [High] security · medium confidence — contract.py — request builder

> request builder: deterministic serialization of EXACTLY (original, revision,
>     ledger_canonical) beneath a fixed semantic-verifier instruction, in clearly delimited
>     data fields.

The three fields contain attacker-controlled document text, but delimiting them does not prevent embedded instructions from steering the model to return `clean` or fabricated copied ranges. Because a clean semantic result participates in acceptance, prompt-injected content can suppress a semantic violation without causing a schema failure.

**Recommendation:** Add an explicit untrusted-input threat model to contract-v1 and a deterministic adversarial fixture suite containing delimiter breaks, role-like instructions, forged ledger text, and demands to emit `clean`. Specify how these inputs are encoded and separated from instructions, and require an independent fail-closed check or additional verifier before a model-authored `clean` result can authorize semantic acceptance.
**Ambiguity:** The exact fixed instruction and serialization format are absent, so their existing resistance to document-borne prompt injection cannot be assessed from the artifact.

### 4. [Medium] feasibility · high confidence — Platform / external dependencies

> feasibility: verified via spike — spike status at design time: PENDING (Step-4 F4/S1); "verified" becomes true ONLY when the live run is recorded to tests/fixtures/invoke/recorded_invocation.json AND the Evidence section below is filled with the positive denial result, IN THIS SAME PR before it merges; Step 9's runtime-surface check gates on that recorded evidence existing

The artifact simultaneously labels feasibility verified and PENDING. No completed capability evidence currently proves that plugin-launched Python may execute the host CLI, inherit usable authentication, use the proposed flags, reach the API, or receive the expected model field under the project's real configuration. If any assumption fails, all semantic calls collapse to ambiguity and #17/#27 cannot provide a usable live path.

**Recommendation:** Change platform_apis.feasibility to `unverified` until the evidence is populated. Require the merge gate to cite the exact plugin-context call site or harness, active capability/manifest configuration, sanitized argv, environment/auth result, CLI version, and machine-observable lockdown result—not merely a terminal invocation outside the plugin runtime.

### 5. [Medium] internal-consistency · high confidence — contract.py — Verdict vocabulary and Concern attribution

> **Verdict vocabulary = the seam's OWN enum (Step-4 loop-back fix, Critical F1):**
>     `{verdict: "real"|"ambiguous"|"clean", concerns: [{code, message, entry_ids: [str],
>     original_ranges: [{start_byte, end_byte}]}]}` — exactly what `normalize_semantic`
>     (ledger.py:211-245) accepts.

The displayed strict response shape presents `entry_ids` and `original_ranges` as fields of every concern, but the later attribution contract requires valid `entry_ids`-only and fully unattributed concerns. An implementer cannot determine whether those fields are required, so the strict validator may reject the very shapes the test matrix says must reach `verify()`.

**Recommendation:** Replace the response notation in contract.py's design with an explicit schema declaring which concern fields are required and which are optional. Define and test three exact valid objects for fully attributed, entry_ids-only, and unattributed concerns, including whether omitted fields and empty arrays are semantically distinct.

### 6. [Medium] internal-consistency · high confidence — contract.py — Failure mapping

> the stable
>     failure codes (`semantic_transport_error`, `semantic_timeout`,
>     `semantic_invalid_response`) are DIAGNOSTIC ONLY: they live in the
>     `InvocationResult`/returned dict and the invoke layer's logging, and are NOT claimed to
>     reach `verify()` findings.

This says diagnostic codes live in the returned dict, while the public API earlier requires the returned dict to be exactly `{verdict, concerns}` and says the internal `InvocationResult` never crosses that boundary. The listed `InvocationResult` fields also contain `status` but no diagnostic-code field. Implementers will either violate the closed return contract or silently discard the promised diagnostic codes.

**Recommendation:** Change Failure mapping to name one authoritative diagnostic carrier. Add an explicit `diagnostic_code` field to internal `InvocationResult` and state that it is emitted only through structured logging; remove `returned dict` from this paragraph and add a deterministic log-capture assertion for each failure mapping.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._