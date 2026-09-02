# Blind paired-preference eval of slopslap's own output — results (#102)

Generated 2026-09-02T09:11:13Z by `scripts/eval/preference.py report`. Human raters and the LLM judge are reported in SEPARATE sections and never combined into one number. This document reports preference counts and percentages only; it carries no single quality score of any kind.

## Method

- Each fixture is one real design-doc paragraph (`original.md`) and the output of `scripts/slopslap_assemble/assemble.py apply` on it (`applied.md`), produced from a committed edit-script authored by the slopslap engine — never hand-written.
- `build` shows the two as sides A and B in a seeded random order per pair; a rater picks A, B, or no preference. The pick is recorded with both side hashes (so the side order rides with the pick) and bound to the pair's `source_sha256`.
- The LLM judge sees the same blind A/B, three trials per pair with a fresh side order each time, and answers per dimension plus an overall preference; the nine-dimension scaffold in `scripts/eval/judge.py` scores each trial as applied-vs-original.
- Roles are recovered per fixture from the recorded hashes at report time; a pick that does not resolve to exactly one original and one applied side is refused, never counted.

## Fixture set — 3 pairs

| pair | source (repo · path · lines) | genre | engine |
|---|---|---|---|
| `pair-102-15-control-api-auth-passive` | 3D-Stories/design-doc-publish · docs/reviews/2026-08-23-github-doc-harness-spec-md-2026-08-23.md · 19-19 | spec | `claude-fable-5-1` |
| `pair-102-17-gc-sha-503-intensifier` | 3D-Stories/design-doc-publish · docs/reviews/2026-08-23-github-doc-harness-spec-md-2026-08-23.md · 78-78 | spec | `claude-fable-5-1` |
| `pair-102-21-publish-verification-passive` | 3D-Stories/design-doc-publish · docs/reviews/2026-08-23-github-doc-harness-spec-md-2026-08-23.md · 53-53 | spec | `claude-fable-5-1` |

### Sampling — 31 paragraphs sampled, 3 shipped as pairs

paragraphs of 40–200 words from the owner's two PUBLIC repos (3D-Stories/slopslap @1591b61, 3D-Stories/design-doc-publish @0aa220d3, both MIT) where the measure-only scanner reported at least one tell; every paragraph auto-classified as genre `spec`; private repos excluded so no private text is published.

| disposition | paragraphs | meaning |
|---|---|---|
| not_authorized | 13 | no strip-recommended tell under the auto-classified genre, so the autonomous path authorized no range |
| abstained | 11 | authorized, but the engine found no demonstrated harm |
| shipped | 3 | engine repair authorized, verifier ACCEPT, applied — a pair |
| verifier_blocked | 3 | engine proposed a repair; the byte-exact verifier rejected it and no safe alternative existed |
| excluded_circular | 1 | quotes slop examples itself; excluded as circular |

The full per-paragraph ledger (source, disposition, note) is `docs/reviews/102-eval/sampled-paragraphs.json`.

### Status against the issue

**AC4 asked for 5 to 10 pairs; this run ships 3.** The shortfall is a measured property of slopslap's default autonomous path on the owner's public prose, not a sampling accident: 31 paragraphs were sampled, the auto-classified `spec` genre authorized edits in 18, the engine proposed repairs in 9, and the byte-exact verifier accepted 3. No genre was declared to widen the authorized ranges (declaring `general` or `prd` on a design doc would misdeclare it to buy edits), and no private text was used. Two product limitations surfaced while trying: (1) a review-stage `edit` decision on any paragraph that carries an invariant is always rejected — the verifier reports every ledger entry inside the replaced span as `entry_dropped` even when the replacement preserves it byte for byte (probe: `tests` reproduce it with a number + negation paragraph); (2) `technical` is a valid genre in the recommendation table but not in `genre._DECL_ALIASES`, so `--declared-genre technical` silently falls through to auto-classification. Ways to widen the set, for the owner to choose: amend AC4 to the measured 3; authorize a declared genre for the 13 `not_authorized` planning paragraphs and re-run the recipe; publish paragraphs from a private repo; or fix the two limitations and re-run.

## Human raters

**Human mode: not yet run — 0 raters.** The rating page and the terminal loop are built (`preference.py human`), but no human has rated these pairs yet. No human preference percentage exists to report.

## LLM judge

Judge model: `gpt-5.6-sol` (pinned by `-m`, not echoed by the Codex CLI — `model_confirmed: false`). Rewrite engine(s): `claude-fable-5-1` — cross-model by construction.

9 trials over 3 pairs (3 per pair, 0 failed call(s), 0 pair(s) errored and excluded from percentages).

- Applied text preferred in **5** trial(s), original in **4**, no preference in **0** → applied preferred in **55.6%** of decided trials.
- Pairs where the applied text won the majority of trials: **2 of 3**.
- Pairs that BEAT the original on the nine-dimension scaffold criterion: **2 of 3**.

| pair | valid trials | applied | original | no pref | beat |
|---|---|---|---|---|---|
| `pair-102-15-control-api-auth-passive` | 3 | 2 | 1 | 0 | yes |
| `pair-102-17-gc-sha-503-intensifier` | 3 | 3 | 0 | 0 | yes |
| `pair-102-21-publish-verification-passive` | 3 | 0 | 3 | 0 | no |

## Limitations

- Sample size: 3 pairs. Any percentage here is a direction, not a measurement.
- Selection: paragraphs were sampled from the owner's public design docs where the measure-only scanner reported at least one tell, so the set skews toward flagged prose; abstentions are reported, not hidden.
- The judge model is pinned by the request and not confirmed from the CLI's output.
- A rater who inspects the fixture directories, `judge.json`, or hashes the side texts can de-blind themselves; the page and the blind file show no role in the clear.
- The rewrite engine and the judge are different models; a human rating is the primary evidence and the LLM judge is secondary.

## Reproduce

```bash
python3 scripts/eval/preference.py build --seed <seed> --out pairs.json
python3 scripts/eval/preference.py human --pairs pairs.json --static rate.html   # or --rater NAME
SLOPSLAP_LIVE=1 python3 scripts/eval/preference.py judge --pairs pairs.json --model gpt-5.6-sol --out judge.json
python3 scripts/eval/preference.py report --picks picks-<rater>.json --judge judge.json --out results.md --json results.json
```
