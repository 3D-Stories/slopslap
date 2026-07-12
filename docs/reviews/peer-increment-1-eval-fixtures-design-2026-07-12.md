# Peer Consult — increment-1-eval-fixtures-design.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Define Increment 1 as an executable, fail-closed acceptance contract with versioned fixture semantics. Store original bytes, canonical original-byte ranges, protected-span hashes, region-scoped invariants, seeded-defect annotations, and control status in each fixture directory. Validate fixture manifests before evaluating candidates. Represent candidate output as both revised bytes and an explicit edit script in original coordinates; use that edit script to prove edit authorization and map protected spans without ambiguous substring matching. Implement deterministic gates as reusable domain checkers shared with the later ledger verifier. Pull a real Markdown parser forward as the increment’s only non-stdlib runtime dependency—or vendor a small pinned parser now—because a skipped or approximate parse gate would not enforce the stated contract. Split invented-claim detection into a mandatory mechanical hard gate for enumerable claim-bearing tokens and an explicitly named semantic judge dimension; never imply that the mechanical subset proves full semantic non-invention. Support optional second-pass artifacts now, but mark idempotence as unevaluated rather than passed when absent; canonical fixture acceptance requires the second pass once a rewriter baseline exists. Make clean controls fail on any byte-level material edit after explicitly defined normalization, independently of judge scores.

## Key decisions

- Candidate submissions include `revision.md` plus an ordered, non-overlapping edit script containing original `start_byte`, `end_byte`, replacement bytes, and optional operation ID. The runner reconstructs the revision from the original and rejects mismatches; this makes authorization, span mapping, and provenance deterministic.
- Fixture manifests have a schema version and are validated for UTF-8 policy, bounds, ordering, overlap, protected-span hashes, editable/protected disjointness, invariant-region coverage, seeded-defect locations, and control-specific constraints before any candidate is scored.
- Markdown validity uses a real pinned CommonMark-compatible parser in Increment 1. Parser initialization failure is a fixture error and cannot become a pass, skip, or structural-sanity fallback.
- The Markdown gate requires successful parsing before and after revision. It does not require equivalent ASTs, because legitimate prose edits alter text nodes; later scanner requirements may add structural preservation checks separately.
- Number, unit, and modality preservation is region-scoped rather than document-global. Each invariant declares its original region and comparison policy, preventing a deleted value in one section from being masked by inserting the same token elsewhere.
- Numeric extraction preserves lexical and semantic attributes: raw token, normalized value, sign, range/comparator, unit, and qualifier. The default contract forbids additions, removals, and changes; fixture metadata may explicitly authorize narrowly defined transformations.
- Modal inventories use a pinned, case-insensitive lexicon with phrase-aware matching, including negation and multiword forms such as `must not`, `may not`, `is required to`, and `should`. Counts are compared within mapped source regions.
- The invented-claim hard gate detects new claim-bearing atoms: numbers, dates, proper-noun candidates, URLs/endpoints, thresholds/comparators, and citation markers. Allowed additions must be fixture-declared. Semantic unsupported claims remain a separate judge dimension and are reported as such.
- Protected spans are verified through edit-script coordinate transformation and byte comparison. Exact-byte searching is not used because repeated text makes location inference ambiguous.
- Edit locality is enforced directly from the submitted edit script: every consumed original interval must be contained within an editable range, and insertions are allowed only at explicitly authorized boundaries. Unchanged text outside edits is verified during reconstruction.
- Idempotence compares first-pass and second-pass bytes after one explicitly documented materiality normalization. Missing second-pass output produces `not_evaluated`, which prevents a canonical acceptance pass but permits scaffold tests to exercise other gates.
- Clean controls use original-unchanged as the oracle. Any material candidate edit is an unconditional failure; judge ties or improvements cannot override it.
- Deterministic checkers live in a neutral reusable package such as `slopslap_verification`, while `scripts/eval` contains fixture loading, orchestration, reporting, and judge scaffolding. The later ledger verifier imports the same checkers and adds ledger-specific policy.
- Judge results are subordinate evidence. Store each trial independently, compute per-dimension medians over at least three valid trials, retain raw scores and rationale, and apply the comparison rule only after all hard gates pass.
- Red-before-green tests include one mutation per gate, boundary insertions, repeated protected text, multibyte UTF-8 offsets, CRLF bytes, reordered duplicate numbers, modality negation, parser failure, absent second pass, unstable second pass, and tempting clean-control edits.
- Canonical fixtures contain multiple defect severities and near-miss prose: passages that sound generic but carry requirements, distinctive awkwardness that should remain, repeated protected strings, numbers expressed in several formats, normative statements adjacent to non-normative prose, and unresolved PRD decisions that must remain visibly unresolved.

## Risks

- A real Markdown parser conflicts with the dependency-light preference. Mitigate with one pinned, vendored or locked parser and a narrow adapter so replacement does not change gate semantics.
- Mechanical invented-claim detection has unavoidable false positives for sentence-initial capitalization and false negatives for ordinary-language claims. Report atom categories separately, support fixture-declared allowances, and reserve semantic coverage for judging.
- Original-byte coordinates are easy for authors to corrupt through editor newline conversion, Unicode normalization, or fixture edits. Treat `original.md` bytes as immutable inputs and provide a manifest regeneration/validation utility rather than hand-maintaining hashes and offsets.
- A candidate-only `revision.md` cannot prove authorized locality when identical output can arise from different edit histories. Requiring a reconstructable edit script closes this gap but raises integration cost for external baselines; an adapter may need to derive a diff and label its provenance as inferred.
- An overly permissive materiality normalization can hide idempotence drift or clean-control edits. Keep normalization minimal and versioned—prefer exact bytes, optionally allowing only a declared terminal-newline policy.
- Region mapping becomes ambiguous if an edit deletes or replaces an entire invariant-bearing region. Define half-open interval transformation rules and fail closed when a required region cannot be mapped.
- Fixtures can overfit implementation if seeded defects are homogeneous or explicitly expose desired rewrites. Describe defect classes and preservation obligations, not canonical replacement text, and include unseeded decoys.
- Judge medians can conceal bimodal or unstable behavior. Preserve trial-level results and report dispersion even if the acceptance rule remains median-based.
- The normative-modal gate may confuse quoted examples, code, and prose. Fixture regions should classify span kind, with code/protected material excluded mechanically and prose inventories evaluated explicitly.

## Sketch

Fixture layout:
`tests/fixtures/eval/<name>/original.md`
`tests/fixtures/eval/<name>/fixture.json`
`tests/fixtures/kukakuka-prd.md`

Manifest core:
`{schema_version, genre, control, byte_policy, editable_ranges, protected_spans, invariant_regions, allowed_claim_atoms, seeded_defects}`

Candidate envelope:
`{fixture, baseline, pass_index, edits:[{start_byte,end_byte,replacement_b64}], revision_sha256}`

Execution flow:
1. Load original bytes and validate the fixture manifest.
2. Validate and apply the candidate edit script; require reconstructed bytes to match the submitted revision hash.
3. Parse original and revision with the pinned Markdown parser.
4. Transform source regions through the edit map.
5. Run protected-byte, authorized-range, numeric/unit/modality, and new-claim-atom gates.
6. If second-pass output exists, validate it against first-pass bytes; otherwise return `not_evaluated` and prevent canonical acceptance.
7. For controls, fail immediately on any material edit.
8. Emit a versioned JSON report containing fixture-validation status, every gate result, evidence locations, overall deterministic status, and optional judge comparison.

Result states:
`PASS` only when every required gate passes; `FAIL` for any gate failure; `INCOMPLETE` when a required artifact or capability is absent; `FIXTURE_ERROR` for an invalid manifest or parser setup. Judge scores can annotate only a deterministic `PASS` and can never promote another state.

---
_Peer proposal (report-only). Synthesize at your discretion._
