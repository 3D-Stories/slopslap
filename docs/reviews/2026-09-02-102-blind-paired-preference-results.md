# Blind paired-preference eval of slopslap's own output — results (#102)

Generated 2026-09-02T16:57:31Z by `scripts/eval/preference.py report`. Human raters and the LLM judge are reported in SEPARATE sections and never combined into one number. This document reports preference counts and percentages only; it carries no single quality score of any kind.

## Abstention funnel — read this first

101 paragraphs sampled, 8 shipped as pairs. Every row below counts paragraphs; any preference percentage in this document is measured over the last row only.

5 human-written documents the owner supplied from their own files (about 58,700 words: a leadership handbook, a servant-leadership reading, a talk on a data-transformation toolchain, a strategic-vision activity, a job profile). Every paragraph of 40 to 200 words was extracted (101, from 4 of the 5 — the job profile carried none of that length) and audited offline with `assemble.py audit`; every paragraph auto-classified as genre `spec`. Company, program, principle and person names were replaced with neutral words before any text entered this repository, and the owner approved each published paragraph individually. No public repo and no machine-authored text was used.

| stage | paragraphs | meaning |
|---|---|---|
| sampled | 101 | paragraphs of 40 to 200 words extracted from the owner's human-written documents (4 of the 5 supplied documents carried paragraphs of that length) |
| authorized | 15 | the free offline audit (`assemble.py audit`) authorized at least one range under the auto-classified genre |
| eligible | 11 | still authorized after names were replaced with neutral words, not quoting a third party, and approved by the owner one paragraph at a time |
| repaired | 8 | the engine proposed a repair, the byte-exact verifier accepted it, and a live `assemble.py apply` wrote it |
| paired | 8 | shipped as a blind A/B pair (`tests/fixtures/eval/pair-102-p*`) |

Per-paragraph dispositions:

| disposition | paragraphs | meaning |
|---|---|---|
| not_authorized | 86 | no strip-recommended tell under the auto-classified genre, so the autonomous path authorized no range |
| shipped | 8 | engine repair authorized, verifier ACCEPT, applied — a pair |
| excluded_third_party | 2 | authorized, but the paragraph quotes or paraphrases a third party; excluded |
| dropped_on_anonymization | 2 | authorized before anonymization; the audit found nothing once the names were replaced |
| abstained | 2 | authorized, but the engine found no demonstrated harm |
| verifier_withheld | 1 | engine proposed a repair and the verify stage accepted it, but the live Layer-3 semantic check withheld the hunk at apply time; nothing was written |

The full per-paragraph ledger (source, disposition, note) is `docs/reviews/102-eval/sampled-paragraphs.json`.

### Status against the issue

**AC4 asked for 5 to 10 pairs; this run ships 8** — the floor is met. The set is the owner's own human-written prose, anonymized and approved one paragraph at a time; the first run's 3 pairs were machine-authored review prose and were discarded (see `superseded_public_sample`). Funnel: 101 sampled → 15 authorized → 11 eligible → 8 repaired → 8 paired. The 86 paragraphs the audit did not authorize are the honest majority result: on this prose the autonomous path finds nothing to strip most of the time. The published judge run uses the genre-neutral rubric adopted at the Step 11 re-run (the rubric had anchored genre fitness to a technical design document); the first run under that rubric — 23 of 24 trials — is recorded in the design document beside the re-run.

## Method

- Each fixture is one source paragraph (`original.md`; its provenance is the pair's `fixture.json`) and the output of `scripts/slopslap_assemble/assemble.py apply` on it (`applied.md`). The committed edit-script replays to `applied.md` byte for byte, and the recorded apply exited 0 with a live semantic pass; that the slopslap ENGINE authored the edit-script is process-reported in each fixture's provenance and is not something the committed artifacts can prove.
- `build` shows the two as sides A and B in a seeded random order per pair; a rater picks A, B, or no preference. The pick is recorded with both side hashes (so the side order rides with the pick) and bound to the pair's `source_sha256`.
- The LLM judge sees the same blind A/B, three trials per pair with a fresh side order each time, and answers per dimension plus an overall preference; the nine-dimension scaffold in `scripts/eval/judge.py` scores each trial as applied-vs-original.
- Roles are recovered per fixture from the recorded hashes at report time; a pick that does not resolve to exactly one original and one applied side is refused, never counted.

## Fixture set — 8 pairs

| pair | source | genre | engine |
|---|---|---|---|
| `pair-102-p008-leadership-program-intensifier` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p040-unique-insights-intensifier` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p087-knowledge-gained-passive` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p093-thought-leadership-transition` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p104-detached-leadership-syntax` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p128-safe-environment-passive` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p133-recognition-filler` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |
| `pair-102-p139-planning-style-passive` | owner-supplied · an internal leadership handbook (June 2021), human-authored, supplied by the repository owner from their own files; company, program, principle and person names replaced with neutral words before publication · anonymized · owner-granted | spec | `claude-fable-5-1` |

## Human raters

**Human mode: not yet run — 0 raters.** The rating page and the terminal loop are built (`preference.py human`), but no human has rated these pairs yet. No human preference percentage exists to report.

## LLM judge

Judge model: `gpt-5.6-sol` (pinned by `-m`, not echoed by the Codex CLI — `model_confirmed: false`). Rewrite engine(s): `claude-fable-5-1` — cross-model by construction.

24 valid trials over 8 pairs (3 per pair, 0 failed call(s), 0 pair(s) errored). The percentages below come from the 24 trial(s) inside the 8 pair(s) that reached a present, non-errored verdict; an errored pair's trials are excluded.

- Applied text preferred in **24** trial(s), original in **0**, no preference in **0** → applied preferred in **100%** of decided trials.
- Pairs where the applied text won the majority of trials: **8 of 8**.
- Pairs that BEAT the original on the nine-dimension scaffold criterion: **6 of 8**.

| pair | valid trials | applied | original | no pref | beat |
|---|---|---|---|---|---|
| `pair-102-p008-leadership-program-intensifier` | 3 | 3 | 0 | 0 | yes |
| `pair-102-p040-unique-insights-intensifier` | 3 | 3 | 0 | 0 | yes |
| `pair-102-p087-knowledge-gained-passive` | 3 | 3 | 0 | 0 | yes |
| `pair-102-p093-thought-leadership-transition` | 3 | 3 | 0 | 0 | yes |
| `pair-102-p104-detached-leadership-syntax` | 3 | 3 | 0 | 0 | yes |
| `pair-102-p128-safe-environment-passive` | 3 | 3 | 0 | 0 | no |
| `pair-102-p133-recognition-filler` | 3 | 3 | 0 | 0 | yes |
| `pair-102-p139-planning-style-passive` | 3 | 3 | 0 | 0 | no |

## Limitations

- A rater's picks are evidence only against the blind file the operator issued: `report` refuses `--picks` without `--pairs`, and refuses a pick whose `run_id` or `token` that file never handed out. Side hashes alone recompute from the committed fixture bytes, so a self-consistent picks file proves only that its author can run sha256.
- Sample size: 8 pairs. Any percentage here is a direction, not a measurement.
- Selection: every paragraph in the funnel's `sampled` row entered the run (the selection line at the top says how it was drawn); the audit's tell policy decided authorization, so the preference results cover only the repaired subset. Abstentions are reported, not hidden.
- The judge model is pinned by the request and not confirmed from the CLI's output.
- The rater-facing page carries neither `source_sha256` nor `pair_id`, so hashing the two texts on screen no longer recovers a role. A rater with repository access can still de-blind themselves from the fixture directories, the private blind file, or `judge.json` — those are operator artifacts.
- The rewrite engine and the judge are different models; a human rating is the primary evidence and the LLM judge is secondary.

## Reproduce

```bash
python3 scripts/eval/preference.py build --seed <seed> --out pairs.json
python3 scripts/eval/preference.py human --pairs pairs.json --static rate.html   # or --rater NAME
SLOPSLAP_LIVE=1 python3 scripts/eval/preference.py judge --pairs pairs.json --model gpt-5.6-sol --out judge.json
python3 scripts/eval/preference.py report --pairs pairs.json --picks picks-<rater>.json \
    --judge judge.json --out results.md --json results.json   # --pairs is REQUIRED with --picks
```
