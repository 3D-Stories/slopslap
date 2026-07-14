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

## Golden pairs (`pair-*`) — slop→clean before/after

`qa-*` captures single-doc discrepancies; `pair-*` captures the **destination**. Each is a
labeled before/after pair — the labeled data the #25 calibration harness was starved of (it
shipped measure-only against 0 labeled points). A pair carries the clean rewrite an aggressive,
verifier-safe de-slop pass should approach, so the eval can score *how close* a candidate gets,
not just whether it abstained.

Recipe (one pair = one dir), guarded by `tests/test_golden_pairs.py` (globs `pair-*`, drop-in):

1. `tests/fixtures/eval/pair-<slug>/` with:
   - `original.md` — the **slop** (before). Minimal, self-contained.
   - `clean.md` — the **target clean rewrite** (after). Valid UTF-8, must differ from `original.md`.
   - `fixture.json` — loader-valid (`validate_manifest` returns `[]`); `control: false` (a pair
     contains slop by construction); `seeded_defects: [{class, region, note}]` naming the slop;
     `pair: true` and `clean_file: "clean.md"` mark it as a pair. `provenance` + a `VALID_GENRES`
     `genre` as usual.
2. **P0 scope:** `editable_ranges` MAY be empty — the pair (original.md + clean.md) IS the label,
   and the guard checks only loader-validity + that `clean.md` is present, non-empty, UTF-8, and
   distinct. It does **not** assert any single edit reproduces `clean.md` byte-for-byte; wiring a
   pair into a verifier-checked golden repair (populated `editable_ranges` + a machine-produced
   candidate scored against `clean.md`) needs a live model and is a P2+ follow-up.
3. Keep the `clean.md` a **de-claim / tighten**, never a lateral swap to a new unsupported claim —
   the pair must itself be an example the Layer-1 `no_new_claim_atoms` gate would accept.

## Promotion to canonical (deferred, batched)

`run_eval.py` drives `CANONICAL`/`CONTROLS` from an explicit inventory with **pinned first-pass
output digests** — promoting a `qa-*` fixture requires generating and pinning that live-model
digest, and the committed DONE gate must stay offline/hermetic. So promote in **batches**, not one
at a time. Suggested trigger: when `qa-*` covers each disposition shape (abstain / flag-only /
safe-repair) or reaches ~a dozen cases, whichever comes first — batching amortizes the live-digest
pinning. Until then these live here as validated data + calibration lessons.
