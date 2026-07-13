# Design — #27 live-orchestration seam (the assembler)

- Date: 2026-07-12
- Issue: [#27](https://github.com/3D-Stories/slopslap/issues/27) · Epic [#16](https://github.com/3D-Stories/slopslap/issues/16) Tier 2
- Complexity: complex_feature (Full WF2)
- Depends on: #26 (platform-feasibility ✓), #17–#20 ✓. Blocks: #28, #29.

## 1. Goal

v0.1 shipped deterministic prose-repair mechanics + a FROZEN eval demonstration (seeded candidate
edits). The live, model-in-the-loop path — run audit/verify/apply on an **arbitrary** document —
is not assembled. `#17–#24` are components with no assembler (WF5 finding F1). This issue builds
the missing seam: one module that chains **audit → verify → (suggest) → apply** end-to-end for any
doc, with defined command entry points, stage ordering, explicit stage-boundary data contracts,
legible error propagation, and an **end-to-end dry-run acceptance test**.

## 2. Scope boundaries (kept deliberately tight)

| In scope for #27 | Deferred to |
|---|---|
| New seam package that derives a ledger manifest from an arbitrary doc, verifies a candidate edit-script, and (dry-run) applies | — |
| Stage-boundary data contract (single `AuditResult` aggregate) + a uniform stage-result envelope | — |
| End-to-end **dry-run** golden (`write=False`): ACCEPT-flows-clean + REJECT-blocks-mutation, offline stub | — |
| Live semantic-fn factory mirroring `eval/semantic.py` (`SLOPSLAP_LIVE` gate) | — |
| Command entry-point CONTRACT documented (what a command shells out to) | apply flip → #29 |
| The live model *generating* the edit-script; suggest→verifier deterministic tests | #23 |
| Flipping `commands/apply.md`'s `mutation_unavailable` sentinel | #29 (dep #21+#27) |
| Live SAFETY golden (assert reject/blocked with a real model) | #28 |
| `cross_refs`/`defined_terms` whitelist lag (#36) in `atoms.CHECK_EXTRACTORS` + `eval/loader.validate_manifest` | #28 (see §7) |

**Why the split holds:** #27 is *plumbing + proof-of-safety-without-a-model*. It must not gold-plate
into live generation (#23/command-prose) or command enablement (#29). The dry-run golden proves the
seam is correct and safe using the offline clean stub; #28 later proves it under a real model.

## 3. Approaches considered

**A. New `scripts/slopslap_assemble/` package (RECOMMENDED).** A sibling to `slopslap_verification`,
`slopslap_invoke`, `slopslap_apply`, following the established package-per-subsystem convention.
Imports the lower-level modules; owns the arbitrary-doc manifest builder, the `AuditResult`
aggregate, the stage-result envelope, the top-level `run_seam`, the live-semantic-fn factory, and a
thin CLI. Pros: matches existing structure; keeps eval harness untouched (it stays a frozen proof,
not repurposed); clean import graph. Cons: one more package (acceptable — it is the assembler the
epic explicitly wants).

**B. Extend `eval/runner.py`.** Rejected. The eval runner is fixture-shaped (`fixture`/`baseline`
fields, frozen seeded candidates, `RunResult`/`State` enum) and documented as a *proof harness, not
the production seam*. Repurposing it would couple arbitrary-doc orchestration to fixture semantics
and risk regressing the v0.1 proof.

**C. Put the seam in `slopslap_verification`.** Rejected. Verification is one stage; the assembler
spans scan→verify→apply and would invert the dependency direction (verification would import apply).

Recommendation: **A** — new `scripts/slopslap_assemble/` package.

## 4. Data contracts (the core of #27)

> Peer-consult (GPT Soul via Codex, `docs/reviews/peer-rawgentic-peer-problem-27-2026-07-12.md`)
> contributed: the explicit `authorization` state encoding (§4.1), the `ok|blocked|failed|aborted`
> stage vocabulary (§4.3), the source-digest boundary re-check (§4.2), and the CLI-hygiene rules
> (§4.4). Folded in below with these attributions.

### 4.1 `AuditResult` — the single audit-stage aggregate

Produced by `audit_document(doc)`, consumed by verify/apply. Fields:

```
AuditResult(
  schema_version: int = 1,
  run_id: str,                             # deterministic: short hash of source_sha256 (golden-stable, no uuid/clock)
  source_path: str,                        # RESOLVED absolute path of the audited file (adv A6: policy binds to file identity, not just content)
  source_sha256: str,                      # sha256(doc) — provenance/anti-drift snapshot identity
  byte_length: int,
  fmt: str,                                # "markdown"|"text"
  genre: str,                              # classify_genre resolved genre
  genre_confidence: str,                   # "high"|"medium"|"low"
  genre_reason: str,
  audit_status: str,                       # "clean"|"flagged" (adv A1) — flagged iff ANY metric emitted a location OR any doc-level soft_flag is true
  metrics: dict,                           # compute_all result (measure-only; consumer: audit_status derivation + CLI surfacing)
  authorization: dict,                     # {"state": "authorized"|"reject_all"|"locality_unverified", "ranges": [{start_byte,end_byte}]}  (peer contribution — see below)
  protected_spans: list[dict],             # [{start_byte,end_byte,sha256,kind}] (#18)
  invariant_regions: list[dict],           # [{start_byte,end_byte,checks[]}] (#19 autoledger)
  ledger: Ledger,                          # build_ledger(doc, manifest) — the in-process verify contract object
)
```

**`audit_status` (adversarial finding A1 — cleanliness must survive the `reject_all` conflation).**
`authorization.state == "reject_all"` deliberately covers BOTH a genuinely clean doc AND a
doc-level-only-flagged doc (the `[]` overload inherited from `diagnoses`). `audit_status` preserves
the distinction the authorization state erases: `clean` = no metric emitted any location and no
doc-level `soft_flag`; `flagged` otherwise. The empty-candidate policy (§10 case 8) keys on
`audit_status`, never on `authorization.state` — a missing model output on a flagged doc is always
visible (`blocked`/`candidate_empty`), even when the authorization is reject-all.

**Pipeline-run note (self-review F4 resolution).** The seam runs the scan pipeline twice: once via
`compute_all` (consumers: `audit_status`, `metrics`) and once inside
`authorized_ranges_from_diagnoses` (owns range derivation). Genre is resolved ONCE and threaded to
both. Accepted cost — target docs are prose-sized; upgrade path = expose a combined
ranges+metrics API in `diagnoses.py` if profiling ever cares.

**Authorization state (peer contribution — resolves the `[]`/`None` overload).** The analysis flagged
that `diagnoses.authorized_ranges_from_diagnoses` overloads `[]` (clean OR doc-level-only-flagged →
reject-all) and that a *separate, external* `None` means locality_unverified/ASK. The seam encodes this
explicitly instead of leaking the ambiguity downstream:
- ranges non-empty → `state="authorized"`, pass `ranges` to `verify(authorized_ranges=...)`.
- ranges `== []` → `state="reject_all"`, pass `[]` (verify's `edit_locality` rejects any edit against an empty editable set).
- deriver unavailable / undecidable → `state="locality_unverified"`, pass `None` (verify fails CLOSED to ASK). #27's audit path always derives (a parser-unavailable failure surfaces as `diagnosis_error`, not this state), so `locality_unverified` is reachable only at the `run_candidate` API boundary (a caller handing in an `AuditResult` with that state); the golden exercises it via that API path. No CLI flag emits it (round-2 L3: the earlier "CLI opt-out" claim was dropped — the flag was never built and isn't needed for #27).

`build_manifest(doc)` is the **missing glue**: `{invariant_regions: build_invariant_regions(doc),
protected_spans: extract_protected_spans(doc)}`, then `build_ledger(doc, manifest)`. No defensive
empty-region filter is needed — confirmed at source: `autoledger.build_invariant_regions` never emits a
region with empty `checks` (`if not checks: continue`, autoledger.py:110-111), and `build_ledger` only
raises `LedgerBuildError` on an empty/OOB/unknown check (ledger.py:183-187). A doc with no invariant
regions and no protected spans yields an **empty-but-valid** ledger (`entries=[]`, `protected_spans=[]`)
— not an error — which `verify` treats as "no invariants to violate".

The candidate edit-script is an **explicit input to verify/run, never part of `AuditResult`** (peer
key-decision): the audit is snapshot-immutable; edits arrive separately from suggest/model/dry-run seed.

### 4.2 Stage ordering + what flows between stages

```
                 doc: bytes  (+ declared_genre?, path?, fmt="markdown")
                     │
   ┌─────────────────▼──────────────────┐
   │ AUDIT                               │
   │  classify_genre(doc, declared, path)│──► genre
   │  authorized_ranges_from_diagnoses(  │──► authorized_ranges   (genre threaded in)
   │      doc, fmt, genre)               │
   │  extract_protected_spans(doc)       │──► protected_spans
   │  build_invariant_regions(doc)       │──► invariant_regions
   │  build_manifest → build_ledger      │──► ledger
   └─────────────────┬──────────────────┘
                     │ AuditResult
   ┌─────────────────▼──────────────────┐   edits: list[Edit]  (from suggest/model, or seeded in dry-run)
   │ VERIFY                              │◄── candidate edit-script
   │  ledger.verify(doc, edits, ledger,  │──► verify_result {decision, proposal_status,
   │    authorized_ranges, semantic_fn)  │       semantic_status, findings, hunks, ledger_sha256}
   └─────────────────┬──────────────────┘
                     │ verify_result
   ┌─────────────────▼──────────────────┐
   │ APPLY (dry-run in #27)              │
   │  apply_selective(path, edits,       │──► apply report {status, mutated, backup, ...}
   │    verify_fn=<bound verify>, write) │       write=False ⇒ mutated=False, file untouched
   └─────────────────────────────────────┘
```

`verify_fn` passed to `apply_selective` is `ledger.verify` **bound** with this run's ledger +
authorized_ranges + semantic_fn (a closure `lambda original, edits: verify(original, edits, ledger,
authorized_ranges=..., semantic_fn=...)`), so apply re-verifies against the live original each
attempt (apply's re-verify loop rebuilds from untouched original — the closure must not capture a
stale revision). The SAME bound verifier serves both the seam's verify stage and apply's re-verify
loop — one audit, one policy (peer risk: divergent verification).

**Source-identity boundary re-check (peer + adversarial A6 — TOCTOU and identity guard).** All byte
offsets, spans, and ledger evidence belong to the audited snapshot **of a specific file**.
`run_candidate` binds both: (1) the resolved target path must equal `AuditResult.source_path`
(an `AuditResult` cannot be replayed against a different file that happens to hold identical
bytes — adv A6), and (2) the file's current sha256 must equal `source_sha256`. Either mismatch →
verify/apply stage `failed` / `code="digest_mismatch"` (path mismatch: `code="path_mismatch"`),
downstream aborted. (`apply_selective` additionally re-checks path/dev/inode + content sha at
replace time — the seam check catches drift *earlier*, before backup creation.)

### 4.3 Stage-result envelope (error propagation) — peer status vocabulary folded in

Every stage returns a uniform envelope so a failure is legible and never silent. Status vocabulary
adopts the peer's four states (richer than a bare ok/error — a **policy** block reads differently
from an **execution** failure):

```
StageResult(stage: str,                    # "audit"|"candidate"|"verify"|"apply"
            status: str,                    # "ok" | "blocked" | "failed" | "aborted"
            code: str,                      # stable slug: "ok","genre_error","diagnosis_error","protected_span_error",
                                            #   "ledger_build_error","invalid_edits","candidate_empty","verify_not_shippable",
                                            #   "apply_blocked","digest_mismatch","upstream_not_ok"
            message: str,
            data: <AuditResult|edits|verify_result|apply report|None>,
            errors: list[dict], warnings: list[str])

RunResult(schema_version: int, run_id: str, status: str,   # overall = worst stage status
          stages: list[StageResult], audit, verification, apply)   # summaries; apply/verification None when not reached
```

- `ok` — stage succeeded.
- `blocked` — a **policy** stop, not a crash: verify returned non-shippable (`decision != ACCEPT`, or
  `proposal_status != ACCEPT`, or `semantic_status != clean`), or the candidate was empty on a
  non-clean audit. The full verify_result is preserved in `data` — non-ACCEPT is never collapsed to a
  generic error (peer risk). Apply is then `aborted`.
- `failed` — an execution error (bad bytes, parser missing, malformed edits, digest mismatch).
- `aborted` — a downstream stage that did not run because an upstream stage was not `ok`; carries
  `code="upstream_not_ok"` + the causal stage (peer key-decision: emit explicit aborted results,
  never a silent partial run).

`run_candidate`/`assemble` return one `RunResult`. Any exception inside a stage is caught and
converted to a `failed` envelope naming `code` — a stage never raises past the seam, and every stage
after the first non-`ok` is explicitly `aborted`. **No timestamps/durations in the envelope** — the
peer flagged them as golden-brittleness; #27 omits them (add an injectable clock later if a perf need
arises). `run_id` is a deterministic short hash of `source_sha256`, so goldens are stable.

**Overall status + exit-code mapping (adv A3 + self F2 — was undefined).** Overall `RunResult.status`
= the worst stage status under the total order **`failed` > `blocked` > `aborted` > `ok`** (an
`aborted` can never be worst in practice — it only exists downstream of a `failed`/`blocked`, which
outranks it). CLI exit code derives mechanically from (overall status, first non-ok code):

| Overall status | First non-ok `code` class | Exit |
|---|---|---|
| ok | — | 0 |
| blocked | any policy code (`verify_not_shippable`, `candidate_empty`, `apply_blocked`) | 2 |
| failed | contract/input codes: `invalid_edits`, `path_mismatch`, `digest_mismatch`, bad CLI args, unreadable/non-UTF-8 input (`genre_error`) | 3 |
| failed | execution codes: `protected_span_error`, `diagnosis_error`, `ledger_build_error`, `semantic_invocation_failed`, `apply` report `status=="error"` | 4 |

**Bad-bytes ownership (round-2 fix):** `classify_genre` runs FIRST in the audit stage and raises
`GenreError` on non-UTF-8 (genre.py:137-138), so ALL bad-bytes failures surface as `genre_error`
(exit 3) before `diagnoses`/`protected` ever run. `diagnosis_error` is therefore
parser-unavailable-only → exit 4, and each `code` slug is statically assigned to exactly ONE class
in the implementation (a `_EXIT_CLASS` dict) — no runtime judgment, no message sniffing.
`upstream_not_ok` tags only `aborted` stages and is never exit-determining — it deliberately has no
`_EXIT_CLASS` row. **Vocabulary rule (adv A4):** the words used by stage
envelopes are exactly `ok|blocked|failed|aborted`; the string `"error"` appears only INSIDE relayed
sub-reports (e.g. `apply_selective`'s `report["status"]`), and a relayed `status=="error"` report
makes the apply stage `failed` (exit 4), while a relayed `status=="blocked"` report makes it
`blocked` (exit 2). Malformed edit-scripts are ALWAYS a `candidate`-stage `failed` (adv A5) —
verify never sees them (`parse_edits` + bounds/overlap validation run in the candidate stage).

### 4.4 CLI hygiene (peer contribution)

`main(argv)` exposes `audit` and `run` subcommands, each emitting exactly one JSON `RunResult` to
stdout, diagnostics to stderr, with stable exit codes: **0** ok · **2** policy-blocked · **3** invalid
input/contract · **4** stage execution failure. **Source bytes are never embedded in the JSON**
(content-leak + oversized envelope): expose `source_sha256`, `byte_length`, structured evidence, and
the ledger as `{"canonical": ledger.canonical_obj(), "sha256": ledger.ledger_sha256()}` — never a raw
Python-pickled `Ledger`. The in-process API passes the live `Ledger` object directly (no serialization).

## 5. File changes

- **NEW** `scripts/slopslap_assemble/__init__.py` — package marker + `sys.path` bootstrap (mirrors siblings).
- **NEW** `scripts/slopslap_assemble/assemble.py` — `AuditResult`, `StageResult`, `RunResult`,
  `build_manifest`, `audit_document`, `run_candidate`, `assemble` (audit+run in one call),
  `live_semantic_fn`, `main(argv)` CLI (`audit` / `run` subcommands). One module (ponytail: split
  into contracts.py/cli.py only if it outgrows ~500 lines — the peer's 3-file layout is deferred,
  not adopted, to keep the diff minimal).
- **NEW** `tests/test_assemble_seam.py` — the end-to-end dry-run golden + unit tests.
- **EDIT** `scripts/slopslap_invoke/invoke.py` — additive optional `status_sink` out-param on
  `invoke_semantic` (adv A2, §7). Default-inert; return contract unchanged.
- **Audit metrics source:** the seam calls the library APIs directly (`extract_markdown`/
  `extract_text` + `compute_all(genre=...)`) — NOT `scan_prose.py:main()` in-process (peer risk:
  couples orchestration to CLI behavior). `authorized_ranges_from_diagnoses` re-runs the same
  pipeline internally (accepted double-run, §4.1); genre is resolved ONCE and threaded to both call
  sites (peer risk: suppression/authorization disagreement).
- **`live_semantic_fn` vs `eval_semantic_fn` (self-review F3):** deliberately NOT a reuse of
  `scripts/eval/semantic.py:eval_semantic_fn` — the seam factory must inject the `status_sink`
  (A2) and must not import from the eval proof-harness package into production. One-line-justified
  duplication of a ~6-line gate pattern.
- **EDIT** `README.md` — Assembler section + Changelog entry.
- **EDIT** `.claude-plugin/plugin.json` — version bump (patch).
- **EDIT** `tests/test_scaffold.py:69` — pinned version assert bump.
- **EDIT** dashboard `docs/planning/2026-07-12-16-v02-epic-dashboard.{md,html}` — #27 row.
- Command `.md` files: **documented contract only** in this PR (audit/suggest stay prose; apply stays
  disabled — flip is #29). No behavioral edit to `commands/apply.md`'s sentinel here.

## 6. Error handling & failure modes

(Vocabulary per §4.3 — `ok|blocked|failed|aborted`; "error" appears only inside relayed sub-reports.)

- **Non-UTF-8 doc** → `audit` stage `failed` / `code="genre_error"` or `"diagnosis_error"` (both raise on bad bytes); downstream stages `aborted`. Exit 3 (invalid input).
- **Pinned markdown parser unavailable** → `DiagnosisError`/`ProtectedSpanError` → audit `failed` (never a silent degraded scan). Exit 4 (execution).
- **Malformed edit-script (out of bounds / overlapping / bad base64)** → `candidate` stage `failed` / `code="invalid_edits"` — BEFORE verify runs (adv A5). Exit 3.
- **Empty authorized_ranges with edits present** (`reject_all`) → `ledger.verify` rejects via locality; verify `blocked` — full verify_result preserved. Exit 2.
- **`locality_unverified`** (ranges `None`) → verify fails CLOSED to ASK → `blocked`. Exit 2.
- **Semantic model verdict ambiguous/real** (successfully obtained) → policy: verify `blocked`. Exit 2.
- **Semantic INVOCATION failure** (subprocess/timeout/CLI-missing/parse — detected via the
  `status_sink`, §7) → verify stage `failed` / `code="semantic_invocation_failed"` (adv A2: an ops
  failure is not a policy verdict). Exit 4. Verify's internal fail-closed-to-ambiguous still holds
  underneath as defense-in-depth — the sink only reclassifies the stage, never weakens the verdict.
- **Path or digest mismatch at the run boundary** → `failed` / `code="path_mismatch"`/`"digest_mismatch"`; apply `aborted`. Exit 3.
- **Apply concurrent-edit / backup failure** → `apply_selective` fails closed; the relayed report's
  `status=="error"` → apply stage `failed` (exit 4); `status=="blocked"` → `blocked` (exit 2). `mutated=False` either way.
- **dry_run (`write=False`)** → `apply_candidate` calls `apply_selective(..., write=False)`: verify
  still runs, **a verified backup IS created first** (`create_verified_backup` runs before the
  `write` short-circuit — apply.py:138-147 vs 215-218; self-review F1), the report says
  `mutated=False`, and the SOURCE file on disk is byte-identical. The dry-run safety guarantee is
  "source unmutated", NOT "no artifacts": the golden points `BackupConfig.backup_dir` at a
  test-owned tmp dir and asserts the backup exists there + source untouched.

## 7. Platform / external dependencies

platform_apis:
- api: fresh-context `claude -p` subprocess invocation via slopslap_invoke.invoke.invoke_semantic on the local shell/runtime
  feasibility: verified via existing-call-site — scripts/slopslap_invoke/invoke.py:264 (invoke_semantic, proven by the #26 platform-feasibility spike, PR #32) and scripts/eval/semantic.py:20 (eval_semantic_fn SLOPSLAP_LIVE gate, wired by #17, PR #34; exercised end-to-end in the run_eval kukakuka path). The seam's live_semantic_fn factory reuses this exact call site — no new platform surface.
  failure: fail-loud
  surface: verify_result.semantic_status + proposal_status (BLOCKED unless semantic_status=="clean") — asserted in the golden's ACCEPT case. invoke_semantic is fail-closed: any subprocess/timeout/parse failure collapses to verdict="ambiguous", which the decision rule folds to SURFACE/ASK, never a silent ACCEPT; the dry-run/offline path invokes NO platform API (explicitly injected clean stub).

The offline seam path (dry-run golden, default) uses no platform API. The live path is precedented
exactly by #26/#17 — no unproven dependency.

**Typed invocation outcome (adv A2 — ops failure ≠ policy verdict).** `invoke_semantic` is a CLOSED
contract: returns EXACTLY `{"verdict","concerns"}`, `InvocationResult` never leaks, failures are
only logged (invoke.py:1-13, 310-315). The seam must still distinguish "the model judged this
ambiguous" (policy → `blocked`, exit 2) from "the invocation never succeeded" (ops → `failed`,
exit 4). Fix: an **additive optional out-param** on `invoke_semantic` —
`status_sink: Optional[dict] = None`. When passed, invoke_semantic records
`{"invocation_status": <ok|timeout|cli_missing|nonzero_exit|parse_error|model_mismatch|invalid_request>}`
into it before returning; the RETURN shape is unchanged and `None` (default) keeps today's behavior
byte-identical — the closed `{"verdict","concerns"}` doctrine holds. The seam's `live_semantic_fn`
passes a per-run sink; after `verify` returns, a sink status ≠ `ok` reclassifies the verify stage to
`failed`/`code="semantic_invocation_failed"` while the verdict inside verify stays fail-closed
ambiguous (defense-in-depth, unchanged). The offline stub never touches the sink (`ok` by
construction). This is the one modification to an existing module (`scripts/slopslap_invoke/invoke.py`)
— additive, default-inert, covered by unit tests (sink populated on injected timeout/missing-CLI;
absent sink identical to today).

**Sink completeness invariant (round-2 fix):** the sink is set to a non-`ok` value on **every**
non-clean return path of `invoke_semantic`, not just the enumerated `InvocationResult` statuses —
including the three internal-contract ambiguous returns: non-UTF-8 revision (invoke.py:289 →
`invalid_request`), malformed original/ledger at request build (invoke.py:307 → `invalid_request`),
and malformed ledger at response parse (invoke.py:318 → `parse_error`). A successfully-obtained
model verdict (real/ambiguous/clean) records `ok` — only those are policy. Unit tests cover the
internal-contract paths too (malformed-ledger input → sink non-`ok` → seam exit 4).

**Sink stickiness (round-2 adversarial):** `verify` calls `semantic_fn` exactly once per invocation
(single call site, ledger.py:334-336) — but `apply_selective`'s bounded re-verify loop invokes the
bound verifier repeatedly, so the semantic_fn may run multiple times per RUN. The sink is therefore
**sticky-worst**: a non-`ok` status, once recorded, is never overwritten by a later `ok` (a later
successful call must not launder an earlier timeout). Unit test: two sequential calls, first
failing, second ok → sink stays non-`ok`.

## 8. Security implications

- Apply mutates a user file: the seam always routes apply through `apply_selective` (backup-first,
  atomic, concurrent-edit guard) — never a raw write. #27's golden runs `write=False`, so no
  mutation occurs in tests.
- The seam passes UNTRUSTED doc bytes to `classify_genre`/scan/autoledger — all pure Python over
  bytes, no `eval`, no subprocess-with-doc-content except the isolated fresh-context `claude -p`
  (scrubbed env, empty tools/MCP, own process group — proven by #26).
- No secrets, no network beyond the model invocation the platform already sanctions.

## 9. #36 deferral (documented decision D-27a)

`autoledger._checks_for` emits `cross_refs`/`defined_terms` (autoledger.py:68,70); these are present
in `ledger._CHECK_KIND` (ledger.py:163-164) but MISSING from `atoms.CHECK_EXTRACTORS` (atoms.py:161-167,
5 entries) and `eval/loader.py:validate_manifest` (loader.py:147, 5-entry inline set). The #27 seam
routes through `ledger.verify`, whose Layer-2 `_L2_EXTRACT` is **kind-keyed** (has `cross_reference`
+ `defined_term`) and handles both correctly. The seam does NOT call `gates.preservation_region_scoped`
or `loader.validate_manifest`. **Therefore #27 does not trip #36.** The gap only bites the eval-fixture
pipeline; #28 (live golden) may route autoledger output through those gates, so #36 is folded into #28.
The seam's `build_manifest` uses only `build_ledger`'s own 7-entry `_CHECK_KIND` whitelist (which
already accepts cross_refs/defined_terms) — verified by a unit test in this PR.

## 10. Testing / acceptance

Suite: `pytest tests/ -q` (D7 local gate; has_ci=false). New `tests/test_assemble_seam.py`
(cases 6–9 peer contributions; cases 3/5/8/11/12 amended per the Step-4 loop-back findings):

1. **`build_manifest`** on an arbitrary doc → manifest with `invariant_regions` (each with non-empty
   `checks`) + `protected_spans`; `build_ledger` accepts it (incl. a doc with cross_refs/defined_terms
   checks — proves the seam's manifest path is not #36-gapped).
2. **`audit_document`** returns a well-formed `AuditResult` (genre classified, `audit_status`
   correct on a clean and a flagged doc, authorization state encoded, ledger valid via
   `validate_ledger`, `run_id` deterministic, `source_path` resolved).
3. **End-to-end dry-run ACCEPT golden (self-review F1 fix):** a doc + a benign in-authorized-range
   edit-script (offline clean stub injected explicitly) → `assemble(write=False)` with
   `BackupConfig.backup_dir` pointed at a test-owned tmp dir → stage order
   audit→candidate→verify→apply all `ok`, verify shippable, apply report `mutated=False`, expected
   `final_digest`; **the SOURCE file on disk is byte-identical** (the safety assertion) AND **a
   verified backup EXISTS in the tmp backup dir** (apply.py creates it before the `write=False`
   short-circuit — asserting reality, not the wish).
4. **End-to-end dry-run REJECT golden ×2:** (a) an edit outside authorized ranges; (b) an edit that
   changes a protected span / a number invariant → verify `blocked` (full verify_result preserved in
   `data`), apply stage `aborted` with `upstream_not_ok` and `data is None` (an aborted stage has NO
   apply report — round-2 fix: assert the stage status + absent data, not a `mutated` field that
   doesn't exist), **the source file byte-for-byte identical on disk**, and no backup created
   (verify blocks before apply is ever invoked — the no-artifact assertion is valid HERE, unlike
   case 3).
5. **Stage propagation + exit codes (adv A5 + F2):** non-UTF-8 doc → audit `failed`, all downstream
   stages explicitly `aborted`, CLI exit 3; malformed edit-script (overlap/out-of-bounds) →
   `candidate` stage `failed`/`invalid_edits` BEFORE verify runs (verify absent or aborted), exit 3.
6. **`locality_unverified` policy state** (peer): ranges `None` reaches verify → ASK → `blocked`,
   exit 2 — the `None` path is exercised, not just documented.
7. **`reject_all` policy state** (peer): clean doc (`ranges == []`) + a nonempty candidate → verify
   `blocked` (locality rejects every edit), exit 2.
8. **Empty candidate policy (adv A1 fix — keyed on `audit_status`, not authorization):**
   edits `== []` on an `audit_status=="clean"` doc → `ok` no-op (exit 0); edits `== []` on an
   `audit_status=="flagged"` doc → `blocked`/`candidate_empty` (exit 2) — EVEN when
   `authorization.state=="reject_all"` (doc-level-only-flagged). Missing model output is never a
   silent success on a flagged doc.
9. **Digest/path-mismatch guards** (peer + adv A6): file modified between audit and run →
   `failed`/`digest_mismatch`; same bytes at a DIFFERENT path → `failed`/`path_mismatch`; apply
   never invoked in either. Exit 3.
10. **Empty doc / no invariants** → empty-but-valid ledger, verify handles it (no `LedgerBuildError`).
11. **Semantic invocation failure (adv A2):** a `semantic_fn` whose sink reports
    `invocation_status != "ok"` (injected: simulate timeout/CLI-missing) → verify stage
    `failed`/`semantic_invocation_failed`, exit 4 — distinct from case 6's policy `blocked`.
    Plus `status_sink` unit tests in `tests/test_invoke_contract.py`: sink populated on failure,
    absent sink → behavior byte-identical to today.
12. **Exit-code table:** unit test over `_EXIT_CLASS` — every **exit-determining** code slug maps
    to exactly one exit class (`upstream_not_ok` excluded — it tags only `aborted` stages and never
    drives the exit); the CLI returns 0/2/3/4 per the table.

(Case-3 authoring note, round-2: the ACCEPT edit must actually change bytes — an identical
replacement makes `apply_selective` return `status="no_op"` (apply.py:212-213), not `"applied"`.)

Red-before-green: tests authored first, confirmed failing (no `slopslap_assemble` module), then the
module makes them pass. Full suite re-run after; delta reported vs the recorded baseline
(**369 passed, 1 skipped, exit 0** — the skip is the `SLOPSLAP_LIVE`-gated live-invocation test;
self-review F5 wording fix).

## 11. Review provenance

**Peer consult:** `docs/reviews/peer-rawgentic-peer-problem-27-2026-07-12.md` (GPT Soul via Codex).
Adopted: authorization-state encoding, `ok|blocked|failed|aborted` stage vocabulary + explicit
`aborted` downstream results, source-digest boundary re-check, CLI hygiene (no source bytes in JSON,
ledger `{canonical,sha256}`, exit codes 0/2/3/4), golden cases 6–9, library-API-not-CLI for metrics,
genre-resolved-once threading, no timestamps in envelopes (golden stability). Deferred: 3-file
package layout (single module until it outgrows), `started_at`/`duration_ms` fields, `retriable`
error flag (no retry consumer exists yet — YAGNI).

**Step-4 gate (design loop-back 1 of global 3, consumed 2026-07-13):** self-review (Opus
`rawgentic-reviewer`) + adversarial-on-design (Codex,
`docs/reviews/2026-07-12-27-live-orchestration-seam-md-2026-07-13.md`). Folded fixes: F1 dry-run
backup reality (§6, §10.3/10.4), A1 `audit_status` cleanliness (§4.1, §10.8), A2 typed semantic
invocation outcome via `status_sink` (§7, §6, §10.11), A3+F2 status ordering + exit-code table
(§4.3, §10.12), A4 vocabulary purge (§6), A5 candidate-stage edit validation (§4.3, §10.5), A6
path-identity binding (§4.1, §4.2, §10.9), F3 justified non-reuse of `eval_semantic_fn` (§5), F4
metrics consumer named + accepted double-run (§4.1), F5 baseline wording (§10).

**Step-11 adversarial diff review (Codex cross-model, `docs/reviews/rawgentic-27-branch-diff-2026-07-13.md`) — 1 Critical + 2 High, all confirmed at source:**
- **Critical (write=True mutates now, contradicting "dry-run until #29"):** CONFIRMED — the API forwarded `write=True` to `apply_selective`. FIXED: v0.1.8 is a hard no-mutation release boundary — `run_candidate`/`assemble` refuse `write=True` with an `apply_not_enabled` policy block (exit 2) and never forward it; `apply_selective` is only ever called `write=False`. #29 removes the fence + flips `commands/apply.md`. Test: `test_write_true_is_refused_no_mutation` (source byte-identical, no backup created).
- **High (offline stub indistinguishable from live):** CONFIRMED — FIXED: added `semantic_mode` (`live`|`offline_stub`|`injected`|`n/a`) to `RunResult` + the CLI JSON, so a consumer can tell a real Layer-3 pass from a stubbed one. `live_semantic_fn` tags itself. Tests: `test_semantic_mode_*`.
- **High (run_candidate trusts caller-constructed AuditResult):** assessed NOT a #27-threat-model vulnerability — a forged in-process `AuditResult` is strictly *easier* to bypass by calling `apply_selective`/`ledger.verify` directly (the caller already has full in-process access), so the seam adds no new attack surface; the untrusted-input surfaces (CLI, `assemble()`) self-derive the audit via `audit_document`. Documented as a trust boundary (`run_candidate`'s `AuditResult` is trusted-caller input); defense-in-depth (an authenticated/opaque audit handle) filed as follow-up for if/when the seam is exposed across a real boundary.

**Step-4 round 2 (no loop-back consumed — no surviving Critical/High):** self-review r2 PASS (all
round-1 Crit/High confirmed resolved at source); fixes applied in place: bad-bytes ownership rule
(`genre_error` owns decode, `diagnosis_error` = parser-unavailable-only, §4.3), sink completeness
invariant + stickiness (§7), `upstream_not_ok` exit-class exclusion (§10.12), case-3 bytes-must-change
authoring note (§10). Adversarial r2: R2-1 (verifier closure digest) **refuted with evidence** —
`validate_ledger` digest-checks first (ledger.py:119-120), a drifted original is REJECT/BLOCKED
fail-closed inside verify, so no unsafe-apply path exists; in-apply drift surfaces as REJECT (safe;
the seam's §4.2 pre-check catches earlier drift with the typed code). R2-2 stale (reviewed pre-fix
text; already fixed). R2-3 folded as sink stickiness (§7). R2-4 folded as the case-4 aborted-stage
assertion fix (§10.4).
