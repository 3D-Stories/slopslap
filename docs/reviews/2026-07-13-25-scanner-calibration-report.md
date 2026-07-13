# Scanner threshold calibration report — #25

- Date: 2026-07-13
- Issue: [#25](https://github.com/3D-Stories/slopslap/issues/25) · Epic [#16](https://github.com/3D-Stories/slopslap/issues/16) Tier 4 (FINAL child)
- Harness: `scripts/slopslap_corpus/calibrate.py` · Corpus: `research/ai-slop-corpus/corpus_manifest.jsonl` (#30)

## Verdict: MEASURE-ONLY (thresholds NOT promoted)

The scanner's 11 metrics stay `purpose="candidate_selection_only"` with their current
soft-flag thresholds unchanged. **No threshold was fit or promoted.** This is the honest
state the issue anticipated ("thresholds stay measure-only until validation criteria met") —
the criteria are not met, for a concrete reason below.

## Why — the corpus cannot calibrate yet

The #30 reference corpus enforces a leak-proof, family-level disjoint calibration/held-out
split (6 calibration items, 2 held-out). But **0 of the 8 tunable items carry verbatim text**
(`verbatim_path: null`): under their source licensing, most are inspiration/metadata-only —
they record the tell taxonomy, provenance, and split assignment, but not redistributable
prose. The scanner needs text to produce a metric value, so there are **0 usable calibration
points and 0 usable held-out points**.

The 5 corpus items that DO carry verbatim text are all `fixture`-lane authored fixtures
(`tests/fixtures/eval/authored-*`), used as eval acceptance data. They are deliberately **NOT**
used as a calibration source — doing so is exactly the train/test overlap the #30 disjoint
split exists to prevent (WF5 F-Medium, the reason #30 was carved out of the old #23).

Harness output on the real corpus:

```
verdict: measure_only · promoted: false · min_points_bar: 20
calibration: 6 items, 0 usable points, 0 thresholds fit
held_out:    2 items, 0 usable points, evaluation empty (precision/recall/abstention: n/a)
```

## What #25 delivers (the reliability half)

`calibrate.py` is the durable calibration harness, unit-tested (`tests/test_calibrate.py`)
against synthetic points so its mechanics are real and verified:

- **`fit_thresholds(points)`** — per-metric threshold on the CALIBRATION partition only, chosen
  to maximize F1 separating positives (tell present) from negatives (control / tell-absent). A
  metric lacking both a positive and a negative example abstains (`insufficient_labels`), never a
  bogus 0.
- **`evaluate_points(held_out, thresholds)`** — precision / recall / abstention **overall and per
  stratum** (tell / genre / length) on held-out, reading the thresholds AS GIVEN. It never writes
  them back — the never-tune-on-held-out guarantee is structural (asserted in
  `test_evaluate_reports_per_stratum_and_does_not_tune`). A point whose metric has no threshold is
  an **abstention**, not a decided verdict.
- **`calibrate_corpus(manifest, scan_fn, load_text)`** — orchestration: fit on calibration,
  evaluate on held-out, and return an honest coverage report. It **never auto-promotes** — the
  verdict is `measure_only` unless every fitted metric clears the `_MIN_POINTS_PER_METRIC` (20)
  bar AND a human promotes it (not automated). On this corpus: 0 usable points → `measure_only`.

## When this fires for real

When the corpus gains licensed verbatim text for its calibration/held-out items (or a new
licensed labeled corpus is added with `verbatim_path` set), re-run the harness. If metrics clear
the point bar, it reports per-stratum precision/recall for a human to review before any
promotion. Fixture hard gates remain independent of scanner thresholds either way.
