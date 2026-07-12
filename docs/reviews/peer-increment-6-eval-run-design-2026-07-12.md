# Peer Consult — increment-6-eval-run-design.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Treat the committed authored edit-scripts as the reproducible evaluation corpus, not as a claim that model inference is deterministic. Each candidate records provenance: engine/tier, effort, source fixture digest, authoring date, and whether it was authored live or manually encoded from a live session. The gated pytest replays those frozen candidates through the real runner, ledger verifier, and second-pass idempotence check. Separately, include one documented live Opus 4.8 authoring transcript or run record showing that the slopslap candidate was produced by applying the shipped skill; do not require live inference in CI. Evaluate all three baselines on identical fixture bytes and ledgers. For kukakuka-prd, derive a conservative ledger before editing, apply only localized repairs, verify zero invariant violations, and report deterministic voice-preservation proxies alongside a clearly secondary recorded blind A/B judgment. Mark Fable as OWNER-VERIFY (Fable API).

## Key decisions

- The DONE gate is deterministic replay of frozen candidate edit-scripts through production mechanics. Live regeneration is a separate provenance demonstration because requiring it in every run would make the proof irreproducible, costly, and sensitive to model drift.
- Bind every edit-script to the SHA-256 digest of its exact input bytes and reject digest mismatches. Compute byte offsets only from that bound input and reject overlapping, out-of-range, or stale edits.
- Represent ABSTAIN as an explicit candidate outcome with reason and an empty edit list, distinct from original-unchanged. Controls pass only when slopslap explicitly abstains and output bytes remain identical.
- Build the humanizer baseline from a declared, versioned transformation policy applied consistently across the full document: remove or rewrite the stylistic patterns humanizer targets without consulting slopslap's expected failures. Preserve its natural collateral edits rather than protecting invariants specially for the benchmark.
- Strengthen baseline fairness with provenance: name the humanizer implementation/version or frozen procedure, preserve raw before/after outputs, derive edits mechanically from those outputs, and disclose whether execution was live, locally reproduced, or faithfully emulated. If the actual tool cannot be run, label the result representative/emulated and avoid claiming a product-level comparison.
- Score each baseline against the same primary metrics: hard-gate result, invariant violations, control mutation, second-pass delta, and fixture-level decision-rule result. Report per-gate values, not only an aggregate winner. 'Beats/ties humanizer' means slopslap is no worse on every specified programmatic hard gate and strictly better on at least one fixture/gate unless the contract explicitly permits an all-tie result.
- For kukakuka-prd, ledger numeric literals with units and qualifiers; normative modals and negations in their clause context; URLs, identifiers, paths, commands, code spans/fences, schema keys, headings/anchors, and other protected literals recognized by the shipped verifier. Avoid treating all ordinary prose as invariant.
- Generate the PRD ledger before producing the repair and commit both its derivation inputs and verifier output. Fail closed on unclassified protected tokens rather than silently weakening the ledger.
- Demonstrate non-flattening deterministically with bounded edits and preservation measurements: unchanged distinctive passages, changed-byte/line ratio, untouched-section ratio, heading/order preservation, and no edits outside scanner-identified targets. Present these as proxies, not proof of literary quality.
- Use a blind, randomized A/B judge only as secondary evidence. The honest minimum is recorded trials through the shipped scaffold with prompts, anonymized candidate order, judge identity/version, raw responses, and aggregation committed. A fresh live judge run may supplement the artifact but should not gate reproducible CI.
- Run multiple recorded A/B trials with order reversal or deterministic randomization and allow ties/abstentions. Keep judge results outside the primary DONE computation unless the contract names an explicit judge threshold.
- Structure the Markdown and HTML identically: an executive verdict matrix first; then fixture-by-baseline hard-gate details; control abstention evidence; kukakuka invariant and preservation evidence; idempotence; secondary A/B results; provenance/limitations; and exact reproduction commands. Embed the complete result data in the HTML so it is self-contained.
- Have run_eval.py emit a stable, machine-readable results object with schema_version, fixture/input digests, candidate provenance, first- and second-pass results, ledger verification, PRD evidence, judge evidence, and final decision-rule calculations. Sort keys and fixture order for stable artifacts.
- The pytest invokes the evaluator rather than trusting committed result files. It asserts all three slopslap canonical fixtures clear every hard gate, all controls explicitly abstain without byte changes, kukakuka has zero invariant violations, second-pass edits are empty, and the declared comparison rule against humanizer holds.
- Do not tune fixtures, ledgers, thresholds, or the humanizer policy after inspecting failures without recording the change as an evaluation-protocol revision. No new exception may convert a failure into a pass in this increment.

## Risks

- Frozen authored candidates prove the skill's demonstrated output and deterministic mechanics, not the probability that an arbitrary future Opus session will reproduce the quality. The artifact must state this boundary plainly.
- A manually emulated humanizer can become a strawman. Without executable/versioned upstream output, comparison language must remain limited to the documented representative transformation.
- Automatic ledger extraction can miss semantic invariants such as scope relationships, exceptions, or which actor owns a requirement. Conservative contextual entries and a committed human audit are needed for the real PRD.
- Over-broad ledgering can make meaningful repairs impossible or produce misleading success through near-no-op edits; under-broad ledgering can hide damage. Report ledger contents and coverage categories visibly.
- Byte offsets are fragile across newline normalization, Unicode encoding, or fixture edits. Digest binding and byte-oriented application are mandatory.
- Idempotence may be falsely claimed if the second pass simply reapplies stale first-pass offsets. The second pass must rerun candidate generation logic applicable to the already-repaired text or explicitly validate that no repair targets remain.
- Deterministic voice proxies can show locality and preservation but cannot establish that revised prose remains distinctive. That conclusion should be phrased as judge-supported, not mechanically proven.
- A single LLM judge is noisy and may recognize stylistic signatures. Blinding, order reversal, raw evidence, and non-primary status reduce but do not eliminate this risk.
- Committing a live-model transcript may expose hidden reasoning, sensitive content, or non-reproducible metadata. Store only permissible prompts, outputs, configuration, and concise provenance.
- A self-contained HTML report can drift from the Markdown or results object if maintained manually. Both artifacts should be rendered from the same results data and checked for matching verdicts.

## Sketch

candidates.py
  Candidate {baseline, fixture, input_sha256, disposition, reason, edits, provenance}
  build_slopslap(input_bytes) -> localized edits | explicit ABSTAIN
  build_humanizer(input_bytes) -> doc-wide representative edits
  build_original(input_bytes) -> empty edits

run_eval.py
  for fixture in canonical_fixtures + controls:
    ledger = load_fixture_ledger(fixture)
    for baseline in [slopslap, humanizer, original]:
      candidate = build_candidate(baseline, fixture.bytes)
      assert candidate.input_sha256 == sha256(fixture.bytes)
      pass1 = hard_gate_runner(fixture.bytes, candidate.edits)
      verify1 = ledger_verify(fixture.bytes, pass1.output, ledger)
      pass2_candidate = build_candidate(baseline, pass1.output)
      pass2 = hard_gate_runner(pass1.output, pass2_candidate.edits)
      record {disposition, pass1, verify1, pass2, changed_bytes, changed_lines}

  prd = read kukakuka-prd bytes
  prd_ledger = derive_conservative_ledger(prd)
  audited_ledger = load committed reviewed ledger
  assert derived ledger matches audited ledger or explain reviewed additions
  repaired = apply slopslap PRD candidate
  assert ledger_verify(prd, repaired, audited_ledger).violations == []
  record locality and preservation proxies

  judge = load recorded blinded A/B trials
  results = calculate_decision_rule(all records, judge_secondary=judge)
  render the same results into Markdown and self-contained HTML
  return results

pytest
  results = run_eval()
  assert every slopslap canonical fixture passes every hard gate
  assert every slopslap control disposition == ABSTAIN and output_sha256 == input_sha256
  assert kukakuka invariant_violations == 0
  assert every slopslap second_pass edit list is empty and output is unchanged
  assert comparison_rule(slopslap, humanizer) in {BEATS, TIES} under the contract's exact rule
  assert artifact verdicts and embedded result digests match results

---
_Peer proposal (report-only). Synthesize at your discretion._
