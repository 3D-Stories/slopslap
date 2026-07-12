# slopslap eval cases — the acceptance contract (fixtures-first)

This is the **red test**: the fixtures and hard gates defined here are pinned BEFORE the
plugin mechanics (scanner, ledger, verify, apply), which are built to satisfy them. Nothing
downstream may relax a hard gate. Spec: `docs/planning/2026-07-12-slopslap-reconciled-spec.md`
(§Evals, §Evaluation decision rule). Increment design + cross-model review:
`docs/planning/increment-1-eval-fixtures-design.md` (peer-consult + WF5, all High/Med folded).

## How the harness works

A **candidate** is an explicit edit script in ORIGINAL byte coordinates — never just revised
bytes — so authorization, protected-span mapping, and provenance are deterministic (no
ambiguous substring matching):

```json
{ "fixture": "normative-spec", "baseline": "slopslap", "pass_index": 1,
  "edits": [ { "start_byte": 210, "end_byte": 288, "replacement_b64": "..." } ],
  "revision_sha256": "..." }
```

The runner (`scripts/eval/runner.py`) reconstructs the revision from `original + edits`,
verifies its sha256 (a mismatch is `FIXTURE_ERROR`), then runs the deterministic gates in
`scripts/slopslap_verification/` (reused by the later ledger-verify layer-1 verifier). A
byte-only baseline (`humanizer`, `original-unchanged`) is adapted through
`derive_edits` (difflib), labeled provenance `inferred`.

### Two-stage state model
- `deterministic_state ∈ {PASS, FAIL, INCOMPLETE, FIXTURE_ERROR}` — from the hard gates ONLY.
  No judge score can promote a non-PASS deterministic state.
- `acceptance_state` — FAIL/FIXTURE_ERROR pass through; INCOMPLETE passes through; on a
  deterministic PASS: a **control** fixture is PASS (abstention already proven), a
  **canonical** fixture is PASS iff the LLM-judge A/B beat-criterion is met (judge loss ⇒
  FAIL, judge absent/errored ⇒ INCOMPLETE).

### Hard gates (any failure ⇒ fixture FAIL; spec §Evaluation decision rule)
| gate | catches |
|---|---|
| `edit_locality` | an edit touching bytes outside an authorized editable range |
| `protected_spans_intact` | a mutated protected span (mapped through the edit map, re-hashed) |
| `preservation_region_scoped` | a changed number/unit/modality/negation **within its source region** (a value can't be masked by inserting the same token elsewhere) |
| `no_new_claim_atoms` | a newly invented enumerable atom — number, date, URL/endpoint, citation, threshold (advisory: proper-noun candidates; NOT a hard fail — capitalization is noisy, so semantic invention is a required *judge* dimension) |
| `markdown_structure` | Markdown damage — unbalanced fences, a changed code-block count, an unterminated link (NOT vacuous "does it parse": a CommonMark parser coerces malformed input) |
| `control_abstention` | ANY material edit to a clean-document control |
| `idempotence` | a 2nd run that materially changes the 1st output (`not_evaluated` when no 2nd pass is supplied; canonical acceptance requires it) |

`capability_unavailable` (markdown parser missing) ⇒ acceptance INCOMPLETE, never a pass and
never an approximate fallback.

## The 3 canonical fixtures (`tests/fixtures/eval/`)

Each is `original.md` (immutable bytes) + `fixture.json` (byte-offset manifest: editable
ranges, protected spans + sha256, invariant regions + checks, expected invariants, seeded
defect **classes** — not replacement text, to resist overfitting).

1. **distinctive-essay** (`personal`) — a first-person essay with genuine voice (fragments,
   an em-dash aside, a quoted saying) carrying **2 seeded semantic-emptiness paragraphs**
   ("In today's fast-paced world…", "Furthermore, it is worth mentioning…"). Only those two
   paragraphs are editable; the voice paragraphs and the blockquote are protected. Tests that
   slopslap **compresses the empty prose without flattening the surrounding voice.**
2. **normative-spec** (`spec`) — real MUST/MUST NOT/SHALL/SHOULD requirements with numeric
   limits (`5` retries, `200 ms`, `2000 ms`, `429`) plus **1 specification-laundered
   non-requirement** ("robust, intuitive, and user-friendly under all conditions"). Only the
   vague sentence is editable (→ convert to a question, do NOT delete); the retry-limits
   region (numbers + modality + negation) and the code block / `Retry-After` identifier are
   preserved. Tests **spec-laundering handling that never touches load-bearing normative vocab.**
3. **underspecified-prd** (`prd`) — real constraints (`10,000` users, `p95 < 300 ms`,
   `2,000,000`/day) with **unresolved decisions** (auth mechanism "determined later";
   retention "under discussion"). Only the aspiration sentence ("delight users … magical") is
   editable; the scale region and the open-questions must stay byte-honest and visibly
   unresolved. Tests that slopslap **flags simulation without inventing a decision.**

## Clean-document controls (abstention is the pass)

`original-unchanged` must win or tie; ANY material edit is a FAIL regardless of judge scores.
- **clean-personal** (`personal`, control) — dry fragmented humor; the flat repetition IS the
  joke. Tempting to smooth. Must abstain.
- **clean-spec** (`spec`, control) — parallel "A message MUST …" repetition is correctness
  infrastructure. Tempting to de-duplicate. Must abstain.

## LLM-judge A/B (scaffold now; live judging in #eval-run)

Blinded, vs `humanizer` AND vs `original-unchanged`. Each dimension scored **0/1/2** (0 =
harmful, 1 = neutral/equal to baseline, 2 = better-than-baseline), **median over ≥3 trials**
per (fixture × engine × baseline) to damp variance. A candidate **BEATS** a baseline iff all
hard gates pass AND its median dimension-sum ≥ the baseline's AND it strictly wins ≥1
dimension AND none worse by >1. A tie resolves to the more preservation-heavy output.

Dimensions (anchors in `scripts/eval/judge.py`): meaning preservation · unsupported-claim
introduction · actor/responsibility preservation · unresolved-intent visibility ·
editorial-cost reduction · voice distance from samples · genre fitness · edit
locality/justification · seeded-defect fixed without normalizing surrounding prose.

## Second-order failures to probe (spec §Second-order failures)

diagnosis-theater · taxonomy-leakage (emitting "specification-laundering" instead of plain
language) · scanner-anchoring (treating a soft flag as proof) · non-native normalization ·
dialect suppression · competence-laundering (cleaner prose making weak reasoning look
authoritative) · uncertainty deletion · responsibility reassignment (invented actor) ·
vision-policing (challenging every PRD aspiration) · question-explosion · iterative-sanding
(runs erode voice) · self-referential slop · corpus contamination · acceptance-ambiguity ·
genre-boundary-bleed · protected-span-laundering (hiding bad prose in quotes/code) ·
diff-fragmentation (many safe micro-edits jointly shift tone) · false-idempotence.

The controls guard iterative-sanding / over-editing; `idempotence` guards false-idempotence;
`preservation_region_scoped` + `protected_spans_intact` guard protected-span-laundering and
taxonomy-boundary bleed; the judge dimensions carry the rest (semantic, live in #eval-run).

## Running

```bash
# validate a fixture manifest (authoring)
python3 scripts/eval/build_fixture.py validate --dir tests/fixtures/eval/normative-spec
# the whole harness + fixtures
pytest -q
```
