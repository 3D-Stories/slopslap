# Increment 6 design brief — #eval-run (the "working" proof)

Context: the mechanics are shipped (fixtures+runner, scaffold, scanner, ledger-verify, apply-backup).
This increment RUNS the eval loop to prove slopslap works (contract §7 DONE): slopslap clears the
decision-rule HARD GATES on all 3 canonical fixtures, ABSTAINS on the clean-document controls, repairs
the real `tests/fixtures/kukakuka-prd.md` with ZERO invariant violations, and BEATS/ties `humanizer` on
the programmatic hard gates. Spec: `docs/planning/2026-07-12-slopslap-reconciled-spec.md` (§Evals,
§Evaluation decision rule). Reuse the increment-1 runner + increment-4 verifier; author nothing new that
weakens a gate.

## Engine (contract §4)
The rewriter is **the session's Claude tier (Opus 4.8) at high effort** — I author slopslap's repairs by
applying `skills/slopslap/SKILL.md`'s judgment. **Fable 5 = bonus-if-API; no Fable API access confirmed
→ flag `OWNER-VERIFY (Fable API)` and proceed on Opus.**

## Deliverables
- `scripts/eval/candidates.py` — the three baselines' edit-scripts per fixture, offsets computed from the
  fixture's own bytes (like the fixture generator): **slopslap** (apply the judgment: compress the seeded
  generic paragraphs, convert the laundered requirement to a question, flag the PRD aspiration; ABSTAIN
  on controls), **humanizer** (its actual doc-wide de-stylizing, which touches invariants/voice/controls),
  **original-unchanged** (empty).
- `scripts/eval/run_eval.py` — runs each (fixture × baseline) through the increment-1 hard-gate runner +
  the ledger verifier; runs a 2nd pass for idempotence; runs the kukakuka-prd repair; aggregates a
  results dict.
- `docs/reviews/2026-07-12-slopslap-eval-results.md` + a self-contained `.html` artifact (workspace
  design-doc mandate).
- A pytest that RE-RUNS the eval and asserts the DONE outcomes (reproducible + gated).

## Questions for the peer
1. Is **authored-candidate edit-scripts run through the REAL deterministic gates** a valid "eval loop
   RUN" for a committed/reproducible proof — with the live-Opus rewrite demonstrated separately — or must
   the rewrite be re-generated live each run? (Determinism vs live-model.)
2. How to construct the **humanizer baseline FAIRLY** (representative of what humanizer actually does —
   strip stylistic tells doc-wide) so "beats humanizer" is defensible, not a strawman.
3. **kukakuka-prd zero-invariant-violations:** auto-build a ledger from the PRD (numbers/modals/protected
   code); which invariants; how to show "does not flatten distinctive prose" deterministically vs judge.
4. **LLM-judge A/B:** run it live (an independent judge — Codex gpt-5.6-sol or a Claude subagent) vs
   exercise the scaffold with recorded trials — what's the honest minimum given the programmatic gates are
   the PRIMARY proof and the judge is secondary (contract §7)?
5. Results artifact structure so the pass/fail is legible at a glance.

## Folded decisions — post peer-consult (gpt-5.6-sol, `docs/reviews/peer-increment-6-eval-run-design-2026-07-12.md`)

1. **DONE gate = deterministic replay** of FROZEN authored candidate edit-scripts through the production
   runner + verifier. Live regeneration would be irreproducible/costly/drift-sensitive, so it is a
   SEPARATE documented provenance demonstration, not a CI requirement. The artifact states this boundary
   plainly (frozen candidates prove the skill's demonstrated output + deterministic mechanics, NOT that an
   arbitrary future Opus session reproduces the quality).
2. **Every candidate is SHA-256-bound to its exact input bytes**; run_eval rejects a digest mismatch;
   offsets computed only from the bound input.
3. **ABSTAIN is an explicit `disposition`** (with reason, empty edits), DISTINCT from original-unchanged.
   A control passes only when slopslap explicitly abstains AND `output_sha256 == input_sha256`.
4. **humanizer = a declared, versioned transformation POLICY** applied consistently doc-wide WITHOUT
   consulting slopslap's expected failures; its natural collateral edits are preserved (invariants are not
   specially protected for the benchmark). It is labeled **representative/emulated** (the upstream tool's
   live model output isn't run deterministically) — comparison language stays at "the documented
   representative transformation," not a product-level claim.
5. **Per-gate scoring, same primary metrics** for every baseline: hard-gate result, invariant violations,
   control mutation, 2nd-pass delta, fixture decision-rule. **Beats/ties** = slopslap no worse on every
   programmatic hard gate AND strictly better on ≥1 fixture/gate.
6. **kukakuka ledger** = numeric literals (value+unit+qualifier), modals+negations in clause context,
   URLs/identifiers/paths/commands/code spans+fences/headings — the literals the shipped verifier
   recognizes; NOT all prose. Built + committed BEFORE the repair; fail closed on unclassified protected
   tokens.
7. **Non-flattening = deterministic PROXIES** (unchanged distinctive passages, changed-byte/line ratio,
   untouched-section ratio, heading/order preservation, no edits outside targets) — presented as proxies,
   NOT literary proof (that stays judge-supported).
8. **Idempotence:** the 2nd pass RE-RUNS candidate generation on the already-repaired text (not stale
   offsets); slopslap's generator keys on the harm CONTENT, so a repaired doc yields an empty edit list.
9. **LLM-judge = SECONDARY, recorded, non-gating:** trials through the shipped scaffold with prompts,
   anonymized order + order-reversal, judge identity/version, raw responses, aggregation committed. Kept
   OUTSIDE the primary DONE computation.
10. **run_eval emits one stable, sorted results object** (schema_version, input digests, provenance,
    pass1/pass2, ledger verify, PRD evidence, judge, decision-rule calcs); md + self-contained html
    rendered from THAT object; verdicts checked to match.
11. **pytest INVOKES the evaluator** (not trusting committed files): all 3 slopslap canonicals clear every
    hard gate; all controls abstain with no byte change; kukakuka invariant_violations == 0; 2nd-pass edits
    empty; the beats/ties rule vs humanizer holds.
12. **No tuning-to-pass:** fixtures/ledgers/thresholds/humanizer-policy are NOT adjusted after inspecting a
    failure without recording it as a protocol revision; no new exception converts a failure into a pass.

## Post-review resolutions — WF5 on the eval-run design (`docs/reviews/increment-6-eval-run-design-md-2026-07-12.md`, 0 Crit / 3 High / 4 Med, all confirmed)

- **R1 (H1) — no product-level humanizer claim.** The baseline is named **`humanizer_emulation`** — a
  declared, versioned de-stylizing POLICY, NOT the upstream product. All success language reads "beats/
  ties the documented humanizer-emulation policy." No product-level benchmark claim is made.
- **R2 (H2) — scoped DONE claim + recorded live-engine provenance.** This increment validates (a) the
  deterministic mechanics on real fixtures and (b) the SKILL's **demonstrated application** — the slopslap
  candidates are authored by the live session engine (Opus 4.8) applying `skills/slopslap/SKILL.md`, and
  are recorded with that provenance (engine, effort, session, input digest). It does NOT claim an
  arbitrary future session reproduces the quality; the artifact states this boundary.
- **R3 (H3) — deterministic pass-two.** `candidates.build_slopslap(input_bytes)` is a DETERMINISTIC
  function keyed on the harm CONTENT (not stale offsets). Pass 1 = `build_slopslap(original)`; its output
  is pinned by digest (a test asserts it). Pass 2 = `build_slopslap(pass1_output)` → **empty** (the harm
  content is gone), proving idempotence. Both passes bind + validate against their own input digest.
- **R4 (H4) — decision-rule inventory.** The pytest iterates an explicit inventory: fixtures
  {distinctive-essay, normative-spec, underspecified-prd} (canonical) + {clean-personal, clean-spec}
  (control); hard gates {edit_locality, protected_spans_intact, preservation_region_scoped,
  no_new_claim_atoms, markdown_structure, control_abstention, idempotence}; expected disposition per cell;
  result-object fields `deterministic_state`/`gates[]`/`acceptance_state`. Entry points: `eval.runner.run`
  + `slopslap_verification.ledger.verify`. No expected gate may be absent.
- **R5 (H5) — engine provenance is recorded, not selected.** A plugin can't select the host tier (engine
  advisory, per `references/engine.md`); the results object RECORDS the real authoring engine
  (`opus-4.8`, from the session) + notes it is unenforceable. Fable = `OWNER-VERIFY (Fable API)`.
- **R6 (H6) — judge status surfaced.** The judge payload carries `status ∈ {not_run, failed, completed}`
  + model identity + timestamp + error; the artifact renders a conspicuous NOT_RUN/FAILED banner. The
  judge is SECONDARY and NEVER gates the DONE computation.
- **R7 (H7) — discoverable gate.** The test is `tests/test_eval_run.py`, collected by the repo's declared
  gate `pytest tests/ -q`. A minimal `.github/workflows/test.yml` runs the pinned deps + `pytest -q` so
  the gate is visible and can't be silently skipped (contract §2's optional CI).
- **M (protocol honesty):** no fixture/ledger/threshold/humanizer-policy is tuned after inspecting a
  failure without recording it as a protocol revision in this design; no new exception converts a failure
  into a pass.

## Post-diff-review resolutions — WF5 on the built diff (`docs/reviews/increment-6-diff-2026-07-12.md`, 0 Crit / 4 High / 3 Med, all confirmed + fixed)

- **H1** — the kukakuka ledger was thin/fail-open. Now the required invariant spans (URL, "3 strikes",
  error codes) MUST resolve (assert, else fail), AND a **negative control** verifies that a hypothetical
  invariant-violating edit (`3 strikes`→`5`) is REJECTED — proving the ledger is live, not vacuous.
- **H2** — `hard_gates_pass` no longer treats INCOMPLETE as a pass: it requires
  `deterministic_state == PASS` AND every required gate present + `"pass"`.
- **H3** — `_beats` compares **gate-by-gate** over the common inventory (ranked pass>skip>fail);
  `worse_anywhere` fires on any single gate slopslap ranks below humanizer; strict wins counted per gate.
- **H4** — the kukakuka audit now comes from a **real `scan_prose.py` subprocess call** (units +
  cluster counts from its JSON), not hard-coded constants; a scanner error fails the eval.
- **H5** — the test asserts the FULL required-gate set per fixture type is present AND `"pass"` (not just
  one control gate).
- **H6** — `run_eval.py --write` writes both artifacts from the results object; a test asserts the
  committed `.md` equals the live render (a stale/obsolete-PASS report fails CI).
- **H7** — each fixture's loaded bytes are bound to a **committed expected input digest** (detects fixture
  drift) — the check is no longer tautological.

## Out of scope
New mechanics (all shipped). Persistent voiceprint (v2). Wiring the apply command to the engine (a
follow-up). This increment PROVES the existing mechanics + a demonstrated application on real fixtures.
