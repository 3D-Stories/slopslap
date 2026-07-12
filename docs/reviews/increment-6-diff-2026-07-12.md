# Adversarial Review — increment-6.diff

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 7 (Critical 0, High 4, Medium 3, Low 0)

## Summary

The change adds a deterministic evaluation gate and generated result artifacts, but several aggregation and validation paths can report PASS from incomplete, weakly protected, or stale evidence. The largest risks are treating INCOMPLETE as success, comparing only aggregate fixture outcomes, and hard-coding audit evidence.

## Findings

### 1. [High] completeness · high confidence — scripts/eval/run_eval.py, `_kukakuka()` ledger construction

> +    url = b"wehewehe.org"
> +    ui = prd.find(url)
> +    if ui >= 0:
> +        manifest["protected_spans"].append(
> +            {"start_byte": ui, "end_byte": ui + len(url), "sha256": sha256_hex(prd[ui:ui + len(url)])})
> +    strike = b"permanent ban after 3 strikes"
> +    si = prd.find(strike)
> +    if si >= 0:
> +        manifest["invariant_regions"].append(
> +            {"start_byte": si, "end_byte": si + len(strike), "checks": ["numbers"]})

The purported conservative PRD ledger protects only two optional literal matches, and silently omits either invariant when it is absent or altered. This contradicts the stated coverage of numeric literals, modals, negations, identifiers, paths, commands, code, and headings; a missing or corrupt match produces a weaker or empty ledger whose zero-violation result still passes DONE.

**Recommendation:** Replace the optional literal construction in `_kukakuka()` with the committed, reviewed ledger described by the design. Assert its expected digest and coverage categories, fail if any required span cannot be resolved, and reject unclassified protected tokens rather than skipping them.

### 2. [High] correctness · high confidence — scripts/eval/run_eval.py, `_cell()`

> +        "hard_gates_pass": result.deterministic_state in (State.PASS, State.INCOMPLETE)
> +                           and not any(v == "fail" for v in gates.values()),

An evaluator result explicitly marked INCOMPLETE is converted into a passing hard-gate result whenever its reported gates contain no literal `fail`. Missing evidence or an unfinished runner result can therefore satisfy `canonical_all_hard_gates_pass` and ultimately produce `ALL_PASS`.

**Recommendation:** Change `_cell()` in `scripts/eval/run_eval.py` so `hard_gates_pass` requires `result.deterministic_state == State.PASS`. Treat `State.INCOMPLETE`, unknown gate statuses, and an empty gate collection as failures with a surfaced reason.

### 3. [High] correctness · high confidence — scripts/eval/run_eval.py, `_beats()`

> +        s = slopslap_cells[fx]["hard_gates_pass"]
> +        h = humanizer_cells[fx]["hard_gates_pass"]
> +        per[fx] = {"slopslap": s, "humanizer_emulation": h}
> +        if s and not h:
> +            strictly_better += 1
> +        if h and not s:
> +            worse_anywhere = True

The declared comparison requires slopslap to be no worse on every programmatic hard gate and better on at least one fixture/gate, but `_beats()` compares only aggregate fixture booleans. If both baselines fail a fixture on different gates, they are treated as equal; a win elsewhere can then yield `BEATS` even though slopslap is worse on a specific gate.

**Recommendation:** Rewrite `_beats()` to compare the two cells gate-by-gate over an explicit common gate inventory. Set `worse_anywhere` when any slopslap gate ranks below the corresponding humanizer gate, and count strict improvements per fixture/gate rather than per aggregate fixture result.

### 4. [High] correctness · high confidence — scripts/eval/run_eval.py, `_kukakuka()` result construction

> +        "audit": {"units_scanned": 107, "slop_clusters": 0,
> +                  "note": "scanner (markdown) found 0 stock/vague/transition clusters — clean, distinctive prose"},

The PRD scanner result is a hard-coded assertion rather than output from a scanner call. The report will continue claiming that 107 units were scanned and zero clusters found even if the PRD changes or scanning fails, producing false evidence for the clean-document abstention.

**Recommendation:** In `_kukakuka()`, invoke the shipped scanner on the current PRD bytes and populate `units_scanned`, `slop_clusters`, and the note from its returned result. Make scanner absence, errors, or incomplete output fail the PRD evaluation instead of substituting constants.

### 5. [Medium] completeness · high confidence — tests/test_eval_run.py, `test_decision_rule_inventory_is_complete()`

> +    for fx in CONTROLS:
> +        gates = set(_R["fixtures"][fx]["baselines"]["slopslap"]["gates"])
> +        assert "control_abstention" in gates, (fx, gates)

The test named `test_decision_rule_inventory_is_complete` verifies only one gate for each control. `edit_locality` and `markdown_structure`, which the committed results currently report for controls, can disappear without failing this test; unknown or empty statuses for them can then pass through the aggregate logic.

**Recommendation:** Define a required-gates mapping for canonical and control fixtures from `HARD_GATES`, and assert exact required membership plus `status == "pass"` for every required gate. Reject missing, extra-unknown, or non-pass statuses.

### 6. [Medium] consistency · high confidence — scripts/eval/run_eval.py, executable entry point

> +if __name__ == "__main__":
> +    res = run_eval()
> +    print(json.dumps(res, indent=2, sort_keys=True))

Despite the module claiming to render Markdown and HTML from the results object, its executable path only prints JSON. The tests also do not compare the committed artifacts with current evaluator output, so the checked-in reports can retain an obsolete PASS verdict after evaluation logic or fixtures change.

**Recommendation:** Update the `run_eval.py` main path to write both report files using `render_md()` and `render_html()`, or add a check mode that compares generated content byte-for-byte with the committed artifacts. Invoke that check from `tests/test_eval_run.py` or CI.

### 7. [Medium] correctness · high confidence — scripts/eval/run_eval.py, `_cell()`

> +    cand = C.BUILDERS[baseline](fixture, original)
> +    assert cand.input_sha256 == sha256_hex(original), "candidate input digest mismatch"

The input-binding check is tautological: every builder receives `original` and assigns `sha256_hex(original)` to the candidate immediately before the assertion recomputes the same value. It cannot detect that fixture bytes differ from the frozen authoring input, so non-slopslap candidates and dynamically generated pass-two candidates are not actually bound to a previously recorded input digest.

**Recommendation:** Store an independently committed expected input digest for each frozen fixture/candidate and compare the loaded bytes against it before calling the builder. Include and validate the input digest in both pass envelopes; define separate expected bindings for pass-two outputs where applicable.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._