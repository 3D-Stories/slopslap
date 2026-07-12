# Peer Consult — corpus-foldin-question.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Use a provenance-first, lane-separated fold-in. Build a corpus manifest that records source, license, allowed use, direction, tell coverage, whether the after invents facts, and eligible artifact lanes. Then route material as follows: (1) committed fixtures: verbatim Wikipedia/MIT material only where redistribution and adaptation terms are satisfied, plus newly authored synthetic fixtures inspired by observed tells but sharing no protected expression; every fixture gets a slopslap-authored faithful golden edit-script, never an imported after by default; (2) judge-trial reference data: eligible AI→human pairs whose after preserves meaning, used as blinded comparison material or scoring anchors, with invented-specific afters represented only as labeled counterexamples for the preservation dimension; (3) threshold-calibration corpus: sufficiently licensed texts, including both positive and clean/control samples, labeled by tell and source family, used only to estimate scanner metric distributions and thresholds—not pass/fail correctness; (4) design inspiration: quote-only commercial blogs, research-only datasets outside permitted local evaluation, wrong-direction human→AI pairs, and remedy-mismatched examples. Treat corpus afters as evidence, not authority: classify each transformation as faithful, fabrication-contaminated, or indeterminate. For contaminated pairs, retain the before when legally usable and author a constrained slopslap edit; otherwise retain only metadata, tell labels, and a non-verbatim transformation description. Add authored fixtures for semicolon overuse, false ranges, and voice discontinuity. Split delivery between #23 for fixtures/goldens/harness changes and #25 for scanner calibration, preceded by a small shared provenance-manifest task; run live judge trials only after #23 establishes valid candidates and stable hard gates.

## Key decisions

- Artifact eligibility is determined per item, not per source collection; manifest fields should include source_id, provenance URL/citation, license, redistribution status, permitted_use, direction, tell labels, after_validity, claim additions, and selected lane.
- A corpus after is never automatically a golden. Promote it only after claim-atom, number/unit, modality, negation, protected-span, and structure checks pass, followed by human semantic review. Otherwise label it negative_after:fabrication or reference_only.
- Fabrication-contaminated afters are useful as explicit judge anchors: they should score poorly on meaning preservation even if stylistically cleaner. Keep them outside candidate goldens and aggregate quality rankings.
- For legally reusable befores, create slopslap-authored edit-scripts constrained to existing claims. Vague unsupported specifics should be removed, qualified, flagged, or converted according to the configured remedy; no replacement fact may appear without source text support.
- Commercial blog text is not committed. Store bibliographic provenance, access date, tell taxonomy, eligibility decision, and an original non-verbatim summary of the observed pattern. Author independent fixtures from abstract tell specifications rather than close paraphrases.
- Wikipedia/MIT verbatim content is committed only with the required attribution, license notice, source revision/commit identifier, modification notice, and share-alike handling where applicable. License compatibility should be resolved before fixture inclusion.
- Wrong-direction datasets are excluded from golden evaluation. They may support asymmetry research, clean/control sampling, or scanner calibration only when licensing permits and labels do not conflate AI polish with de-slopping.
- Scanner calibration is stratified by tell, source family, genre, document length, and positive/control status. Thresholds are learned on a calibration partition and reported on a held-out partition; fixture hard gates remain independent of scanner thresholds.
- Thin tells get original fixtures. Semicolon overuse should include semicolons that are stylistic and semicolons whose removal would alter structure. False-range fixtures should distinguish unsupported 'from X to Y' rhetoric from genuine bounded ranges.
- A voice-discontinuity fixture should contain two locally coherent sections separated by an abrupt internal seam—for example, a restrained technical incident report switching into promotional second-person hype—while preserving the same facts, terminology, headings, and speaker context. Editable ranges should cover the seam-adjacent prose, with facts and structural tokens protected.
- Voice continuity should not become a brittle deterministic style gate. Deterministic checks can verify authorized edit locality, protected facts, pronoun/person constraints where explicitly declared, terminology, markdown structure, and idempotence. Seam reduction belongs in a dedicated blinded judge dimension or a future calibrated classifier. The fixture passes hard gates independently of that soft assessment.
- Remedy mismatch must be tested directly with authored fixtures: include laundering cases whose authorized result converts an assertion to a question and paired harm/confidence annotations. Imported examples that merely delete text cannot validate this behavior.
- Split implementation: a shared provenance/schema prerequisite, then #23 for committed fixtures, slopslap-authored goldens, negative judge anchors, and any harness metadata; #25 for calibration ingestion, labels, partitioning, and threshold reports. This keeps deterministic correctness separate from empirical threshold tuning.

## Risks

- Licenses may permit research use but prohibit repository redistribution, transformed derivatives, or CI use; a dataset name alone is not sufficient permission.
- Wikipedia share-alike and attribution obligations may affect how fixture derivatives are distributed; legal compatibility cannot be inferred from technical usefulness.
- Synthetic fixtures can become caricatures that are easy to detect and unlike real prose. Counter this with genre diversity, subtle severities, clean near-neighbors, and held-out templates.
- Using contaminated afters in an overall judge score could teach the judge that fabricated specificity is an improvement. Their role and expected preservation failure must be explicit, with dimension-level assertions.
- Judge anchors may leak into prompts or candidate authoring, causing overfitting. Keep authoring, calibration, and held-out evaluation partitions distinct and record lineage.
- Wrong-arrow data can invert conclusions about desirable edits if mixed into AI→human evaluation without a direction field and enforced filters.
- A deterministic voice gate based on pronoun counts or embeddings would produce false confidence: voice is contextual, while many legitimate documents intentionally change register or speaker.
- Scanner thresholds can encode source, genre, or length artifacts rather than tells. Report per-stratum performance and abstain from global thresholds when distributions do not support them.
- Multiple related fixtures derived from one source can create pseudo-replication and inflate apparent coverage. Split and report by source family, not merely by passage.
- Adding many fixtures before live judge behavior is characterized may freeze poor rubrics. Start with a small representative tranche and expand after judge disagreement analysis.
- Provenance metadata can drift from copied fixture bytes. Generate and verify hashes, source revision identifiers, and license metadata in CI.
- Issue splitting can leave #23 blocked if the shared provenance contract is implicit. Make the manifest schema a small explicit prerequisite accepted by both issues.

## Sketch

Phase 0 — shared provenance task
corpus_manifest.jsonl
  source_id, item_id, source_family, citation, revision
  license, allowed_uses[], redistribution, attribution
  direction: ai_to_human | human_to_ai | before_only
  tells[], genre, control
  after_validity: faithful | fabricated | indeterminate | none
  artifact_lane: fixture | judge_reference | calibration | inspiration
  content_hashes, lineage, notes

Routing
  Wikipedia/MIT + permitted + suitable -> fixture and/or calibration
  AI→human + faithful + permitted -> judge reference; possible golden only after validation
  AI→human + fabricated -> negative preservation anchor; usable before gets new authored golden
  human→AI -> calibration/control or inspiration, never de-slopping golden
  quote-only/research-restricted -> metadata and design inspiration only
  thin tells -> wholly original fixtures

#23 tranche
  authored-semicolon/
  authored-false-range/
  authored-voice-seam/
  authored-laundering-question/
  reusable-corpus-before-* with slopslap-authored edit-scripts
  negative judge anchors tagged expected_preservation_failure
  hard gates unchanged except declarative fixture constraints such as allowed person/terminology

Voice fixture example
  Section A: restrained third-person incident narrative with exact times, counts, and uncertainty.
  Section B: abrupt marketing-style second-person claims about the same incident.
  Authorized edit: normalize Section B to the established register without changing facts or headings.
  Hard checks: bytes outside editable ranges, facts, modality, negation, terms, structure, idempotence.
  Soft check: blinded seam/coherence score against unchanged and humanizer baselines.

#25 tranche
  ingest only manifest-approved calibration items
  deduplicate and split by source family
  label tell presence/severity plus clean near-neighbors
  fit thresholds on calibration split
  report precision/recall and abstention per tell/genre/length
  keep thresholds measure-only until predefined validation criteria are met

Sequence
  provenance schema -> small #23 fixture tranche -> run hard gates -> pilot blinded judge trials -> refine rubric -> #25 calibration/held-out report -> expand fixtures and only then consider promoting scanner thresholds.

---
_Peer proposal (report-only). Synthesize at your discretion._
