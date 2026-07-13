# Peer Consult — .rawgentic-peer-problem-27.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Create a production-facing `slopslap_assemble` package alongside the existing scan, verification, invoke, and apply packages. Its public API should expose two phases: `audit_document(...) -> AuditResult` and `run_candidate(...) -> RunResult`. `audit_document` reads immutable source bytes once, classifies genre using declared/path hints, performs the deterministic scan, derives authorized ranges, extracts protected spans and invariant regions, builds the ledger, and returns one immutable aggregate. `run_candidate` accepts that aggregate plus a candidate edit-script, verifies against the exact audited bytes and ledger, and calls `apply_selective(..., write=False)` only when verification is shippable. A thin JSON CLI should expose `audit` and `run` subcommands; command prose can generate edits between them without moving policy into the assembler. Every stage emits the same typed envelope, and the orchestrator stops at the first failed, blocked, or aborted stage.

## Key decisions

- Use `scripts/slopslap_assemble/` as a sibling package, with orchestration only: `contracts.py` for typed JSON contracts, `assemble.py` for APIs, and `cli.py` for entry points. Do not place it in verification because audit, verification, and application are peers in this workflow.
- Read the document once at audit start. Carry `source_path`, raw `source_bytes` internally, `source_sha256`, byte length, and format. Before verify or apply, reject if the current file digest differs; all byte offsets and ledger evidence belong to the audited snapshot.
- Define `AuditResult` with: contract/schema version, run ID, source identity and digest, format, declared/path genre inputs, resolved genre/confidence/reason, scan metrics and diagnoses, authorization state (`authorized`, `reject_all`, or `locality_unverified`) plus ranges, protected spans, invariant regions, canonical ledger or lossless ledger serialization, and `ledger_sha256`. Do not overload `[]` and `None`; encode their meanings explicitly.
- Order stages as: load snapshot → classify genre → deterministic scan/diagnosis → protected-span extraction → invariant-region extraction → ledger build → candidate parse/normalization → three-layer verify → conditional dry-run apply. Genre must be resolved before metrics and diagnoses, using explicit `declared` and `path` hints supplied at the API/CLI boundary.
- Make the candidate edit-script an explicit input, not part of `AuditResult`. Normalize it into sorted, non-overlapping `Edit` values and fail during `candidate` stage for malformed bounds, invalid encoding, overlap, or source-digest mismatch.
- Use a uniform `StageResult` envelope: `{stage, status, code, message, data, errors, warnings, started_at, duration_ms}`. Status is one of `ok`, `blocked`, `failed`, or `aborted`; errors contain stable `{code,message,details,retriable}` objects. A top-level `RunResult` contains contract version, run ID, overall status, ordered stage results, audit summary, verification result, and apply report.
- When a stage fails or blocks, append explicit `aborted` results for every downstream stage with `code: upstream_not_ok` and the causal stage/code. Never return an apparently successful partial run and never convert exceptions into an empty scan, empty manifest, clean semantic result, or no-op apply.
- Treat verifier outcomes as policy results, not infrastructure exceptions: `ACCEPT` plus `semantic_status=clean` proceeds; `REJECT`, `ASK`, `SURFACE`, blocked proposal status, or non-clean semantic status produces a blocked verify stage and an aborted apply stage.
- Keep semantic selection injectable. The production CLI chooses the live semantic function only under the established live gate; the offline dry-run test injects the clean stub explicitly. The assembler should not silently choose a clean stub merely because live mode is absent.
- For `write=False`, still invoke `apply_selective` after an acceptable verification so the acceptance test covers edit consumption, selective-apply reporting, final digest calculation, and the no-mutation guarantee. Actual command mutation remains outside #27.
- Provide CLI commands such as `slopslap-assemble audit --path ... [--declared-genre ...]` and `slopslap-assemble run --path ... --edits ... --dry-run [--declared-genre ...]`. Both emit exactly one JSON `RunResult` to stdout, diagnostics to stderr, and stable nonzero exit codes for failed versus policy-blocked runs.
- Build against lower-level public modules rather than the eval runner. Shared pure helpers or fixtures may be extracted, but fixture assumptions, seeded-candidate conventions, hardcoded semantic cleanliness, and eval-only `RunResult` semantics must not become production contracts.
- The golden should include an ACCEPT case asserting exact stage order, stable source/ledger digests, populated protected and invariant evidence, authorized edit locality, clean three-layer verification, `apply.status` success, expected final digest/content, `mutated=false`, no backup, and unchanged source bytes/digest on disk.
- The golden should also include at least two blocked cases: an edit outside authorized ranges and an edit that changes a protected span or invariant. Assert verification is non-shippable, apply is explicitly aborted, the file remains byte-identical, and no backup or staged artifact is created. Add a malformed edit-script case to prove failures stop before verification.
- Test the ambiguous locality state separately: `locality_unverified` must reach verification as an explicit policy state and produce `ASK`/blocked behavior, while `reject_all` must reject any nonempty candidate. This guards the critical `None` versus empty-list distinction.

## Risks

- Calling `scan_prose.py:main()` in-process could couple orchestration to CLI behavior or defeat its subprocess isolation. Prefer a library API if available; otherwise use a narrowly specified subprocess adapter with timeout, exit-code, stdout JSON, and stderr capture.
- Re-reading the source independently in audit, verification, and apply can create time-of-check/time-of-use drift. Snapshot digests must be checked at every boundary, and apply must verify the same original bytes represented by the ledger.
- Serializing a rich `Ledger` object may not be stable or reconstructable. Define a versioned canonical manifest/ledger representation and verify its digest rather than relying on Python object serialization.
- A clean offline semantic stub proves plumbing and deterministic safety layers, not live semantic quality. The result must label semantic execution mode so offline acceptance cannot be mistaken for live assurance.
- Treating all non-ACCEPT decisions as generic errors would erase actionable distinctions among unsafe edits, missing locality evidence, and surfaced concerns. Preserve the complete verifier result while mapping it to the uniform blocked stage status.
- If genre is classified after diagnoses or recomputed in separate stages, metric suppression and authorization can disagree. Resolve it once and thread the same result throughout the audited snapshot.
- An empty candidate may be mistaken for a successful suggestion. Define its policy explicitly—prefer a successful no-op only when the audit is clean/reject-all, otherwise return blocked with `candidate_empty` so missing model output is visible.
- The apply engine may call verification again through `verify_fn`. The adapter must ensure the same ledger, authorization state, semantic function, and audited digest are used, and should expose whether verification was reused or repeated to avoid divergent results.
- Embedding source bytes in CLI JSON can leak document content and create oversized envelopes. Keep bytes internal; expose digests, lengths, structured evidence, and only bounded/redacted error context.
- Stable timestamps and durations make golden snapshots brittle. Assert their presence/type while comparing deterministic semantic fields, or allow an injectable clock in tests.

## Sketch

contracts:
  AuditResult = {
    schema_version, run_id,
    source: {path, format, byte_length, sha256},
    genre: {declared, path_hint, resolved, confidence, reason},
    scan: {metrics, diagnoses},
    authorization: {state, ranges},
    manifest: {protected_spans, invariant_regions},
    ledger: {canonical, sha256}
  }

  StageResult[T] = {
    stage, status: ok|blocked|failed|aborted,
    code, message, data: T|null,
    errors: [{code, message, details, retriable}], warnings,
    started_at, duration_ms
  }

  RunResult = {
    schema_version, run_id, status,
    stages: [StageResult],
    audit, verification, apply
  }

API:
  audit_document(path, *, format, declared_genre=None, path_hint=None) -> RunResult
  run_candidate(audit, edits, *, semantic_fn, write=False, apply_config=None) -> RunResult
  assemble(path, edits, *, format, declared_genre=None, semantic_fn, write=False) -> RunResult

flow:
  snapshot = load_once(path)
  genre = classify_genre(snapshot.bytes, declared=declared_genre, path=path_hint or path)
  scan = deterministic_scan(snapshot, genre)
  auth = encode_authorization(authorized_ranges_from_diagnoses(snapshot.bytes, format, genre))
  manifest = {
    protected_spans: extract_protected_spans(snapshot.bytes),
    invariant_regions: build_invariant_regions(snapshot.bytes)
  }
  ledger = build_ledger(snapshot.bytes, manifest)
  audit = freeze(snapshot, genre, scan, auth, manifest, ledger)
  candidate = parse_and_validate(edits, against=audit.source)
  verification = ledger.verify(snapshot.bytes, candidate, ledger,
      authorized_ranges=authorization_policy(auth), semantic_fn=semantic_fn)
  if verification.decision != ACCEPT
     or verification.proposal_status != ACCEPT
     or verification.semantic_status != clean:
       verify.status = blocked
       apply.status = aborted
  else:
       assert_current_digest(path, audit.source.sha256)
       apply = apply_selective(path, candidate,
           verify_fn=bound_same_audit_verifier, write=write)

exit codes:
  0 = completed successfully
  2 = policy blocked
  3 = invalid input/contract
  4 = stage execution failure

---
_Peer proposal (report-only). Synthesize at your discretion._
