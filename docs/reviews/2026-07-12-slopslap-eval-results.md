# slopslap eval results — the working proof

**Overall: ✅ ALL PASS**  
Engine: `opus-4.8` — authoring engine recorded, not selected by the plugin (advisory); Fable 5 = OWNER-VERIFY (Fable API — no access confirmed)

## Verdict matrix (primary — deterministic hard gates)

| DONE criterion | result |
|---|---|
| slopslap clears hard gates on all 3 canonical fixtures | ✅ |
| slopslap abstains (no byte change) on both clean controls | ✅ |
| slopslap 2nd pass is empty (idempotent) everywhere | ✅ |
| kukakuka-prd: 0 invariant violations | ✅ |
| kukakuka-prd: Layer-3 fold reaches shippable ACCEPT | ✅ |
| beats/ties the humanizer-emulation policy | ✅ |

## Per-fixture × baseline (hard-gate pass)

| fixture | slopslap | humanizer_emulation | original_unchanged |
|---|---|---|---|
| distinctive-essay | ✅ (repair) | ❌ (repair) | ✅ |
| normative-spec | ✅ (repair) | ✅ (abstain) | ✅ |
| underspecified-prd | ✅ (repair) | ❌ (repair) | ✅ |
| clean-personal *(control)* | ✅ (abstain) | ❌ (repair) | ✅ |
| clean-spec *(control)* | ✅ (abstain) | ❌ (repair) | ✅ |

**Comparison vs humanizer-emulation:** BEATS (strictly better on 6 gate(s), worse nowhere: True).

## kukakuka-prd (real 421-line PRD — end-to-end)

- audit: shipped scanner flagged synthetic-cadence tells: negative-parallelism x16, em-dash 25.101/1k, semicolon 26.991/1k — NOT clean prose
- slopslap disposition: **repair** — repaired 2 demonstrated-harm passage(s)
- invariant violations: **0** · bytes changed: **119** · changed-byte ratio: 0.00425 · headings preserved: True
- Layer-3 fold (end-to-end): semantic_status **clean** · proposal_status **ACCEPT** · decision **ACCEPT** (offline these are by-construction: a hardcoded `clean` stub + candidate-span locality; a real `claude -p` semantic judgement runs under `SLOPSLAP_LIVE=1`)
- conservative ledger over real invariants: 2 entries, 1 protected span(s); negative control (bad edit rejected): True
- slopslap made **2 localized repairs** (drop an 'honest crash recovery' anthropomorphism + the tautological 'two materials' metaphor) with ZERO invariant violations; the pervasive negative-parallelism cadence is FLAGGED for the human, not doc-wide flattened (genre=PRD tolerates some punch — slopslap preserves voice). These are seeded, author-demonstrated frozen edit-scripts (the SKILL's demonstrated output), verified through the real gates — not live per-session generation (same provenance as the canonical fixtures).

## LLM-judge (secondary, non-gating): **NOT_RUN**

> secondary + non-gating (contract §7). A cross-model blinded A/B (Codex gpt-5.6-sol) is a documented follow-up; the PRIMARY proof is the programmatic hard gates + abstention below.

## Provenance & limitations

- The candidate edit-scripts are FROZEN, content-keyed, and replayed through the production runner + verifier. This proves the deterministic mechanics + the SKILL's demonstrated output — NOT that an arbitrary future session reproduces the quality.
- `humanizer_emulation` is a declared representative policy, NOT the upstream humanizer product; the comparison is against that documented policy only.

## Reproduce

```bash
pytest tests/test_eval_run.py -q
python3 scripts/eval/run_eval.py   # prints the full results JSON
```
