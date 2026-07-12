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

- **Version:** 0.1.3 (v0.2 epic #16 in progress — live model-in-the-loop).
- **Engine:** whatever Claude tier the session provides (Opus 4.8 / Sonnet 5) at high effort;
  Fable 5 is a bonus rewrite tier *if* API access exists — never required.
- **Deferred (v2):** persistent voiceprint learning + its UserPromptSubmit capture hook; wiring the
  `apply` command to the apply engine; a live cross-model LLM-judge A/B (currently secondary/not-run).

## Changelog

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
scripts/slopslap_scan/        scanner adapter + metrics
scripts/slopslap_verification/ ledger + 3-layer verify + edit-map
scripts/slopslap_apply/       backup + selective apply
scripts/eval/                 fixtures runner + candidates + run_eval
vendor/python/                pinned markdown-it-py + mdurl (THIRD_PARTY_LICENSES/)
tests/                        pytest suite (the `pytest -q` gate)
```
