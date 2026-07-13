# QA discrepancy fixtures (`qa-*`)

Real-world cases where a live slopslap run's diagnosis diverged from a **document owner's
ground-truth label** (false positive, missed harm, or a valid-but-mislabeled finding). We capture
each as a fixture here, accumulate, then promote batches into the pinned `run_eval` inventory once
there are enough. Data-only; guarded by `tests/test_qa_fixtures.py` (globs `qa-*`, so a new capture
is drop-in). This is the established home — do not stand up a parallel one.

## Capture recipe (one discrepancy = one dir)

1. `tests/fixtures/eval/qa-<slug>/` with:
   - `original.md` — the **minimal self-contained excerpt** of the real prose that carries the case
     (not the whole document).
   - `fixture.json` — per `scripts/eval/loader.py` (`validate_manifest` must return `[]`).
2. Pick the shape by what the correct behavior is:
   - **False positive** (tool flagged clean prose) → `control: true`; empty `editable_ranges` and
     `seeded_defects`; `control_reason` states why abstention is correct **and the lesson**.
   - **True positive, flag-only** (e.g. `simulation` — no safe edit exists) → `control: false`;
     empty `editable_ranges`; `seeded_defects: [{class, region, note}]`;
     `expected_preservation_failure: true` (any inserted support is fabrication → verifier rejects).
   - **True positive with a safe repair** → `control: false`; `editable_ranges` bounding the harmed
     span; `seeded_defects`.
3. Always add `provenance` (source doc · who labeled it · date) and `genre` from the loader's
   `VALID_GENRES`.

## Promotion to canonical (deferred, batched)

`run_eval.py` drives `CANONICAL`/`CONTROLS` from an explicit inventory with **pinned first-pass
output digests** — promoting a `qa-*` fixture requires generating and pinning that live-model
digest, and the committed DONE gate must stay offline/hermetic. So promote in **batches**, not one
at a time. Suggested trigger: when `qa-*` covers each disposition shape (abstain / flag-only /
safe-repair) or reaches ~a dozen cases, whichever comes first — batching amortizes the live-digest
pinning. Until then these live here as validated data + calibration lessons.
