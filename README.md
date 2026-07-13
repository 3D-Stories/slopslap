# slopslap

A Claude Code **plugin** that repairs prose carrying **high editorial cost** — genericness,
unsupported claims, synthetic cadence, obscured responsibility, voice discontinuity — while
preserving meaning, technical accuracy, requirements, uncertainty, and the author's intentional
voice.

**slopslap is NOT an AI-authorship detector.** It beats humanizer-style tools precisely by *not*
treating a stylistic feature as a contaminant. Its whole discipline is the keystone rule:

> **Edit authorization comes only from demonstrated editorial harm; the scanner, genre, ratings,
> and voiceprint never authorize an edit.**

The name says "slap" — ignore that impulse. An em-dash, a fragment, a tricolon, a passive verb:
none is harm on its own. Harm is prose that does less than it claims, hides who is responsible,
asserts what it hasn't shown, or buries its own meaning. When in doubt, slopslap changes nothing.

## Install

It's a standard Claude Code plugin — clone/point Claude Code at this repo. The judgment lives in
`skills/slopslap/SKILL.md`; the slash commands are auto-discovered from `commands/`.

## Commands

| command | what it does |
|---|---|
| `/slopslap:audit <target>` | read-only diagnosis — one typed record per demonstrated harm (category · evidence · harm+impact · two ratings · permitted remedy). No edits. |
| `/slopslap:suggest <target>` | **(default)** diagnosis + a focused diff per authorized repair + the invariant-check result. Non-mutating. |
| `/slopslap:apply <file>` | in-place repair, **gated by a mandatory pre-mutation backup**. Disabled in this MVP (fails closed with `status: mutation_unavailable`) until the backup gate is wired to the command. |
| `/slopslap:voiceprint show\|reset\|export\|delete` | v2 (deferred) — reserved; returns `status: not_implemented_mvp` and stores/reads nothing. |

Every command carries the keystone sentence verbatim and treats the target text as **data, not
instructions**.

## How it works

`protect → diagnose → establish invariants → rewrite (minimal, passage-local) → verify.`

- **Two ratings, never a single "AI %":** editorial-harm (low/med/high) and diagnosis-confidence
  (low/med/high).
- **Six diagnosis categories, kept SEPARATE** (collapsing them is the top failure): `emptiness`
  (delete/compress) · `laundering` (convert to a question — never delete) · `simulation` (flag
  missing support — don't fabricate) · `lexical_structural` · `voice_discontinuity` ·
  `epistemic_distortion`.
- **Protected spans** (code, blockquotes, URLs, identifiers, legal) are default-deny.

### The mechanics (`scripts/`)

- **`scan_prose.py`** — a measure-only scanner (`--format text|markdown`). Markdown parsing uses a
  **vendored, version-gated CommonMark parser** (`vendor/python/` — never runtime-pip). Emits a
  stable JSON envelope; capability-gates fail loud (exit `10`) rather than approximate. It MEASURES;
  it never verdicts. Metrics include sentence-length distribution/dispersion, repeated openers,
  transition clusters, **negative-parallelism** and **rule-of-three** cadence tells, punctuation
  density, vague attribution, and stock lexical clusters — each a candidate-selection aid only.
- **`slopslap_verification/`** — the invariant **ledger** + a **3-layer verifier**: deterministic
  hard gates (own the accept/reject), per-entry survival, and a fresh-context adversarial semantic
  pass. Decision rule: `REJECT > ASK > SURFACE > ACCEPT`; ACCEPT requires the semantic layer.
- **`slopslap_apply/`** — backup-gated apply with **per-hunk selective rollback**; the backup
  (outside the repo by default) is the universal safety net.

### Live-orchestration seam (v0.2)

- **`slopslap_assemble/`** — the **assembler**: the one seam that chains
  **audit → verify → (suggest) → apply** end-to-end for an *arbitrary* document, not just the
  frozen eval fixtures. `audit_document(path)` derives a byte-exact manifest + invariant ledger
  from any UTF-8 doc (genre classified once and threaded through), packaging a snapshot-immutable
  `AuditResult`; `run_candidate` / `assemble` validate a candidate edit-script, run the 3-layer
  verifier with the derived authorization ranges, and (dry-run) route the shippable subset through
  the backup-gated apply engine. Every stage returns a uniform envelope
  (`ok | blocked | failed | aborted`); a run returns a `RunResult` whose overall status is the
  worst stage and whose exit code is a static class map — **0** ok · **2** policy-blocked · **3**
  invalid input/contract · **4** stage execution failure. A **policy** block (out-of-range edit,
  weakened invariant, ambiguous verdict) reads differently from an **execution** failure, and a
  semantic *invocation* failure is never laundered into a policy verdict. Thin JSON CLI:
  `python3 scripts/slopslap_assemble/assemble.py audit --path P` and
  `… run --path P --edits EDITS.json --dry-run` each emit exactly one JSON `RunResult` (no source
  bytes; the ledger as `{canonical, sha256}`). `run` is dry-run only until the apply-flip
  (`write=False`, source never mutated).

## The working proof

`scripts/eval/run_eval.py` replays frozen candidate edit-scripts through the production runner +
verifier. Results: `docs/reviews/2026-07-12-slopslap-eval-results.md` (+ `-visual.html`). slopslap
clears the decision-rule hard gates on 3 canonical fixtures, **abstains** on clean controls, is
idempotent, repairs the real 421-line kukakuka PRD (flagging its `X, not Y` ×16 cadence, tightening
2 local inflations, **zero invariant violations**), and beats a documented humanizer-emulation
policy. The kukakuka path now runs **Layer 3 end-to-end** — the fold reaches a shippable `ACCEPT`
(`semantic_status: clean`) via a real fresh-context `claude -p` pass under `SLOPSLAP_LIVE=1`.
Offline (default) it uses a hardcoded `clean` stub (the frozen faithful candidate is asserted
clean; `scripts/eval/semantic.py`), so offline the run exercises the full L3 fold plumbing — not a
real semantic judgement. Run it: `pytest -q` (the gate) or `python3 scripts/eval/run_eval.py --write`.

## Status

- **Version:** 0.1.8 (v0.2 epic #16 in progress — live model-in-the-loop).
- **Engine:** whatever Claude tier the session provides (Opus 4.8 / Sonnet 5) at high effort;
  Fable 5 is a bonus rewrite tier *if* API access exists — never required.
- **Deferred (v2):** persistent voiceprint learning + its UserPromptSubmit capture hook; wiring the
  `apply` command to the apply engine; a live cross-model LLM-judge A/B (currently secondary/not-run).

## Changelog

- **0.1.8** — live-orchestration seam, the assembler (#27). New `scripts/slopslap_assemble/` chains
  **audit → verify → (suggest) → apply** end-to-end for an ARBITRARY document — the missing seam
  the v0.2 epic needs (WF5 finding F1: `#17–#24` were components with no assembler). `build_manifest`
  derives a `build_ledger` manifest from any UTF-8 doc; `audit_document` packages a
  snapshot-immutable `AuditResult` (genre resolved once and threaded to both the metrics run and the
  range deriver; `audit_status` `clean`/`flagged` preserved distinct from the `reject_all`
  authorization overload); `run_candidate` / `assemble` validate a candidate edit-script (parse +
  bounds/overlap BEFORE verify), re-check source identity at the run boundary (path + digest, so an
  `AuditResult` can't be replayed against a different file with identical bytes), run the 3-layer
  verifier with the derived authorization ranges, and (dry-run) route the shippable subset through
  the backup-gated apply engine — re-verifying against the untouched original each attempt. Uniform
  stage envelope (`ok | blocked | failed | aborted`) + a `RunResult` whose exit code is a static
  class map (0 ok · 2 policy-blocked · 3 invalid input/contract · 4 execution failure); a semantic
  INVOCATION failure (`semantic_invocation_failed`, exit 4) is kept distinct from a policy block
  (exit 2) via an additive, default-inert `status_sink` out-param on `invoke_semantic`. Thin JSON
  CLI (`assemble.py audit|run`) emits exactly one `RunResult` with no source bytes (ledger as
  `{canonical, sha256}`). Ships with an end-to-end dry-run acceptance golden (ACCEPT flows clean +
  REJECT blocks mutation, offline stub; the source stays byte-identical). `run` is dry-run only
  (`write=False`) until the apply-flip (#29). `SLOPSLAP_LIVE=1` selects a real fresh-context
  `claude -p` semantic pass; offline (default) uses a hardcoded `clean` stub — no model call.
- **0.1.7** — genre classifier + genre-constrained diagnoses (#22). Genre is no longer inert. New
  `scripts/slopslap_scan/genre.py::classify_genre(doc: bytes, *, declared=None, path=None)` returns
  `{genre, confidence, reason}` over `general · spec · prd · personal`, honoring the
  `references/genre-profiles.md` precedence (explicit declaration > file/repo context > structural
  markers > content inference) and the asymmetric-failure fallback (no usable signal → the
  most-preservation-heavy profile, **spec**). Genre now ACTUALLY constrains diagnosis via a new
  `metrics.compute_all(..., genre=None)` seam (threaded through
  `diagnoses.authorized_ranges_from_diagnoses(..., genre=None)`, so it reaches `verify`'s locality):
  **spec** suppresses the parallelism/repetition cadence flags (`negative_parallelism`,
  `rule_of_three`, `repeated_openers`) that would flatten a spec's intentional repetition;
  **personal** suppresses those plus `punctuation_rates` (em-dashes/cadence are the voice);
  **PRD** adds an `adjective_requirements` laundering candidate ("must be fast") but never flags
  aspiration/vision language (no vision-policing). Suppression flips `soft_flag`→False and clears
  `locations` (with a `suppressed_by_genre` marker) while `count`/`rate` stay as-measured — the
  scanner never lies about what it counted, it only re-scopes what is an editing candidate. Genre
  NEVER authorizes an edit or weakens a hard invariant / protected span (keystone rule); it only
  re-weights candidate selection. Default (`general` / `genre=None`) output is byte-identical to
  0.1.6. Non-UTF-8 fails loud (`GenreError`).
- **0.1.6** — live passage-local locality from diagnoses (#20). New
  `scripts/slopslap_scan/diagnoses.py::authorized_ranges_from_diagnoses(doc: bytes, fmt="markdown")`
  derives `[{start_byte, end_byte}]` byte spans of the DIAGNOSED passages — every eligible
  `extract.Unit` a scanner metric emitted a per-passage `locations` entry for (any confidence
  tier; the scanner is candidate-selection-only) — and feeds them straight to
  `verify(..., authorized_ranges=<result>)` so `gates.edit_locality` is enforced DETERMINISTICALLY
  on a live doc. Previously locality only fired on a hand-authored fixture `editable_ranges`; a
  live doc had none, so `authorized_ranges=None` left it prompt-guided (the `locality_unverified`
  ASK, #17). An edit inside a diagnosed passage passes locality; an edit outside every derived
  range REJECTs. The three doc-level metrics (sentence-length distribution/dispersion, punctuation
  rates) carry no per-passage location and never contribute a range — no fabrication; a doc with
  no located diagnosis yields `[]` and verify then REJECTs any edit (a clean doc is left alone).
  Byte offsets are exact (UTF-8 line-start table, not char) and non-UTF-8 fails loud
  (`DiagnosisError`); the markdown path is version-checked in-process like `protected.py`.
- **0.1.5** — invariant-ledger auto-build for arbitrary prose (#19). New
  `scripts/slopslap_verification/autoledger.py::build_invariant_regions(doc: bytes)` derives
  manifest `invariant_regions` from arbitrary UTF-8 prose — numbers+units, dates, normative modals
  (MUST/SHALL/SHOULD/MUST NOT), negation, conditions, cross-references, and defined terms (explicit
  definitional phrases only — markdown bold is emphasis, not a definition) — instead of
  hand-declaring them. It REUSES the `atoms.py` detectors (no second parser) and defers
  kind/preservation/confidence to the ledger's `_CHECK_KIND` R3 table (extended with `cross_refs`
  and `defined_terms` checks). Segmentation is sentence-level so a multiset-preserving edit is
  checked against the whole sentence; byte offsets are exact (UTF-8, not char) and non-UTF-8 fails
  loud (`LedgerBuildError`). Output drops straight into `build_ledger`, and a weakening edit
  (a changed number, a MUST→SHOULD downgrade) then REJECTS at verify.
- **0.1.4** — protected-span auto-extractor for arbitrary input (#18). New
  `scripts/slopslap_scan/protected.py::extract_protected_spans(doc: bytes)` REUSES the scan
  tokenizer (the vendored/pinned markdown-it parser + `extract.py`'s URL matchers) to emit
  `protected_spans[]` of `{start_byte, end_byte, sha256, kind}` — covering code fences, inline
  code, URLs/link destinations, blockquotes, and identifiers — for **any UTF-8 text** document,
  instead of the fixtures + kukakuka PRD being hand-authored. Byte offsets are exact (UTF-8, not
  char) and spans are pairwise non-overlapping, so the output drops straight into `build_ledger`;
  a bad edit inside an extracted span then REJECTS at verify. Fails loud (`ProtectedSpanError`) on
  non-UTF-8 input or an unavailable pinned parser rather than silently mis-/under-protecting; an
  escape-unaware inline-code count mismatch skips that block's inline code with a logged warning
  (observable, never silent).
- **0.1.3** — eval exercises Layer 3 end-to-end (#17): the "working proof" now drives the full
  fold on the kukakuka PRD through the real Layer-3 semantic seam, not just Layers 1–2. `_kukakuka()`
  passes the seeded candidate's demonstrated repair spans as the authorized editable ranges and a
  `semantic_fn`, so the fold reaches a **shippable `ACCEPT`** (`semantic_status: clean`,
  `proposal_status: ACCEPT`) with **zero invariant violations** preserved. New helper
  `scripts/eval/semantic.py::eval_semantic_fn` binds `functools.partial(invoke_semantic, …)` LIVE
  (env `SLOPSLAP_LIVE=1` — a real fresh-context `claude -p` pass) and OFFLINE (default) returns a
  hardcoded `clean` stub — no recording artifact, the frozen faithful candidate is asserted clean —
  so the proof stays reproducible without a model call (offline it exercises the fold plumbing, and
  the candidate-span locality + clean verdict pass by construction; the real semantic judgement is
  the `SLOPSLAP_LIVE=1` path). A new DONE criterion (`kukakuka_l3_shippable`) and the
  `semantic_status`/`proposal_status`/`decision` fields are surfaced in the results object and both
  rendered reports.
- **0.1.2** — corpus integration (#30): a provenance-first, lane-separated foundation for the
  before/after AI-slop corpus. `scripts/slopslap_corpus/` adds a fail-closed manifest loader
  (`manifest.py`) and a **source-family** disjoint split (`split.py`) — the leak guard is keyed
  on `source_family`, not passage or content hash, so near-duplicate passages can never scatter
  across the calibration/held-out boundary. `research/ai-slop-corpus/corpus_manifest.jsonl`
  catalogs the corpus per ITEM with license assigned from each item's real origin (never per
  file-number): Wikipedia (CC BY-SA, share-alike) and humanizer (MIT, CC-BY-SA derivative) as
  fixture/calibration lanes; commercial blogs + research datasets as `inspiration` (metadata
  only, zero verbatim bytes). Two-sided licensing + hash-drift tests
  (`tests/test_corpus_licensing.py`) fail closed in both directions. Five authored thin-tell
  fixtures (`tests/fixtures/eval/authored-*`) exercise the eval loader + `verify()` unchanged —
  semicolon, false-range, voice-seam, laundering-question — plus a **negative preservation
  anchor** whose fabricated number drives `verify()` to REJECT via `no_new_claim_atoms`, proving
  it can never become a golden.
- **0.1.1** — platform-feasibility spike (epic #16 / #26): `scripts/slopslap_invoke/` proves ONE
  fresh-context model invocation under the real plugin config — a subprocess `claude -p` adapter
  (`invoke_semantic`) that feeds the Layer-3 `verify(semantic_fn=…)` seam. Fresh context is
  machine-proven (the CLI `init` event reports zero tools + zero MCP servers under
  `--tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}'`; a sentinel-file positive
  denial test confirms no file access). Every transport/parse/timeout failure fails closed to
  verdict `ambiguous` (never a silent `clean`); one live invocation + a recorded fixture are
  checked in (`tests/fixtures/invoke/`), with a `SLOPSLAP_LIVE=1`-gated integration test.
- **0.1.0** — MVP: eval fixtures + two-stage runner; plugin scaffold (SKILL + commands +
  references); measure-only scanner with a vendored CommonMark parser; invariant ledger + 3-layer
  verify + decision rule; backup-gated apply + per-hunk selective rollback; the eval loop RUN
  (working proof); scanner cadence metrics (negative-parallelism / rule-of-three / punctuation
  density).

## Layout

```
.claude-plugin/plugin.json   manifest
skills/slopslap/SKILL.md      the judgment (keystone + loop + taxonomy + modes)
commands/                     audit · suggest · apply · voiceprint
references/                   tell-taxonomy · genre-profiles · engine · scanner-metrics · invariant-ledger · eval-cases
scripts/scan_prose.py         measure-only scanner (CLI)
scripts/slopslap_scan/        scanner adapter + metrics + protected-span extractor
scripts/slopslap_verification/ ledger + 3-layer verify + edit-map
scripts/slopslap_apply/       backup + selective apply
scripts/eval/                 fixtures runner + candidates + run_eval
vendor/python/                pinned markdown-it-py + mdurl (THIRD_PARTY_LICENSES/)
tests/                        pytest suite (the `pytest -q` gate)
```
