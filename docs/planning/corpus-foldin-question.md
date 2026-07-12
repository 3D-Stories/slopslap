# Folding the AI-slop corpus into slopslap's evals — thought-partner brief

We gathered a corpus of AI-slop before→after pairs (`research/ai-slop-corpus/`). We want to fold it into
slopslap's evaluation WITHOUT compromising slopslap's discipline. Be a design thought-partner: propose a
concrete folding plan + name the traps. Push back where the obvious move is wrong.

## What slopslap's eval is today
- **Fixtures** (`tests/fixtures/eval/<name>/`): `original.md` (immutable bytes) + `fixture.json`
  (byte-offset editable_ranges, protected_spans+sha256, invariant_regions, expected_invariants, control
  flag). 3 canonical (distinctive-essay / normative-spec / underspecified-prd) + 2 clean controls.
- **Runner:** deterministic HARD GATES (protected-span byte-identity, region-scoped number/unit/
  modality/negation preservation, no-new-claim-atoms, markdown structure, control abstention,
  idempotence). Any failure ⇒ fixture FAIL, overriding any judge score.
- **Candidates** are edit-scripts per baseline (slopslap / humanizer_emulation / original_unchanged),
  currently FROZEN + authored. There is an LLM-judge A/B scaffold (0/1/2 per dimension, median over ≥3
  trials, blinded vs humanizer AND vs original) — not yet run live.
- **Scanner** (measure-only) has 11 metrics with UN-calibrated soft-flag thresholds.

## The corpus (what we have)
~75 verbatim before→after pairs + ~20 Wikipedia AI-example passages (before-only) + 2 gold long-form
pairs + 9 bulk academic paired datasets catalogued (Beemo, HPPT, SciHRA, MixSet, OpAI-Bench, PAN'25,
EditLens, APT-Eval, PASTED). Tell coverage: negative-parallelism / emptiness / em-dash — excellent;
rule-of-three / copula-avoidance — good; anthropomorphism / inflated-metaphor / unsupported-claims /
laundering / epistemic — moderate; **semicolon overuse, false ranges, voice-discontinuity — thin/absent.**

## The four hard cautions (from the corpus findings)
1. **FABRICATION:** most blog "afters" fix a vague claim by INVENTING a specific ("r=0.267", "4,200
   teams"). slopslap must NOT do this — its `simulation` remedy is "flag missing support, don't invent."
   So a corpus "after" is often an INVALID target for slopslap.
2. **LICENSING:** cleanly reusable verbatim = Wikipedia (CC BY-SA) + the MIT OSS skills; the commercial
   blogs are fair-use-QUOTE-only (can't commit their text); datasets are often research-only.
3. **DIRECTION:** most datasets are human→AI (polishing) — the wrong arrow; only Beemo / MixSet-humanize
   / a small PAN'25 class run slopslap's direction (AI draft → human de-slopped).
4. **REMEDY MISMATCH:** no source models slopslap's `laundering→convert-to-a-question` remedy or its
   harm/confidence split; they all delete or single-score.

## Questions
1. Which corpus material should become which artifact: committed **fixtures**, **judge-trial reference
   data** (blinded A/B), **threshold-calibration corpus** (scanner soft-flags), or just design
   inspiration? Draw the mapping.
2. Given the FABRICATION caution: a before→after pair's "after" can't be slopslap's authorized target if
   it invented specifics. How do we use these pairs honestly — as "what NOT to do" negative examples? as
   the "before" only (slopslap authors its own faithful after)? as judge anchors for meaning-preservation?
3. Given LICENSING: for fair-use-quote-only blogs, do we commit NOTHING and instead author our own
   original fixtures INSPIRED by the tell (no verbatim), keeping only Wikipedia/MIT text verbatim? How to
   keep provenance honest in-repo.
4. The thin/absent tells (semicolon, false-ranges, VOICE-DISCONTINUITY — no prior art): author our own
   fixtures. What should a voice-discontinuity fixture look like (an internal seam), and how does the
   deterministic harness even check it?
5. Should the fold-in be ONE issue, or split across #23 (fixtures/goldens) and #25 (calibration corpus)?
   Sequence vs the rest of the epic?
