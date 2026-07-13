# Design — #23 suggest → deterministic verifier wiring

- Date: 2026-07-13
- Issue: [#23](https://github.com/3D-Stories/slopslap/issues/23) · Epic [#16](https://github.com/3D-Stories/slopslap/issues/16) Tier 3
- Complexity: standard_feature (Full WF2 per owner queue; opt-in peer/adversarial-on-design skipped as disproportionate — D-23a)
- Depends on: #27 (the seam, merged v0.1.8). Blocks: #28 (live golden).

## 1. Goal

WF5 F2, deterministic half. slopslap's suggest mode currently narrates its invariant-check as a
**model claim** — `skills/slopslap/SKILL.md:98-101`: *"the invariant check is **model-reported**;
the deterministic byte-exact verifier … is wired into the flow in a later increment."* That later
increment is **#27** (the `slopslap_assemble` seam, merged). #23 makes the **deterministic verifier
the authority** for suggest's invariant-check — the model no longer self-certifies "numbers, units,
modality, negation, conditions, protected spans — all intact"; it runs the seam and reports the
verifier's real verdict. Deterministic tests lock it: verifier input construction, verdict handling,
and rejection (a proposed diff that violates an invariant is BLOCKED). The **live** semantic golden
is #28 — #23 is Layer-1/Layer-2 (deterministic) only, no model in the check.

## 2. Scope

| In scope for #23 | Out |
|---|---|
| Retire the "model-reported / later increment" claim across the doc surfaces (SKILL.md, suggest.md, invariant-ledger.md, engine.md if stale) — the invariant-check is now the deterministic seam verifier | — |
| `commands/suggest.md`: the invariant-check RESULT the model presents MUST be the seam's `verify` verdict (run `assemble.py run --dry-run`), not model narration | — |
| Deterministic tests: verifier input construction from a suggest candidate, verdict handling, rejection-blocks-violation — all with NO live model (semantic stub / Layers 1+2) | live semantic golden → #28 |
| Doc-drift guard test: SKILL.md suggest mode no longer says "model-reported" | — |
| `plugin.json` `description` "model-reported" clause | #25 (owner-scoped, run-contract §3) |

**No new production logic.** The suggest→verifier *wiring* is the #27 seam (`scripts/slopslap_assemble/`).
#23 makes the suggest *contract* reflect and depend on it, and locks the deterministic behavior with
tests. This is a correctness-contract + docs-authority change, not a new module.

## 3. Approach

One obvious approach (no design fork): the seam already exposes `assemble.py run` (deterministic
verify of a candidate edit-script, Layers 1+2 with an offline/clean semantic stub). #23:
1. Edit the doc surfaces so the invariant-check is described as — and in the command flow, produced
   by — the deterministic verifier via the seam. Remove every "model-reported"/"arriving in a later
   increment"/"wired later" clause that #27 made stale.
2. Add `tests/test_suggest_verifier_wiring.py` — deterministic tests over the suggest→verify contract
   (using `slopslap_assemble` / `slopslap_verification` directly). **Use an offline CLEAN stub, NOT
   `semantic_fn=None`** (confirmed at ledger.py:365-366: `semantic_fn is None` → `decision="SURFACE"`,
   which is NOT shippable — a preserving repair would wrongly BLOCK). The clean stub neutralizes
   Layer-3 to always-clean so Layers 1+2 are the sole gate; a Layer-1/2 violation still REJECTs
   regardless of the stub (ledger.py:286/303/327). BLOCK cases cover the classes #27's seam tests
   miss: modality / negation / protected-span.
3. A doc-drift guard anchored to the SKILL.md suggest-mode sentence (red before the edit, green after).

## 4. File changes (self-review folds M1–M4/L1 applied)

- **EDIT** `skills/slopslap/SKILL.md` — TWO stale surfaces: (a) ~98-101 suggest mode "model-reported /
  later increment"; (b) ~141-142 "byte-exact verifier (arrive with the scanner / ledger increments)"
  (M3). Both: the verifier is the deterministic seam (Layers 1+2), wired as of #27. **Edit the
  VERIFIER clause only — leave the measure-only-scanner status accurate** (141-142 bundles both).
- **EDIT** `commands/suggest.md` — the mandated invariant-check result is the seam's `verify` verdict;
  restructure so the seam run IS the check (not an appendix). **Inline-text entry path (M2):** the
  seam CLI needs `run --path FILE`, but `$ARGUMENTS` is often pasted prose — the rewrite MUST state
  the precondition: materialize inline text to a temp file at its exact UTF-8 bytes, then run the
  seam against it (byte offsets are computed against those bytes). Keystone + untrusted-data framing unchanged.
- **EDIT** `references/engine.md` (~25) — "the verifier … arriving with the ledger increment" is stale;
  reflect wired-as-of-#27. (L1: `references/invariant-ledger.md:3-7` is NOT stale — grep confirms no
  "arriving/not-yet/wired-later" language there; do NOT edit it.)
- **NEW** `tests/test_suggest_verifier_wiring.py` — net-new deterministic tests ONLY (M1 dedupe):
  #27's `test_assemble_seam.py` already covers ACCEPT-clean (`test_e2e_dry_run_accept_golden`) and
  NUMBER-weakening BLOCK (`test_e2e_dry_run_reject_invariant_weakening`). #23 adds the invariant
  classes the seam tests DON'T cover at seam level — **modality / negation / protected-span** BLOCK —
  plus the SKILL.md doc-drift guard, plus one test driving the **CLI** (`assemble.py run` on a written
  file, not only the library on bytes) so the real command entry path is exercised (M2). Reuse
  `eval/candidates._span`/`to_envelope` + the seam's `CLEAN_STUB` — do not reinvent edit-script builders.
- **EDIT** `README.md` (+ Changelog `## 0.1.9`), `.claude-plugin/plugin.json` (0.1.8→0.1.9),
  `tests/test_scaffold.py` pinned assert, dashboard `2026-07-12-16-v02-epic-dashboard.{md,html}` #23 row.
  (Version surface ×1 — this repo has no codex-plugin manifest, unlike rawgentic's ×3.)

**Known temporary contradiction (M4, named not hidden):** `.claude-plugin/plugin.json:4` description
says the suggest invariant-check is "model-reported … until the deterministic … verifier land[s]".
After #23 (v0.1.9) that clause is FALSE — the verifier is now the authority. The run-contract (§3)
owner-scopes the description edit to #25 (the 0.2.0 child), so v0.1.9 ships a manifest description that
contradicts the skill for a few patch versions. This is an owner-accepted, tracked staleness (the
owner anticipated it explicitly), recorded here rather than silently deferred.

## 5. Platform / external dependencies

platform_apis: none

The suggest deterministic verify uses NO platform/external API — it is Layers 1+2 of `ledger.verify`
(pure Python: gates + per-entry re-extraction) with the semantic layer stubbed off. The live semantic
model call is #28's surface, not #23's.

## 6. Error handling & failure modes

- Deterministic verify is total (the seam's `run_candidate` catches every stage exception → typed
  `failed` envelope; #27). #23 adds no new failure surface.
- Doc-drift guard: anchor to ONE canonical SKILL.md sentence (per workspace rule on drift guards —
  no whole-corpus regex that false-positives on stray "model-reported" mentions elsewhere).

## 7. Testing / acceptance

Suite: `pytest tests/ -q` (D7 local gate). Baseline 415 passed / 1 skipped, exit 0 on main @ b9de742.
`tests/test_suggest_verifier_wiring.py` (net-new only — #27's `test_assemble_seam.py` already covers
ACCEPT-clean + number-weakening BLOCK; do not duplicate, M1):
1. **Verifier input construction** — a suggest candidate diff built via `eval/candidates._span`/
   `to_envelope` serializes to the `{start_byte,end_byte,replacement_b64}` edit-script the seam
   consumes; round-trips through `parse_edits` to the same `Edit`s.
2. **BLOCK on modality / negation / protected-span violation** (the classes seam tests miss) — each
   repair → `verify` REJECT / stage `blocked` (`verify_not_shippable`) under the CLEAN stub, proving
   the deterministic layers (not a model) block it. This is the "rejection behavior" AC.
3. **CLI entry path (M2)** — write a doc to a real file, build an invariant-preserving edit-script,
   run `assemble.py run --path FILE --edits E.json --dry-run` → exit 0; a violating script → exit 2.
   Exercises the real command entry path, not just the library on bytes.
4. **Not model-reported (doc-drift guard, red→green)** — SKILL.md suggest mode does NOT contain
   "model-reported" (anchored to the ONE canonical suggest-mode sentence, not a corpus-wide regex).

Red-before-green: the doc-drift guard is red until SKILL.md is edited; the behavioral tests assert the
deterministic verifier is the authority (a candidate violating an invariant MUST be blocked with no
model in the loop).

## 8. Security

No new trust surface. Suggest stays non-mutating (write=False); the seam's dry-run boundary (#27)
holds. Untrusted target content remains data, never instructions (keystone unchanged).

## 9. Review provenance

- **Step 4 self-review** (Opus): PASS, thesis (no new production logic) confirmed at source. 4 Med + 1 Low folded into §4/§7 (M1 dedupe vs #27 tests, M2 inline-text→temp-file entry path, M3 SKILL.md:141-142 also stale, M4 plugin.json v0.1.9 contradiction named, L1 bad citation dropped). Peer consult + adversarial-on-design skipped per D-23a (proportionate to a docs+tests change).
- **Step 11 code review** (Opus full-diff): PASS. Med fixed — README Status "Version:" bumped 0.1.8→0.1.9. Low — dashboard #23 row (updated in the PR). Out-of-scope catches folded: rendered this doc's `.html` companion (workspace mandate).
- **Step 11 adversarial diff** (Codex, `docs/reviews/rawgentic-23-branch-diff-2026-07-13.md`): 2 High + 1 Med + 1 Low, all dispositioned:
  - High (input-construction test shallow): FIXED — the test now builds a suggest candidate via `eval/candidates._span`/`to_envelope` (real diff→edit-script path), asserts it targets the harm bytes, round-trips, and applies to the intended repair.
  - High (edit-script has no per-range preimage → in-bounds-wrong-offset): the whole-file digest + Layers-1/2 result-verify already block an *unsafe applied* edit; suggest.md "fail-closed" wording made precise (digest = whole-file, bounds = invalid_edits, result = verify). A self-checking per-range preimage is an editscript/#27-schema hardening, out of #23's docs-authority scope → **follow-up filed**.
  - Med (`--dry-run` optional, unmutating-when-omitted untested): FIXED — CLI `run` hardcodes write=False (confirmed assemble.py:579-581); added `test_cli_run_without_dry_run_flag_is_still_non_mutating`; suggest.md clarifies the flag is reserved, not the safety boundary.
  - Low (plugin.json v0.1.9 contradiction): already named (M4) + owner-deferred to #25. No action.
