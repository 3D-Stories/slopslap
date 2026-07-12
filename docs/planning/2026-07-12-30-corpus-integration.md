# #30 Corpus integration — provenance manifest + disjoint split + fixtures + negative anchors

Part of epic #16 (Tier 0). Prerequisite for #25 (calibration) and #28 (e2e golden).
Design synthesizes the owner-approved GPT-Soul consult
(`docs/reviews/peer-corpus-foldin-question-2026-07-12.md`) + the corpus licensing map
(`research/ai-slop-corpus/SOURCES.md`). Corpus already committed under `research/ai-slop-corpus/`.

## Problem

WF5 F5: putting the same gathered pairs into BOTH calibration data and eval/judge fixtures
creates train/test overlap — thresholds tuned on the very examples later used to claim
reliability. This issue lays the provenance-first, lane-separated, disjoint-split foundation so
#25 and #28 build on clean partitions.

## Approach (provenance-first, lane-separated — peer-approved)

**1. Shared provenance manifest** `research/ai-slop-corpus/corpus_manifest.jsonl` — one JSON
object per LINE, per ITEM (not per source). Fields (peer sketch):
`source_id, item_id, source_family, citation, revision, license, allowed_uses[],
redistribution, attribution, direction (ai_to_human|human_to_ai|before_only), tells[], genre,
control, after_validity (faithful|fabricated|indeterminate|none), artifact_lanes[]
(subset of fixture|judge_reference|calibration|inspiration), content_hashes{before,after},
lineage, notes`.

**Two orthogonal axes, disambiguated (fixes the calibration-lane/calibration-split collision):**
- `artifact_lanes[]` is a LIST (fixes the "fixture and/or calibration" one-value contradiction):
  an item may legitimately serve as both `fixture` and `calibration`. The lane is the
  PURPOSE (what the item may be used for).
- `split` (a SEPARATE field, `calibration|held_out`, present ONLY on items whose lanes include
  `calibration` or `judge_reference` — the empirically-tuned lanes) is the PARTITION. `fixture`
  and `inspiration` items carry `split: null` (they are deterministic-gate or metadata-only,
  never threshold-tuned, so the leak concern does not apply to them). This removes the naming
  collision: "calibration" the lane ≠ the `calibration` split value.
- **Split by SOURCE FAMILY, not passage (fixes the real leak — self-review H1, peer consult
  "split by source family, not merely by passage").** A content-hash key is NOT enough: the
  humanizer file alone is 29 pairs from ONE Wikipedia guide, file 01 is many passages from one
  article — near-duplicates that are not byte-identical (so different `before` hashes) would
  still scatter across the calibration/held-out boundary and leak. The partition is therefore
  keyed on `source_family`: EVERY item from one family lands in the SAME partition. The split
  field is carried per tunable item in the manifest; `assert_split_disjoint` proves **no
  `source_family` spans both partitions** (the real leak-proofness guard). `content_hashes` are
  still recorded (for the drift check below), but they are not the split key.

**2. Routing (per-item, from license + direction + after_validity):**
- **License is assigned per manifest ITEM from the item's real origin URL, NEVER inherited from
  the source-file number (self-review H3).** Two traps in SOURCES.md: file 04
  (`deslop-github-and-cover-letter`) is **split-license** — the GitHub repo `examples.md` items
  are MIT/committable, but the `blog.stephenturner.us` prose items are ⚠️ fair-use → `inspiration`
  only; file 02 (humanizer) is MIT but a **CC-BY-SA derivative**, so its share-alike +
  attribution obligations are recorded in each item's `attribution`/`lineage`.
- Wikipedia (CC BY-SA) / MIT repo items (files 01, 02, 03, 04-repo) verbatim + permitted → `fixture` and/or `calibration`.
- AI→human + faithful + permitted → `judge_reference` (golden ONLY after claim/number/modality/
  negation/protected/structure checks + human review; never auto-golden).
- AI→human + fabricated → `judge_reference` tagged `after_validity: fabricated` = **negative
  preservation anchor** (scores POORLY on meaning preservation; NEVER a golden, kept out of
  aggregate quality rankings).
- human→AI → `calibration`/control only (never a de-slopping golden).
- ⚠️ commercial blogs / research-only datasets (files 05–10) → `inspiration` only: metadata +
  tell taxonomy + an ORIGINAL non-verbatim description; **commit NO verbatim text**.

**3. A corpus "after" is NEVER auto-golden** — slopslap authors its own faithful edit-script
constrained to existing claims (the no-fabrication rule).

**4. Authored thin-tell fixtures** (no prior art / no license risk — fully original), matching
the existing `tests/fixtures/eval/<name>/{fixture.json,original.md}` structure so the eval
loader + `verify()` exercise them unchanged:
- `authored-semicolon` — semicolons that are stylistic (removable) AND semicolons whose removal
  would alter structure (must stay); tell `synthetic_cadence`.
- `authored-false-range` — unsupported "from X to Y" rhetoric distinguished from a genuine
  bounded range; tell `false_range`.
- `authored-voice-seam` — two locally-coherent sections + an abrupt internal register seam
  (restrained incident report → promotional 2nd-person hype), SAME facts/terms/headings.
  Editable = seam-adjacent prose; facts/structure protected. Deterministic hard gates check
  locality/facts/modality/terms/structure/idempotence ONLY; seam-reduction is a SOFT
  blinded-judge dimension (NOT a brittle deterministic style gate — peer decision).
- `authored-laundering-question` — an assertion that the authorized result converts to a
  question (remedy-mismatch tested directly, not by deletion).
- One **negative anchor** `authored-negative-fabricated` — a fabricated "after" (invents a
  specific number **whose normalized token does NOT already appear anywhere in `original.md`** —
  self-review H7, so the deterministic Layer-1 `no_new_claim_atoms` reject is guaranteed
  independent of ledger coverage) tagged `expected_preservation_failure: true`; a test asserts
  `verify()` REJECTS it, proving it can never be a golden.

**Where each authored fixture's candidate "after" lives (self-review H4).** The eval harness
feeds candidate edits from `scripts/eval/candidates.py`, and `fixture.json`/`original.md` carry
NO after. To keep this PR purely additive (no change to `candidates.py`/`run_eval.py`), each
authored fixture's candidate edit-script is constructed **inline in
`tests/test_authored_fixtures.py`** (as `editscript.Edit` objects, the same way
`test_invoke_verify_roundtrip.py` does), and the test drives `verify()` directly. The test
passes `authorized_ranges = fixture.editable_ranges` (else `verify()` downgrades locality to
ASK) and supplies a **second pass** so the idempotence gate actually fires (else NOT_EVALUATED).
"Terms preservation" is enforced by encoding each protected term as a byte-pinned
`protected_spans` entry (there is no standalone terms gate) — the voice-seam fixture's facts,
terminology, and headings are all protected spans; only seam-adjacent prose is editable.

**5. Fixed disjoint split** — the partition is CARRIED in the manifest (`split` field, present
ONLY on items eligible for calibration — lanes including `calibration` or `judge_reference`;
`fixture`/`inspiration` items carry `split: null`, self-review H6), not computed at read time,
so it is stable and auditable in the committed file. The loader exposes `calibration_items()` /
`held_out_items()`, and `assert_split_disjoint(manifest)` proves **no `source_family` appears in
both partitions**. #25 fits thresholds on `calibration` and reports on `held_out`; a test
enforces family-level non-intersection.

## File changes
- NEW `research/ai-slop-corpus/corpus_manifest.jsonl` (per-item provenance)
- NEW `scripts/slopslap_corpus/__init__.py`, `manifest.py` (schema + load/validate),
  `split.py` (deterministic disjoint split)
- NEW authored fixtures `tests/fixtures/eval/authored-{semicolon,false-range,voice-seam,
  laundering-question,negative-fabricated}/{fixture.json,original.md}`
- NEW `tests/test_corpus_manifest.py`, `tests/test_corpus_split.py`,
  `tests/test_authored_fixtures.py`
- README + Changelog; version bump ×2

## Configuration changes
None.

## Error handling and failure modes
- Manifest load fails closed: a malformed line, an unknown `artifact_lane`/`after_validity`
  enum, a missing required field, or a bad `direction` → `ManifestError` (never a silent
  accept of an unlabeled item into a lane).
- The split raises if any item lacks the fields needed to place it, rather than silently
  dropping it from both partitions.
- **Content-hash drift check (self-review H5):** for every item carrying a committed verbatim
  file (fixture/calibration lane), a test recomputes `sha256_hex(bytes)` and compares against
  the manifest's `content_hashes`, reusing the exact pattern at `scripts/eval/loader.py:134-135`.
  Fail-closed on mismatch OR a committed-text item lacking a hash — so provenance metadata
  (license, revision, attribution) can never silently detach from the bytes it describes.

## Representability (confirmed against real code — Step-4 H3)
- Authored fixtures use the EXACT loader schema (`scripts/eval/loader.py:63-75`: 11 required
  fields + `control_reason`), so `load_fixture` + `verify()` exercise them unchanged. The
  assertion→question laundering case is already a supported `seeded_defects` class
  (`specification_laundering`, present in the existing `normative-spec` fixture). Selective
  semicolon protection and seam-local editing are expressed via `editable_ranges` +
  `protected_spans` (the same mechanism the existing fixtures use).
- The negative-anchor hard-REJECT is REAL: a fabricated "after" that invents a number introduces
  a new claim atom, which the `no_new_claim_atoms` deterministic gate (`gates.py:144`) fails →
  `verify()` REJECT. The test asserts exactly this decision.

## Security implications
- Licensing is the real risk. The manifest's `license`/`redistribution`/`allowed_uses` are
  authoritative: only `fixture`/`calibration`-lane items carry verbatim text, and ONLY when
  `redistribution` permits (MIT / CC BY-SA with attribution). ⚠️ sources are `inspiration`
  lane — metadata + original description only, zero verbatim bytes committed.
- **Two-sided licensing test (Step-4 H5):** (a) NEGATIVE — no `inspiration`-lane item has a
  committed verbatim fixture file; AND (b) POSITIVE — every item whose lanes include `fixture`
  or `calibration` (i.e. carries committed verbatim text) has `redistribution` in
  `{permitted, share-alike}` and a non-empty `attribution`. An item that carries verbatim text
  without a redistribution-permitting license fails the test — the invariant is enforced in
  both directions, not just the inverse.
- Wikipedia CC BY-SA share-alike: attribution + license notice recorded in the manifest
  `attribution` field; `THIRD_PARTY_LICENSES/PROVENANCE.md` updated.

## Platform / external dependencies
platform_apis: none

## Multi-PR assessment
Single PR. Additive: new module + manifest + authored fixtures + tests; no existing module changed.

## Provenance
Design synthesizes the owner-approved GPT-Soul peer consult
(`peer-corpus-foldin-question-2026-07-12.md`) and the WF5 epic-stack review finding F5. No new
peer consult run (this design IS the consult's output applied).
