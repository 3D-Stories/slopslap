# FINDINGS — AI-slop before/after corpus

Gathered 2026-07-12. GATHER-ONLY: no slopslap code/SKILL/scanner/tests touched. All web text treated as data.

## Headline numbers
- 11 files (10 content + SOURCES). ~10 substantive sources with usable material; 9 academic datasets catalogued as bulk leads.
- ~75 clean before→after pairs captured verbatim (excluding datasets), plus ~20 Wikipedia AI-example passages (before-only, pattern-tagged with real article+date), plus 2 gold long-form pairs (deslop PLOS ONE cover letter 8/50→43/50; humanizer AI-coding essay).
- 9 paired corpora (file 10) hold thousands more machine/human-edited pairs for eval/training (Beemo, HPPT, SciHRA, MixSet, OpAI-Bench, PAN'25, EditLens, APT-Eval, PASTED).

Pair counts by source: humanizer 30 · deslop 16 · donatassimkus 11 · stop-slop 5 (+~30 pattern→fix) · llmbestpractices 5 · texttoolsai 3 · Wikipedia 2 diffs (+~20 examples) · genintelsys/tropes ~2 · TextKit 1.

## Tell coverage (against slopslap's target tells)

| slopslap tell / category | Coverage | Best sources | Notes |
|---|---|---|---|
| Synthetic cadence — "X, not Y" negative parallelism | ★★★★★ excellent | 01,02,03,04,05,07,08 + tropes.fyi | Universally named THE #1 AI tell. Variants: "not just X but Y," "not because X but Y," "X — not Y," cross-sentence reframe, "Not A. Not B. Just C." Supports the kukakuka ×16 finding. |
| Genericness / emptiness | ★★★★★ excellent | 01,02,03,04,05,06,07 | Deepest category: significance inflation, promotional tone, filler transitions, generic conclusions, signposting, one-point dilution. |
| Em-dash overuse | ★★★★★ excellent | 01,02,05,06,08 | Consensus: density/volume not presence ("one is a choice, five is a fingerprint"). |
| Rule of three | ★★★★ good | 01(rotary saw),02,03,05,08 | Adjective triples + phrase triples; fix = cut to two or expand one. |
| Copula avoidance ("serves as") | ★★★★ good | 01(2 real diffs),02,04,tropes.fyi("Serves As Dodge") | Only tell with two authentic Wikipedia before→after diffs. |
| Anthropomorphic flourish / false agency | ★★★ moderate (concentrated) | 03(structures),04(Ex4) | "the data tells us," "the market rewards," "results emerged," "uncertainty naturally increased." Rich but only in stop-slop + deslop. |
| Inflated metaphor | ★★★ moderate | 06("tapestry woven from threads"),04("landscape/paradigm shift"),01(McAllen temple) | Present but fewer clean single-tell pairs. |
| Unsupported claims / simulation | ★★★ moderate | 07(self-congratulatory-without-proof),01(notability),04 | Fix modeled as "add a real number/name" — see fabrication caution below. |
| Laundering (vague attribution) | ★★★ moderate (remedy mismatch) | 01(Haolai),02(#5),07 | Well-attested tell, but NO source models slopslap's remedy of converting to a question; all delete or replace with an invented specific. |
| Epistemic distortion (hedging / cutoff / invented labels) | ★★★ moderate | 02(#21,#24),04(#14 "calibration paradox"),tropes.fyi(invented concept labels) | Good on hedging + invented concept labels. |
| Semicolon overuse | ★ THIN — near-zero | (none) | slopslap lists it; sources fixate on em dash and ignore semicolons. Gap. |
| False ranges ("from X to Y") | ★ THIN | 02(#12) only | One example (Big Bang → dark matter). Gap. |
| Voice discontinuity (seam within a doc) | ✗ absent | (none) | Every source targets "make it sound human" globally or voice-MATCH a sample; none detects an internal voice SEAM. slopslap-distinctive; no prior-art pairs exist. Gap. |

## Register spread (good, with holes)
Encyclopedic (01,02) · scientific/technical (04,05) · marketing/copy (07,08) · general essay (06) · bureaucratic/cover-letter (04 gold). Thin/absent: legal, fiction/creative (explicitly out-of-scope in most guides), product-UI microcopy (only humanizer #13/#16).

## Notable cross-source patterns
1. Negative parallelism is the consensus #1 tell — independently, by every catalog.
2. Density over presence — every serious source states slopslap's keystone: a single em dash / tricolon / "delve" is not harm; the cluster is. Strong external validation of the abstention discipline.
3. "Change the skeleton, not just the words" (Louis Bouchard) — scrubbing vocabulary leaves structural slop; deeper harm is paragraph arc / one-point dilution / tidy-resolved conclusions.
4. Over-correction is itself a tell (Nathan Fennel) — banning all em dashes produces a different but still-artificial smell. Argues against blanket bans, for harm-gated edits.
5. The two aggressive OSS skills (stop-slop, deslop) share a 5-dim / 50-pt single score. slopslap splits harm vs. confidence and refuses a single number — position explicitly against these.

## Caveats / risks to carry into slopslap
- FABRICATION RISK in the "afters": most blog rewrites replace a vague claim with an invented specific ("in 2020," "r=0.267," "Atlassian, 2019," "4,200 teams"). A tool that must not fabricate CANNOT copy this move — it is slopslap's `simulation` category (flag missing support, don't invent). Do not reward added specifics in eval unless present in source. Single most important divergence.
- Direction mismatch in datasets: HPPT/SciHRA/APT-Eval/OpAI-Bench are human→AI (polish/revise). Their AI side = slop to repair; human seed = target/abstention reference — but not "AI draft a human de-slopped." Only Beemo (machine→expert-edited), MixSet "humanize," PAN'25 "machine→human-edited" run in slopslap's direction; PAN'25's on-target class is tiny (1,368 train).
- Licensing: only Wikipedia (CC BY-SA), humanizer/stop-slop/deslop (MIT) cleanly reusable. Blog sources 05–09 are fair-use-quote only. Datasets carry their own, often research-only, terms. See SOURCES.md.
- Coverage gaps to fill next: semicolon overuse, false ranges, voice-discontinuity (no prior art), laundering-as-question remedy, legal register, and a dedicated Reddit/HN/forum pass (not done — Firecrawl was 402 this session). TextKit / Louis Bouchard / Nathan Fennel have highlight-level capture only and merit a full re-fetch.

## Highest-value assets for slopslap eval
1. deslop PLOS ONE cover letter (file 04) — real published paper, scientific register, scored long-form pair; ideal end-to-end fixture that also exercises the "add real numbers not invented ones" boundary.
2. humanizer 29-pair table (file 02) — one clean pair per tell, encyclopedic register; ready-made per-category eval seeds.
3. Wikipedia copula-avoidance diffs (file 01) — the only two AUTHENTIC (real-edit) before→after pairs; ground-truth quality.
4. Beemo (file 10) — bulk on-mission machine→human-edited pairs for scaled eval.
