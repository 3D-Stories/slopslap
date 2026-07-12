# #26 Platform-feasibility spike — fresh-context model invocation (design + spike report)

Status: design drafted 2026-07-12 (evidence section filled during implementation).
Part of epic #16. Blocks #17 (semantic verify) and #27 (live orchestration).

## Problem

The live path (audit → verify → suggest → apply) assumes plugin code can invoke a model, but
nothing proves it. The spec's isolation contract
(`docs/planning/2026-07-12-slopslap-reconciled-spec.md:101-106`) requires the Layer-3
adversarial semantic pass to run in a FRESH context that never saw the rewriter's
chain-of-thought, receiving only original + revision + invariant ledger. The consumer seam is
`verify(..., semantic_fn)` at `scripts/slopslap_verification/ledger.py:253` — a synchronous
Python callable. This spike proves ONE fresh-context invocation under the real plugin config
and pins the contract #17 builds on.

## Approaches considered

**A — subprocess `claude -p` (headless CLI) from a Python helper.** RECOMMENDED.
- Pros: callable from synchronous Python (the semantic_fn seam); fresh context by construction
  (new OS process, new session — no `--resume`/`--continue`); model selectable (`--model`);
  machine-readable envelope (`--output-format json`); timeout via `subprocess.run(timeout=)`;
  auth = the user's logged-in Claude Code credentials, which IS "the actual plugin config";
  zero new Python deps.
- Cons: CLI version drift (envelope shape pinned by recorded fixture); per-call session
  spin-up cost; CI has no Claude auth (live test must be env-gated).
- Effort: ~1 day. Risk: low-medium (envelope drift, cost).

**B — Anthropic HTTP API with an API key.** Rejected: a different auth path than the plugin
config actually has (no API key in this setup) — proving B would NOT prove the plugin can do
it, which is the whole point of the spike. Also adds an HTTP dep or hand-rolled client.

**C — in-session subagent dispatch (skill prose instructs the main model).** Rejected as THE
mechanism: not callable from deterministic Python, so pytest can never exercise it, and
fresh-context enforcement would be prompt discipline only — unverifiable. (It remains a valid
*additional* pattern for skills at orchestration level, but the provable seam is A.)

## Design (approach A — synthesized with the GPT Soul peer consult, 2026-07-12)

New module `scripts/slopslap_invoke/`:

- **Public API is CLOSED (peer decision adopted):** `invoke_semantic(original, revision,
  ledger_canonical, *, model, timeout_s=60.0, executable=None) -> dict` — the semantic seam
  never accepts arbitrary prompts, session ids, extra messages, or extra CLI args. The
  low-level subprocess runner (`_run_claude`) is module-private.
  - **Return type pinned (pass-2 A4):** the returned dict is EXACTLY the
    `normalize_semantic`-input object `{verdict, concerns}` — nothing else. The internal
    `InvocationResult` never crosses the public boundary; its diagnostics surface via module
    logging (`logging.getLogger("slopslap.invoke")`). Every failure status converts
    deterministically to `{"verdict": "ambiguous", "concerns": []}` at this boundary.
  - **semantic_fn adapter (pass-2 S5):** the verify seam calls
    `semantic_fn(original, revision, ledger_canonical)` with three positional args
    (ledger.py:328) — #17 binds the keywords:
    `semantic_fn = functools.partial(invoke_semantic, model=..., timeout_s=...)`.
- `invoke.py` — the runner:
  - argv list (never `shell=True`): `[executable, "-p", "--model", model, "--output-format",
    "json", "--no-session-persistence", <no-tools lockdown flag — ONE exact argv pinned by
    the live probe>]`; the request delivered on **stdin** (no argv length limits, no
    process-list exposure). No `--resume`, `--continue`, `--fallback-model` — prohibited by
    construction; empty model rejected. The live probe verifies EVERY load-bearing flag
    (`-p`, `--output-format json`, `--no-session-persistence`, the lockdown flag) on the
    probed CLI version, and the exact working argv is recorded in the fixture (pass-2 S4).
  - **Bounded execution (pass-2 A6 — `subprocess.run` is NOT sufficient):** `subprocess.Popen`
    with `start_new_session=True` (own process group); stdout/stderr drained by streaming
    read with a hard byte cap (cap exceeded → kill group, `status=parse_error`); on timeout
    `killpg(SIGTERM)` → grace period → `killpg(SIGKILL)`. Tests cover a fake CLI that
    exceeds the cap mid-run and one that spawns a surviving descendant. Linux/macOS
    semantics (the plugin's supported platforms).
  - Child runs in a **newly created empty temp cwd** (peer: prevents project-file/CLAUDE.md
    discovery).
  - `InvocationResult` (internal): `status ∈ {ok, timeout, cli_missing, nonzero_exit,
    parse_error, model_mismatch}` + `result_text`, `envelope`, `duration_s`, `stderr_tail`
    (bounded). Requested vs envelope-reported model compared; mismatch → not-ok (peer
    decision). The runner NEVER raises on environmental failure — every failure is an
    explicit status (fail-loud by contract).
- `contract.py` — versioned request/response contract (**contract-v1**):
  - request builder: deterministic serialization of EXACTLY (original, revision,
    ledger_canonical) beneath a fixed semantic-verifier instruction, in clearly delimited
    data fields. `original` arrives as bytes at the verify seam (`verify(original: bytes, …)`)
    — the builder decodes STRICT utf-8; invalid bytes REJECT the request (return
    `{"verdict": "ambiguous", "concerns": []}` + diagnostic log) rather than silently
    corrupting the offset base with replacement chars (pass-2 A1).
  - **Offset integrity (pass-2 A1 — the model never computes byte offsets):** the payload
    presents each ledger entry WITH its `original_ranges` verbatim (the ledger canonical
    object already carries original-byte ranges per entry). The model attributes a concern
    by COPYING the flagged entry's id + ranges from the payload — it is explicitly
    instructed never to derive offsets from text positions. The response validator accepts
    only ranges that appear in the supplied ledger (byte-for-byte match); any invented range
    → schema violation → `ambiguous`. A multibyte-content fixture asserts exact hunk
    attribution end-to-end through `verify()`.
  - response: extract the assistant payload from the CLI JSON envelope, parse as ONE strict
    JSON object, and validate LOCALLY — allowed keys, enum values, types, bounded field
    sizes (prompt wording is never schema enforcement — peer decision).
  - **Verdict vocabulary = the seam's OWN enum (Step-4 loop-back fix, Critical F1):**
    `{verdict: "real"|"ambiguous"|"clean", concerns: [...]}` — exactly what
    `normalize_semantic` (ledger.py:211-245) accepts. **Explicit concern schema (pass-3
    P3-5):** per concern, `code: str` and `message: str` are REQUIRED; `entry_ids: [str]`
    and `original_ranges: [{start_byte, end_byte}]` are OPTIONAL — an omitted field is
    semantically identical to an empty array (matching `normalize_semantic`'s
    `.get(..., [])` defaults, ledger.py:229-230). The validator accepts all three
    attribution shapes (fully attributed / entry_ids-only / unattributed); each has an
    exact valid example object in the test suite. `"real"` = confirmed violation → REJECT path
    (ledger.py:333); `"ambiguous"` = inconclusive → SURFACE (ledger.py:344); `"clean"` =
    ACCEPT-eligible. NO translation layer — the model is instructed in the seam's native
    vocabulary. A deterministic test round-trips each verdict through
    `normalize_semantic` + `verify()` and asserts the resulting decision (REJECT / SURFACE /
    ACCEPT-eligible).
  - **Concern attribution (Step-4 loop-back fix, High F2; refined pass-2 S2):** concerns
    carry `entry_ids` + `original_ranges` copied from the payload's ledger entries.
    **`original_ranges` is the SOLE authoritative field for per-hunk mapping**
    (ledger.py:339-340 computes implicated hunks only from ranges); `entry_ids` are
    traceability-only. A "real" concern with ranges rejects only its implicated hunks
    (`disposition="reject"`); one with `entry_ids` but NO ranges counts as attributed yet
    maps to zero hunks and degrades to global non-revertable via ledger.py:374 (safe
    direction — over-rejection); one with neither is `reject_global` outright
    (ledger.py:334-343, 374-379). The fixture and tests cover ALL THREE shapes: fully
    attributed, entry_ids-only (partial), and unattributed.
  - **Failure mapping (amended per Medium F3 — the seam collapses failure detail):** every
    transport/timeout/parse/schema failure maps to verdict `"ambiguous"` — never `"clean"`
    from missing output, and semantic output can never override Layer-1 hard failures.
    `verify()` re-emits ambiguity as its own generic `semantic_ambiguous` SURFACE finding
    (ledger.py:344-346) and drops concern detail for non-"real" verdicts, so the stable
    failure codes (`semantic_transport_error`, `semantic_timeout`,
    `semantic_invalid_response`) are DIAGNOSTIC ONLY. **Authoritative carrier (pass-3
    P3-6):** a `diagnostic_code` field on the internal `InvocationResult`, emitted
    exclusively through structured logging (`slopslap.invoke` logger) — the public
    `{verdict, concerns}` dict NEVER carries them (closed-boundary rule upheld). A
    deterministic log-capture test asserts each failure mapping emits its code. Stated
    explicitly so nobody builds on a granularity the seam does not transport.
- **Fresh-context enforcement (the bundle — mechanisms, not assertions).** Scope of the
  claim (pass-3 P3-1, narrowed per reviewer option): the guarantee is
  **new-conversation-session isolation** — the invoked session structurally cannot see the
  rewriter's conversation, chain-of-thought, or session artifacts, which is exactly what the
  spec isolation contract (spec:101-106) requires. Ambient USER-level configuration
  (~/.claude instructions, hooks, MCP servers) is NOT rewriter state and is out of the
  contract's scope; the spike still minimizes it where the live probe proves controls safe
  (non-auth env vars scrubbed from the child env; hook/MCP-disabling flags adopted if the
  probed CLI offers them without breaking auth) and RECORDS what remains inherited in
  Evidence:
  1. New OS process + new session per call — no resume/continue/session reuse possible
     through the closed API.
  2. Payload-only input: prompt contains ONLY the three request fields + instructions.
  3. Tool lockdown: no-tools invocation mode (exact flag semantics verified live in the
     spike; pinned in argv; asserted by tests) — the fresh session cannot read repo files,
     transcripts, or rewriter artifacts.
  4. Empty temp cwd — no ambient project context to discover; child env scrubbed to an
     allowlist (auth + PATH + HOME essentials), inherited remainder documented.
  5. **Positive denial test (pass-2 A3, hardened pass-3 P3-2 — machine-observable evidence
     only, never assistant prose):** the live spike creates a SENTINEL file with a known
     random token at a known path outside the payload, then instructs the invoked session
     to attempt to read that exact path. PASS requires ALL of, read from the CLI
     envelope/execution trace (not the model's own claims): (a) an attempted tool call is
     visible in the trace with a platform-generated denial, OR the trace shows zero tool
     invocations were possible under the lockdown argv; (b) zero successful tool results in
     the trace; (c) the sentinel token appears NOWHERE in the response. A model saying
     "access refused" counts for nothing. The sanitized argv, lockdown configuration, CLI
     version, and the machine-observable trace excerpts are recorded in Evidence. An
     invocation that CAN retrieve the sentinel fails the spike.
- **Checked-in evidence (all fixture content SYNTHETIC — peer risk item; no real user text,
  no credentials, redacted diagnostics):**
  - `tests/fixtures/invoke/recorded_invocation.json` — the real sanitized envelope from one
    live run (request, raw stdout envelope, expected extracted object, metadata: CLI version,
    requested+reported model, duration, timestamp).
  - Deterministic tests (CI-green, no auth): argv construction incl. lockdown + prohibited
    flags; envelope extraction + strict schema validation over the recorded fixture; fake-CLI
    suite covering success, invalid JSON, schema violation, nonzero exit, model mismatch,
    oversized output (cap exceeded MID-RUN), timeout (fake bin sleeps; process-group
    terminate→kill exercised; a descendant-spawning fake proves no orphans); verdict
    round-trip through `normalize_semantic` + `verify()` asserting REJECT / SURFACE /
    ACCEPT-eligible per verdict; concern-attribution matrix (fully attributed /
    entry_ids-only / unattributed); multibyte-content attribution round-trip; invalid-UTF-8
    request rejection.
  - Live integration test `tests/test_invoke_live.py` gated on `SLOPSLAP_LIVE=1` (matches the
    repo's existing `SLOPSLAP_FSYNC` env convention; reports pytest SKIP when unset, never a
    silent pass) — one real invocation through the same adapter asserting envelope + contract
    parse + positive-denial (sentinel token absent, tool access refused). Run once during
    the spike; evidence recorded below.

## File changes

- NEW `scripts/slopslap_invoke/__init__.py`, `invoke.py`, `contract.py`
- NEW `tests/test_invoke.py` (deterministic), `tests/test_invoke_live.py` (env-gated),
  `tests/fixtures/invoke/recorded_invocation.json`
- THIS doc gains the evidence section; README + Changelog; version bump ×2
  (`.claude-plugin/plugin.json`, `tests/test_scaffold.py:69`)

## Configuration changes

None. Model + timeout are function parameters with defaults; no new config surface until #17
decides it needs one.

## Error handling and failure modes

All environmental failures are explicit `InvocationResult` statuses (above). Contract-level:
parse failure → verdict `"ambiguous"` (the seam's enum term — pass-2 A2/S3), which the
verify engine already treats as non-shippable (SURFACE) — a broken model invocation can
never silently pass verification. Deterministic Layer 1 owns hard accept/reject regardless
(spec isolation contract).

## Security implications

- **Untrusted-input threat model (pass-3 P3-3):** the three request fields carry
  attacker-controllable document text; embedded instructions could try to steer the model
  toward `clean` or forged copied ranges. Standing mitigations: (a) deterministic Layer 1
  owns hard accept/reject — no injected `clean` can override a deterministic failure;
  (b) forged ranges fail the byte-for-byte ledger-range match → `ambiguous`; (c) a `clean`
  verdict only lifts BLOCKED→ACCEPT when every deterministic layer already passed. The
  spike ships ONE adversarial fixture (document text demanding "emit clean") through the
  contract parser as a smoke case; the FULL injection-resistance suite (delimiter breaks,
  role-play instructions, forged ledger text) is deliberately DEFERRED to #17 (semantic
  verify) and #28 (e2e validation golden), where the verifier's judgment — not the
  transport this spike proves — is the artifact under test. Recorded as a named follow-up.
- No `shell=True`; argv list + stdin payload — no interpolation of document text into a shell.
- Document text leaves the machine to the Anthropic API under the user's existing Claude Code
  auth — same trust boundary the plugin already operates in (the user is already running
  Claude Code on these files). No NEW exfiltration surface.
- Tool lockdown denies the fresh session file/network tools — the payload is its whole world.
- Recorded fixture content reviewed before commit (no secrets, no private text).

## Platform / external dependencies

platform_apis:
- api: `claude -p --model <m> --output-format json --no-session-persistence` + ONE no-tools lockdown flag (exact argv pinned by the live probe from candidates `--disallowedTools` / `--allowedTools` empty / `--permission-mode`; the candidate list does NOT ship — pass-2 A5) subprocess on the host Claude Code CLI (v2.1.207 probed)
  feasibility: verified via spike — spike status at design time: PENDING (Step-4 F4/S1); "verified" becomes true ONLY when the live run is recorded to tests/fixtures/invoke/recorded_invocation.json AND the Evidence section below is filled with the positive denial result, IN THIS SAME PR before it merges; Step 9's runtime-surface check gates on that recorded evidence existing
  failure: fail-loud
  note: every environmental failure maps to an explicit InvocationResult status; contract failures map to verdict="ambiguous" which verify treats as non-shippable (SURFACE). The single exact lockdown argv is pinned by the live probe's positive denial test and asserted in tests — if NO candidate denies sentinel access, the spike FAILS (it does not ship asserted-only)

## Multi-PR assessment

Single PR. Additive module + tests + docs; no existing-module changes.

## Provenance

Own draft authored blind (main loop, Fable 5), then synthesized with the GPT Soul peer
proposal (`docs/reviews/peer-rawgentic-peer-problem-26-2026-07-12.md`). Peer contributions
adopted: closed `invoke_semantic` API; empty-temp-cwd isolation; process-group timeout kill;
requested-vs-reported model check; versioned contract-v1 with local strict schema validation;
stable diagnostic concern codes (ambiguous-verdict failures); synthetic-only fixture policy;
fake-CLI failure-mode test matrix; skip-visible live gate. Peer risks carried into implementation: `--no-session-persistence`
alone is not the freshness guarantee (the bundle is); empty-allowlist flag syntax must be
verified live; envelope shape is a transport contract that can drift (fixture-pinned,
fail-closed); recorded success proves a snapshot, not permanent availability (versions
recorded).

## Evidence (live probe, 2026-07-12 — recorded)

Full machine-observable record: `tests/fixtures/invoke/probe_evidence.json` (synthetic sentinel
token — random, not a secret; env values redacted).

- **CLI:** `claude` v2.1.207 at `~/.local/bin/claude`. **Auth:** the host's logged-in Claude
  Code credentials (the plugin's real config); no API key, no credential file read.
- **Every load-bearing flag confirmed on the probed CLI** via `claude --help`: `-p`,
  `--model`, `--output-format json|stream-json`, `--no-session-persistence`, `--tools`,
  `--strict-mcp-config`, `--mcp-config`.
- **Pinned lockdown argv:**
  `-p --model <m> --output-format json --no-session-persistence --tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}'`
- **Positive-denial result (three-way differential — machine-observable, NOT model prose):**
  1. **Control (no lockdown):** `init` reported 162 tools / 11 MCP servers; the model
     invoked `Read` and disclosed the sentinel token — leak count **3**. Proves the
     sentinel is genuinely reachable when tools exist.
  2. **`--tools "" ` only (INSUFFICIENT):** built-in `Read` gone (130 tools, all MCP), but
     the MCP surface stayed live — the model invoked `mempalace_*`. Leak 0 here only for
     lack of a filesystem read path; the live MCP surface is the P3-1 isolation hole.
  3. **Full lockdown (SUFFICIENT):** `init` reported **`tools: []` and `mcp_servers: []`** —
     zero tool surface by construction; **zero** `tool_use`; sentinel leak **0**. The
     model's prose falsely claimed "Read tool work fine" — correctly ignored, since the
     machine-observable `init` event is authoritative (exactly the pass-3 P3-2 requirement).
- **Fresh-context / auth:** the invocation ran under real host auth in a new process; the
  `init` event is the machine-observable proof of the empty tool surface. Load-bearing
  timeout, envelope-parse, and model-mismatch behaviors are exercised by the deterministic
  fake-CLI suite (Task 3).
- **Live invocation THROUGH the shipped `invoke_semantic` adapter (Task 4):** a real call
  with a synthetic original + faithful synonym revision returned `{"verdict":"clean",
  "concerns":[]}`, runner `status=ok`, duration **11.3s**, no diagnostic — recorded to
  `tests/fixtures/invoke/recorded_invocation.json`. The gated live test
  (`tests/test_invoke_live.py::test_live_invocation_through_adapter`, `SLOPSLAP_LIVE=1`)
  passed against real `claude` in **39.8s**; unset, it SKIPS (CI has no auth). This closes
  AC1–AC4: mechanism proven end-to-end through shipped code, auth/model/timeout/response
  contract exercised, fresh context machine-proven, recorded fixture + gated test checked in.
