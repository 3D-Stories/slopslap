# Increment 1 design brief — #eval-fixtures (the red test / acceptance contract)

Context: building the **slopslap** Claude Code plugin (repairs high-editorial-cost prose while
preserving meaning/requirements/uncertainty/voice; NOT an AI detector). Build order is
**fixtures-first**: pin the eval fixtures + the programmatic runner BEFORE the ledger/verify/apply
mechanics, so the mechanics are built to satisfy a fixed acceptance target. Full spec:
`docs/planning/2026-07-12-slopslap-reconciled-spec.md` (already WF5-clean, 0 Critical).

This brief is the design for the FIRST increment only. Independent peer proposal wanted.

## Goal of this increment

Deliver the acceptance contract: (a) 3 canonical fixtures + clean-document controls, machine-loadable;
(b) a programmatic eval runner that enforces the spec's **hard gates**; (c) an LLM-judge A/B scaffold
(data model + scoring logic, live judging deferred to the eval-run increment); (d) commit the real
`tests/fixtures/kukakuka-prd.md` PRD; (e) pytest with red-before-green.

## Hard gates (spec §Evaluation decision rule) — the runner must enforce these

Any failure ⇒ fixture FAIL, overriding all judge scores:
- protected spans byte-identical
- no changed number / unit / modality (modal-verb inventory by source region)
- no invented claim (no new numbers/dates/proper-nouns/endpoints/thresholds/citations)
- no edit outside authorized ranges
- idempotent 2nd run (no material diff)
- Markdown parses pre+post

Clean-document controls: pass criterion is **abstention** — original-unchanged must win/tie; ANY
material edit is a FAIL.

## Proposed design

**Fixture representation.** `tests/fixtures/eval/<name>/`:
- `original.md` — canonical original bytes (the fixture prose).
- `fixture.json` — `{editable_ranges:[{start_byte,end_byte}], protected_spans:[{start_byte,end_byte,sha256,kind}], expected_invariants:[{kind,text,preservation}], genre, seeded_defects:[...], control:bool}`.
All coordinates are **original-byte offsets** (matches the spec's canonical-coordinate decision).

The 3 canonical fixtures: distinctive human essay (2 seeded generic paragraphs among genuine voice);
normative spec (1 vague non-requirement among real normative statements); underspecified PRD (real
numeric constraints + missing decisions). Plus ≥2 clean controls (distinctive/clean prose, no defects).

**Runner** `scripts/eval/`:
- `hard_gates.py` — pure functions, one per gate, each `(original_bytes, revision_bytes, fixture) -> GateResult{name, passed, detail}`. Numeric-multiset check extracts `(value,unit,qualifier)` tuples; modal-inventory counts normative modals per source region; protected-span check re-hashes the span bytes in the revision via the edit map (increment-1: since editable_ranges are known, map protected spans by locating their exact bytes / verifying they are outside any changed region).
- `runner.py` — loads a fixture + a candidate revision (produced by a "baseline": slopslap / humanizer / original-unchanged), runs all gates, emits a JSON verdict `{fixture, baseline, hard_gates:{...}, passed:bool}`.
- `judge.py` (scaffold) — dimension list (meaning preservation, unsupported-claim introduction, actor/responsibility, unresolved-intent visibility, editorial-cost reduction, voice distance, genre fitness, edit locality, seeded-defect-fixed-without-normalizing); 0/1/2 scoring; per-dimension median over ≥3 trials; beat-criterion (all hard gates pass AND median dimension-sum ≥ baseline AND strictly wins ≥1 with none worse by >1); preservation-heavy tie-break. **No live LLM call yet** — a pluggable `judge_fn` interface; eval-run injects the real Claude judge.

**Chicken-and-egg calls I want the peer's view on:**
1. **Markdown-parse gate before the vendored CommonMark parser exists** (that parser lands in the scanner increment, #3). Options: (a) increment-1 uses a minimal structural sanity check (balanced fences, no broken links) and the real parse-equivalence gate wires in at #scanner; (b) block the gate as `skipped/capability_unavailable` until #scanner; (c) pull a tiny parse check forward. Which is safest without creating a silent-approximate fallback the spec forbids?
2. **"No invented claim" programmatically** is only partially mechanical (new numbers/dates/proper-nouns catchable; a new unsupported *sentence* is judge territory). Is the right MVP split: mechanical subset in hard_gates, semantic residue explicitly labeled a judge dimension — or should the runner attempt more?
3. **Reuse boundary with #ledger-verify.** hard_gates.py here vs the layer-1 deterministic verifier there — same code extended, or separate modules with the verifier importing these? I lean: build the checkers here, #ledger-verify imports+extends them (single source of truth). Agree?
4. **Idempotence** in a fixtures-only increment with no live rewriter yet: model it as "runner accepts an optional 2nd-run revision and asserts no-material-diff", tested with a synthetic stable/unstable pair. Reasonable?
5. Any fixture-authoring trap that would make these fixtures a weak acceptance contract (e.g., seeded defects too easy, protected spans not adversarial, controls not genuinely tempting to over-edit)?

## Folded decisions — post peer-consult (gpt-5.6-sol, `docs/reviews/peer-increment-1-eval-fixtures-design-2026-07-12.md`)

The peer proposal is adopted. Concrete decisions now binding for the build:

1. **Candidate envelope = explicit edit script (primary), not just revised bytes.**
   `{fixture, baseline, pass_index, edits:[{start_byte,end_byte,replacement_b64}], revision_sha256}`.
   The runner reconstructs `revision` from `original` + edits and rejects a `revision_sha256`
   mismatch. This makes edit-authorization, protected-span mapping, and provenance **deterministic**
   — no ambiguous substring search. A byte-only baseline (humanizer, original-unchanged) goes through
   an adapter that derives a minimal edit script via `difflib`, labeled `provenance:"inferred"`.
2. **Markdown parse gate uses a real CommonMark parser NOW** — `markdown-it-py` (present in env,
   v3.0.0; the scanner increment vendors it for distribution). Gate requires successful parse
   **pre AND post** (not AST-equivalence — legitimate prose edits change text nodes). If the parser
   is unimportable, the gate result is **`INCOMPLETE`/`capability_unavailable`**, never a pass, never a
   structural-sanity approximation (spec forbids silent-approximate fallback).
3. **Region-scoped invariant checks.** number/unit/modality preservation is compared **within the
   mapped source region**, not doc-global — a deleted value can't be masked by inserting the same
   token elsewhere. Fixtures declare `invariant_regions[]` with a comparison policy; region mapping
   uses half-open interval transforms through the edit map and **fails closed** when a required region
   can't be mapped (e.g. its bytes were deleted).
4. **Numeric extraction** keeps raw token + normalized value + sign + range/comparator + unit +
   qualifier. **Modal lexicon** is pinned, case-insensitive, phrase-aware (`must not`, `may not`,
   `is required to`, `should`, negation). Code/protected spans excluded from modal inventory.
5. **Invented-claim = mechanical hard gate** for enumerable atoms (new numbers/dates/proper-noun
   candidates/URLs-endpoints/thresholds-comparators/citation markers; fixture-declared
   `allowed_claim_atoms` exempted) **+ a separate named judge dimension** for semantic unsupported
   claims. The mechanical gate never implies semantic non-invention.
6. **Idempotence** returns **`not_evaluated`** when no 2nd-pass artifact is supplied (NOT "passed");
   canonical acceptance requires the 2nd pass once a rewriter baseline exists (eval-run increment).
   Tested here with synthetic stable/unstable pairs.
7. **Shared checker package `scripts/slopslap_verification/`** (pure deterministic gate functions) is
   imported by `scripts/eval/` (loading, orchestration, reporting, judge scaffold) AND later by the
   #ledger-verify layer-1 verifier — single source of truth for the hard gates.
8. **Result states:** `PASS` (all required gates pass) · `FAIL` (any gate fails) · `INCOMPLETE`
   (required artifact/capability absent, e.g. no 2nd pass or parser missing) · `FIXTURE_ERROR`
   (invalid manifest / parser setup). **Judge scores annotate only a deterministic `PASS`** and can
   never promote another state.
9. **Fixture-authoring utility** `scripts/eval/build_fixture.py` computes sha256/byte-offsets from
   human annotations so hashes/offsets aren't hand-maintained; `original.md` bytes are immutable
   inputs; a `validate` mode checks manifest bounds/ordering/overlap/disjointness/hashes.
10. **Fixtures avoid overfitting:** describe defect *classes* + preservation obligations, not canonical
    replacement text; include unseeded decoys, repeated protected strings, multibyte/CRLF offsets,
    numbers in several formats, normative adjacent to non-normative, and genuinely-tempting clean
    controls. Red-before-green test matrix: one mutation per gate + boundary insertion + repeated
    protected text + multibyte UTF-8 offset + CRLF + reordered duplicate numbers + modality negation +
    parser failure + absent 2nd pass + unstable 2nd pass + tempting clean-control edit.

## Post-review resolutions — WF5 adversarial review (`docs/reviews/increment-1-eval-fixtures-design-md-2026-07-12.md`, 0 Crit / 3 High / 4 Med, all confirmed)

**R1 (H1) — `control_abstention` gate.** A required deterministic gate: for `control:true`, ANY
material edit ⇒ FAIL, independent of editable ranges and judge scores. "material edit" = reconstructed
revision bytes ≠ original bytes under the material-equivalence normalization (R4).

**R2 (H2) — honest scope of the invented-claim gate + two-stage acceptance.** The deterministic gate is
renamed `no_new_claim_atoms` and advertised only as "no new *enumerable* claim atoms." Semantic
unsupported-claim detection is a **required judge dimension**; until a semantic evaluator result is
supplied, `acceptance_state = INCOMPLETE` (never PASS on the mechanical subset alone).

**R3 (H3) — markdown gate checks structural invariants, not "parses".** markdown-it-py coerces malformed
input, so parse-success is vacuous. The gate `markdown_structure` checks explicit invariants across
supported failure classes: fenced-code fence balance (equal open/close, no fence introduced/removed
inside a protected code span), inline code-span backtick balance, link-destination well-formedness (no
`[text](` left unterminated), and tokenizability. Backed by mutation tests (unclosed fence, broken
link). Named for what it checks.

**R4 (M4) — idempotence input contract.** A 2nd-pass artifact is a candidate envelope with
`pass_index=2` and `base_hash` == sha256 of the **reconstructed first-pass revision**; its `edits` are
in **first-pass-revision coordinates** (the 2nd run operates on the 1st output). Runner rejects a
`base_hash` mismatch (FIXTURE_ERROR for the run). Material-equivalence = exact bytes modulo a declared
trailing-newline policy (`byte_policy.trailing_newline: "preserve"|"normalize"`, default preserve).
Idempotent ⇒ 2nd-pass reconstruct == 1st-pass bytes under that policy; any material edit ⇒ FAIL; absent
2nd pass ⇒ `not_evaluated` (⇒ acceptance INCOMPLETE for canonical acceptance).

**R5 (M5) — final binding `fixture.json` schema** (validated by `build_fixture.py validate`):
```
{
  "schema_version": 1,
  "genre": "personal|spec|prd|marketing|technical|general",
  "control": false,
  "byte_policy": { "encoding": "utf-8", "trailing_newline": "preserve" },
  "editable_ranges":  [ { "start_byte": int, "end_byte": int } ],            // half-open, non-overlap, in-bounds
  "protected_spans":  [ { "start_byte": int, "end_byte": int, "sha256": hex, "kind": "code|blockquote|url|identifier|legal|quote|other" } ],
  "invariant_regions":[ { "id": str, "start_byte": int, "end_byte": int,
                          "checks": ["numbers"|"units"|"modality"|"negation"|"conditions"],
                          "policy": "preserve_all" } ],                       // region-scoped comparison
  "expected_invariants":[ { "kind": <closed enum>, "text": str, "preservation": <closed enum>,
                            "region": str|null } ],
  "allowed_claim_atoms":[ str ],                                             // atoms a revision MAY introduce (exempt from no_new_claim_atoms)
  "seeded_defects":   [ { "class": str, "region": str, "note": str } ],      // defect CLASS, not replacement text
  "control_reason":   str|null                                              // why a control is tempting to over-edit
}
```
`editable_ranges` and `protected_spans` MUST be disjoint. Controls have empty `editable_ranges`.
Coordinates are original-byte offsets; `build_fixture.py` computes `sha256`/offsets from annotations so
they are never hand-maintained; `original.md` bytes are immutable.

**R6 (M6) — dependency provenance + state semantics.** markdown-it-py is pinned in `tests/requirements.txt`
(`markdown-it-py==3.0.0`, `mdurl==0.1.2`) and imported via a version-gated shim; the #scanner increment
vendors it under `vendor/python/` for the packaged plugin. **`capability_unavailable`** (⇒ acceptance
INCOMPLETE) = parser unimportable. **`FIXTURE_ERROR`** = enumerated set: invalid manifest (schema/bounds/
overlap/hash), version-gate mismatch (an env parser whose version ≠ pinned), or a 2nd-pass `base_hash`
mismatch.

**R7 (M7) — explicit two-stage state model.** `deterministic_state ∈ {PASS, FAIL, INCOMPLETE, FIXTURE_ERROR}`
from the hard gates only. Then `acceptance_state`:
- deterministic FAIL / FIXTURE_ERROR ⇒ acceptance = same.
- deterministic INCOMPLETE ⇒ acceptance INCOMPLETE.
- deterministic PASS, **canonical fixture**: acceptance PASS iff judge present AND beat-criterion met vs
  the named baseline (median dimension-sum ≥ baseline, strictly wins ≥1, none worse by >1); a judge
  **loss** ⇒ acceptance FAIL; judge **absent/errored** ⇒ acceptance INCOMPLETE. (Judge never promotes a
  non-PASS deterministic state.)
- deterministic PASS, **control fixture**: acceptance PASS (abstention already proven deterministically;
  judge not required).
Each judge dimension carries explicit 0/1/2 anchors (0 = harmful, 1 = neutral/equal, 2 =
better-than-baseline) defined in `eval-cases.md`.

## Post-diff-review resolutions — WF5 on the built diff (`docs/reviews/increment-1-diff-2026-07-12.md`, 0 Crit / 7 High / 1 Med, all confirmed, all fixed)

The built runner was fail-open on several paths; every finding was a real gap and is fixed with a
regression test:
- **F1** — `run()` now consumes validated `judge.JudgeVerdict`s keyed by baseline and requires the
  beat-criterion against BOTH `humanizer` AND `original-unchanged` for a canonical PASS (no
  caller-supplied `beat` boolean, no single-baseline pass).
- **F2** — `markdown_structure` now also flags a dropped inline code-span (broken backtick delimiter).
- **F3** — `validate_manifest` requires every binding-schema field present + correctly typed (a
  truncated manifest is FIXTURE_ERROR, not an empty-collection vacuous pass) and enforces
  `byte_policy.encoding == utf-8`.
- **F4** — the `units` check uses a real value+unit quantity extractor (`200 ms` → `200 s` now
  FAILs); `units` added to the numeric invariant regions.
- **F5** — a judge `Trial` must carry the COMPLETE dimension set; `evaluate` returns errored on an
  incomplete trial; `beat_criterion` rejects a median map missing any dimension.
- **F6** — `revision_sha256`, second-pass `base_hash`, and `pass_index` are mandatory; absent/
  mismatched ⇒ FIXTURE_ERROR.
- **F7** — original + revision are strict-utf-8 decoded; corrupt bytes ⇒ FIXTURE_ERROR (no
  `errors="replace"` laundering).
- **F8** — malformed edit scripts (`EditError`/base64/`KeyError`/`TypeError`/`ValueError`) are caught
  and returned as FIXTURE_ERROR instead of crashing the runner.

## Out of scope for this increment
The rewriter/skill, the scanner, the full ledger, apply/backup. Those are later increments built to
pass THIS contract. Runner stays stdlib + `markdown-it-py` only (vendoring lands in #scanner).
