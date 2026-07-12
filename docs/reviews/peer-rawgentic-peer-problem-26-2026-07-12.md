# Peer Consult — .rawgentic-peer-problem-26.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Standardize on a small synchronous Python adapter around a one-shot `claude -p` subprocess. Send a canonical, versioned request over stdin; launch a new process for every semantic check with an explicit model, JSON output, no tools, no session persistence, and a bounded timeout. Treat the CLI response as untrusted data: extract the assistant payload, strictly validate the application JSON, and map every transport, timeout, or parsing failure to `inconclusive`. Prove the path once through the installed plugin entry point, preserve a sanitized invocation transcript as a fixture, and keep live tests opt-in while CI continuously replays the fixture and exercises failure behavior with a fake executable.

## Key decisions

- Use `claude -p` via `subprocess.run` as the supported mechanism. It uses the actual Claude Code installation and logged-in authentication, adds no Python dependency, and fits the synchronous `semantic_fn` seam. Do not introduce direct Anthropic SDK/API support in this spike.
- Create one adapter boundary such as `invoke_semantic(original, revision, ledger_canonical, *, model, timeout_s, executable)`. Never accept arbitrary prompts, session identifiers, extra messages, or CLI arguments through this semantic API.
- Construct a versioned request containing only `original`, `revision`, and the canonical invariant ledger. Serialize it deterministically and place it inside clearly delimited data fields beneath a fixed semantic-verifier instruction. Send it through stdin rather than argv to avoid command-line length limits and accidental process-list exposure.
- Require the model to return exactly an application object shaped as `{ "verdict": "clean|concerns|inconclusive", "concerns": [{"code": "...", "message": "..."}] }`. Use `--output-format json` for the CLI transport envelope, then parse the assistant result as JSON and validate allowed keys, enum values, types, and bounded field sizes locally. Do not rely on prompt wording as schema enforcement.
- On malformed envelopes, non-JSON payloads, schema violations, nonzero exits, signals, or timeouts, return a normalized `inconclusive` concern with a stable internal code such as `semantic_transport_error`, `semantic_timeout`, or `semantic_invalid_response`. Never infer `clean` from missing or partial output, and never let semantic output override Layer-1 hard failures.
- Enforce fresh context structurally: start a new CLI process for every call; always pass `--no-session-persistence`; prohibit `--continue`, `--resume`, session IDs, and fallback models in the adapter; pass no prior messages; and expose only the three allowed request fields. Set `--allowedTools` to an empty allowlist so the invocation cannot retrieve repository files, transcripts, or rewriter artifacts.
- Run the child in a newly created empty temporary working directory to prevent project-file discovery. Preserve the user's normal environment only as needed for Claude Code authentication and plugin installation; do not copy conversation/session variables into the child if any are identified. Delete the temporary directory after completion.
- Make model selection explicit and observable. Resolve it from the function/configuration argument, with an optional documented environment override for the plugin command; reject an empty model. Pass exactly one `--model` value, omit `--fallback-model`, and record the requested model plus the model reported by the JSON envelope. A mismatch makes the result inconclusive.
- Inherit Claude Code's existing logged-in credentials. Do not read, copy, print, fixture, or inspect credential files. The live probe records only that authentication succeeded, along with CLI version, exit status, elapsed time, and redacted model metadata. Authentication failure is a transport-level inconclusive result with actionable diagnostics.
- Apply a configurable wall-clock timeout with a conservative default such as 60 seconds. On expiry, terminate the process, escalate to kill if necessary, collect bounded diagnostics, and return `semantic_timeout`. Unit tests must prove the timeout path using a controllable fake CLI rather than spending model calls.
- Check in: the adapter contract tests; a fake-CLI test suite covering success, invalid JSON, invalid schema, nonzero exit, model mismatch, oversized output, and timeout; one sanitized canonical request; the exact sanitized raw CLI JSON envelope from the successful probe; the expected extracted object; and a fixture-replay test that runs in ordinary CI.
- Add one opt-in live integration test gated by an explicit variable such as `SLOPSLAP_RUN_LIVE_CLAUDE=1`. It should otherwise report a pytest skip, not silently pass. When enabled, it must require the executable, explicit model, and usable auth, invoke through the same adapter under the installed plugin workflow, assert contract-valid output, and emit a sanitized evidence record.
- The feasibility report should document the exact redacted argv, stdin contract version, CLI version, plugin entry path used, requested/reported model, authentication mode at a non-secret level, fresh-context controls, tool isolation, timeout and termination behavior, observed response envelope, fixture provenance and hashes, CI gating, known limitations, and the stable callable contract handed to issue #17.

## Risks

- `--no-session-persistence` prevents saving the new session but may not alone guarantee that no ambient context is loaded. The new-process rule, absence of resume flags, empty working directory, empty tool allowlist, and closed request type must all be tested and documented as the enforcement bundle.
- Claude Code may still load user-level instructions or settings required by the real installation. The report must distinguish those ambient configuration inputs from prohibited rewriter conversation state; stronger isolation must not replace `HOME` if doing so breaks the credentials being tested.
- The precise syntax for an empty `--allowedTools` value must be verified by the live spike. If the CLI cannot express an empty allowlist reliably, the spike is not complete until a confirmed no-tools invocation mode is found and fixture-backed.
- CLI JSON is a transport envelope, not necessarily application-schema enforcement, and its fields may change between CLI releases. Keep envelope extraction isolated, fixture-tested, and fail closed to `inconclusive` on unknown shapes.
- A recorded successful response proves compatibility with one CLI and model snapshot, not permanent platform availability. Record versions and make the opt-in live test easy to rerun after CLI upgrades.
- Model aliases may move over time. Recording both requested and reported model improves evidence, but reproducibility may require a pinned model identifier where the installed CLI supports one.
- Captured prompts and outputs can contain sensitive source text. Use intentionally synthetic probe inputs for checked-in fixtures, redact diagnostics, cap stdout/stderr retention, and never fixture credentials or real user content.
- Killing only the immediate process may leave descendants alive on some platforms. Launch the CLI in its own process group and terminate the group on timeout where supported.
- Skipping the live test in CI can conceal later authentication or platform breakage. Mitigate with a documented manual/release check and optionally an authenticated scheduled job outside ordinary unauthenticated CI.

## Sketch

Plugin command / future #17 semantic_fn
  -> invoke_semantic(original, revision, canonical_ledger, model, timeout)
  -> build contract-v1 prompt from exactly those three values
  -> create empty temporary cwd
  -> spawn new process group:
       claude -p --model <explicit> --output-format json
              --allowedTools <empty> --no-session-persistence
     stdin = prompt; no resume/continue/fallback flags
  -> timeout/nonzero/auth failure => stable inconclusive concern
  -> parse bounded CLI JSON envelope
  -> verify reported model when available
  -> parse assistant payload as one strict JSON object
  -> validate verdict and concerns schema
  -> return raw validated object for normalize_semantic

CI:
  fake CLI contract tests + sanitized fixture replay = mandatory
  real invocation test = skipped unless SLOPSLAP_RUN_LIVE_CLAUDE=1

Spike acceptance:
  one successful synthetic invocation launched through the installed plugin path,
  exact sanitized request/envelope/expected result checked in,
  fresh-context and timeout controls demonstrated,
  feasibility report supplies #17 with the adapter API and failure semantics.

---
_Peer proposal (report-only). Synthesize at your discretion._
