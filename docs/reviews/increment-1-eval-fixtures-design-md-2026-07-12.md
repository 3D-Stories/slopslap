# Adversarial Review — increment-1-eval-fixtures-design.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 7 (Critical 0, High 3, Medium 4, Low 0)

## Summary

The artifact defines a fixture-first acceptance runner, but several binding decisions do not fully enforce the stated hard gates. The largest risks are false passes for semantic claim invention and clean-control edits, plus a Markdown gate that does not test the failure modes it names.

## Findings

### 1. [High] completeness · high confidence — Clean-document controls; Runner; Folded decisions 7–8

> Clean-document controls: pass criterion is **abstention** — original-unchanged must win/tie; ANY
> material edit is a FAIL.

No folded decision or named deterministic gate implements this rule. The generic edit-authorization gates can permit an edit to a control when it falls within an editable range, while live A/B judging is deferred, producing a false PASS for a materially edited clean control.

**Recommendation:** Add a required `control_abstention` gate to `scripts/slopslap_verification/`. For `control:true`, define “material edit” precisely, compare the reconstructed revision against the original under that definition, and return FAIL for every material difference independently of judge scores or editable ranges.

### 2. [High] correctness · high confidence — Hard gates; Folded decision 5

> 5. **Invented-claim = mechanical hard gate** for enumerable atoms (new numbers/dates/proper-noun
>    candidates/URLs-endpoints/thresholds-comparators/citation markers; fixture-declared
>    `allowed_claim_atoms` exempted) **+ a separate named judge dimension** for semantic unsupported
>    claims. The mechanical gate never implies semantic non-invention.

The stated hard gate is “no invented claim,” but the deterministic gate detects only enumerable atoms, while semantic judging is deferred. A revision can therefore introduce an unsupported claim containing no new enumerated atom and receive a deterministic PASS, violating the acceptance contract.

**Recommendation:** Change Folded decision 5 and the result-state logic so semantic claim evaluation is required for canonical acceptance. Until a semantic evaluator result is supplied, return INCOMPLETE rather than PASS; alternatively narrow the increment’s advertised gate explicitly to “no new enumerable claim atoms.”

### 3. [High] correctness · high confidence — Folded decision 2

> Gate requires successful parse
>    **pre AND post** (not AST-equivalence — legitimate prose edits change text nodes).

A CommonMark parser normally converts malformed-looking constructs such as unclosed fences or broken link syntax into valid token/text output instead of reporting a parse failure. Consequently, “successful parse” is nearly vacuous and will not detect the structural Markdown damage this gate is intended to reject.

**Recommendation:** Replace the parse-success criterion in Folded decision 2 with explicit token/source invariants for the supported failure classes, such as fence closure and link-destination validity, backed by mutation tests. If only parser execution is intended, rename the gate so it does not claim Markdown structural validity.

### 4. [Medium] ambiguity · high confidence — Folded decisions 1 and 6

> 6. **Idempotence** returns **`not_evaluated`** when no 2nd-pass artifact is supplied (NOT "passed");
>    canonical acceptance requires the 2nd pass once a rewriter baseline exists (eval-run increment).
>    Tested here with synthetic stable/unstable pairs.

The artifact does not define “material diff,” how a second-pass artifact is bound to the first-pass revision, or whether its edits are based on the original or first-pass coordinates. Different implementations can compare the wrong artifacts or ignore byte-level changes and report contradictory idempotence results.

**Recommendation:** Add an Idempotence input contract defining a run/candidate identifier, the second pass’s base hash and coordinate space, reconstruction rules, and the exact material-equivalence function. Require hash linkage from pass two to the reconstructed pass-one bytes before comparison.
**Ambiguity:** The intended relationship between the candidate envelope’s `pass_index` and the optional second-pass artifact is not specified.

### 5. [Medium] completeness · high confidence — Fixture representation; Folded decisions 3 and 5

> `fixture.json` — `{editable_ranges:[{start_byte,end_byte}], protected_spans:[{start_byte,end_byte,sha256,kind}], expected_invariants:[{kind,text,preservation}], genre, seeded_defects:[...], control:bool}`.

The only concrete manifest schema omits fields later made mandatory, including `invariant_regions[]` and `allowed_claim_atoms`. Implementing the literal schema leaves the region-scoped and exemption-aware gates without required inputs; inventing those field shapes independently risks incompatible fixtures and runner logic.

**Recommendation:** Replace the Fixture representation’s inline schema with the final binding schema, including exact structures, required/optional status, defaults, coordinate semantics, and validation rules for `invariant_regions` and `allowed_claim_atoms`.

### 6. [Medium] feasibility · high confidence — Folded decisions 2 and 8; Out of scope

> 2. **Markdown parse gate uses a real CommonMark parser NOW** — `markdown-it-py` (present in env,
>    v3.0.0; the scanner increment vendors it for distribution).

The artifact asserts availability in an unspecified environment but cites no project dependency/lock file, capability or manifest entry, CI configuration, exact call-site spike, or packaged-plugin proof. Because vendoring is deferred, a clean CI or plugin execution environment can lack the parser and make the required acceptance run INCOMPLETE. The later distinction between `capability_unavailable` and the separately listed `parser setup` FIXTURE_ERROR is also undefined.

**Recommendation:** In Folded decision 2, cite the exact project dependency and CI/plugin capability mechanism that supplies version 3.0.0, or vendor the parser in this increment. In Result states, define unimportable dependency as INCOMPLETE and reserve FIXTURE_ERROR for a specifically enumerated set of malformed or incompatible parser configurations.

### 7. [Medium] internal-consistency · high confidence — Judge scaffold; Folded decision 8

> 8. **Result states:** `PASS` (all required gates pass) · `FAIL` (any gate fails) · `INCOMPLETE`
>    (required artifact/capability absent, e.g. no 2nd pass or parser missing) · `FIXTURE_ERROR`
>    (invalid manifest / parser setup). **Judge scores annotate only a deterministic `PASS`** and can
>    never promote another state.

This makes judge scores annotations on an already-final PASS, while the earlier scoring logic defines a judge-dependent beat criterion as part of acceptance. It is therefore unclear whether a deterministic PASS that loses the A/B comparison remains PASS or becomes FAIL. The unanchored 0/1/2 dimensions further prevent consistent implementation of that decision.

**Recommendation:** Rewrite Result states as an explicit two-stage model: `deterministic_state` followed by `acceptance_state`. Specify whether a judge loss demotes deterministic PASS, define the state used when judging is absent or errors, and provide direction and 0/1/2 anchors for every dimension before defining medians and tie-breaks.
**Ambiguity:** “Annotate only” and the earlier judge-dependent beat criterion assign conflicting roles to judge results.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._