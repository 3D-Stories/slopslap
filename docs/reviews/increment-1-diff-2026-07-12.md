# Adversarial Review — increment-1.diff

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 8 (Critical 0, High 7, Medium 1, Low 0)

## Summary

The change implements a fixture-based acceptance runner, but several validators and gates are fail-open on incomplete manifests, partial judge results, malformed Markdown, corrupt encoding, and omitted envelope linkage. These paths can produce PASS for candidates that have not satisfied the stated acceptance contract, while malformed inputs can also escape the declared FIXTURE_ERROR state by crashing the runner.

## Findings

### 1. [High] completeness · high confidence — scripts/eval/runner.py — run and _acceptance_state

> +    judge: Optional[JudgeOutcome] = None,
> +) -> RunResult:

The runner accepts an unsubstantiated `JudgeOutcome` boolean rather than validated trials, and the outcome contains no fixture, candidate hash, or baseline identity. It also accepts only one outcome even though the acceptance contract says judging is against both `humanizer` and `original-unchanged`. A caller can pass `JudgeOutcome(present=True, beat=True)` for the wrong artifact or only one baseline and obtain acceptance PASS.

**Recommendation:** Change `run` to accept validated judge verdict records bound to the fixture name, reconstructed revision hash, and baseline hash/name. Require successful verdicts for both named baselines before canonical PASS, and derive `beat` through `judge.evaluate` rather than accepting a caller-provided boolean.

### 2. [High] completeness · high confidence — scripts/slopslap_verification/mdstructure.py — compare

> +    if r["broken_links"] > o["broken_links"]:
> +        violations.append(
> +            f"introduced {r['broken_links'] - o['broken_links']} unterminated "
> +            f"link/image destination(s)"
> +        )

The binding design explicitly requires inline code-span backtick balance, but `compare` checks only fence parity, code-block count, and link destinations. Deleting an inline code span's closing backtick changes none of these features and can pass `markdown_structure`, despite being one of the supported Markdown damage classes.

**Recommendation:** Add inline-code delimiter validation to `mdstructure.structural_features` and `compare`, with CommonMark-aware handling of backtick run lengths. Add a test that removes an inline code closing delimiter and requires failure.

### 3. [High] correctness · high confidence — scripts/eval/loader.py — validate_manifest

> +    editable = [(r["start_byte"], r["end_byte"]) for r in manifest.get("editable_ranges", [])]
> +    protected = [
> +        (r["start_byte"], r["end_byte"]) for r in manifest.get("protected_spans", [])
> +    ]

The validator treats missing gate-defining fields as empty collections instead of invalid manifests. Missing `protected_spans`, `invariant_regions`, `expected_invariants`, or `allowed_claim_atoms` therefore produces no validation error, and the corresponding gates iterate zero items and pass vacuously. A truncated or incorrectly authored canonical fixture can consequently reach deterministic PASS without enforcing its preservation obligations.

**Recommendation:** In `validate_manifest`, require every field in the binding schema with its declared type, including `control`, `byte_policy`, `editable_ranges`, `protected_spans`, `invariant_regions`, `expected_invariants`, `allowed_claim_atoms`, `seeded_defects`, and `control_reason`. Return manifest problems for every absent or mistyped field before constructing ranges or running gates.

### 4. [High] correctness · high confidence — scripts/slopslap_verification/atoms.py — CHECK_EXTRACTORS

> +    "units": numbers,  # units ride along with the numeric token in this MVP

The `units` check extracts only numeric values; it does not capture a unit. Changing `200 ms` to `200 seconds` leaves the extracted counter unchanged, so a fixture whose editable and invariant regions overlap can pass the stated no-changed-unit hard gate.

**Recommendation:** Replace the `units` mapping in `CHECK_EXTRACTORS` with a quantity extractor that returns normalized tuples containing the numeric token and unit. Add a mutation test that changes only `ms` to another unit and requires `preservation_region_scoped` to fail.

### 5. [High] correctness · high confidence — scripts/eval/judge.py — Trial.validate and beat_criterion

> +        for label, scores in (("candidate", self.candidate), ("baseline", self.baseline)):
> +            for dim, val in scores.items():
> +                if dim not in DIMENSIONS:
> +                    raise ValueError(f"unknown judge dimension '{dim}'")
> +                if val not in (0, 1, 2):
> +                    raise ValueError(f"{label}.{dim} score {val} not in 0/1/2")

Trial validation checks only dimensions that were supplied and never requires the complete dimension set. A judge can omit `unsupported_claim_introduction` and every other unfavorable dimension, submit one favorable dimension for three trials, and satisfy `beat_criterion`; canonical acceptance can then PASS without the required semantic unsupported-claim evaluation.

**Recommendation:** In `Trial.validate`, require `set(candidate) == set(DIMENSIONS)` and `set(baseline) == set(DIMENSIONS)`. Make `evaluate` return an errored verdict if any trial is incomplete, and make `beat_criterion` reject median maps missing any required dimension.

### 6. [High] correctness · high confidence — scripts/eval/runner.py — reconstruct and _second_pass_revision

> +    declared = envelope.get("revision_sha256")
> +    if declared is not None and sha256_hex(revision) != declared:

A supposedly required candidate hash is checked only when present. The second-pass `base_hash` is handled the same way, and neither first- nor second-pass `pass_index` is validated. Envelopes lacking their provenance/linkage fields are therefore accepted, allowing a dummy second-pass envelope with empty edits to satisfy idempotence without meeting the documented input contract.

**Recommendation:** In `reconstruct` and `_second_pass_revision`, require `revision_sha256`, `base_hash`, and the correct `pass_index` values. Reject absent, malformed, or mismatched values as FIXTURE_ERROR; also require and verify a second-pass revision hash.

### 7. [High] correctness · high confidence — scripts/slopslap_verification/gates.py — _decode

> +def _decode(b: bytes) -> str:
> +    return b.decode("utf-8", errors="replace")

Candidate replacements are arbitrary base64 bytes, but invalid UTF-8 is silently converted to replacement characters for all text-based gates. Manifest validation also does not enforce the declared encoding. A revision containing corrupt byte sequences can therefore pass claim, preservation, and Markdown checks and reach acceptance PASS even though the fixture contract declares UTF-8.

**Recommendation:** Decode original and reconstructed revisions with strict UTF-8 before running gates. Convert `UnicodeDecodeError` or a byte-policy encoding other than the supported value into FIXTURE_ERROR, and add a test using an invalid UTF-8 replacement payload.

### 8. [Medium] correctness · high confidence — scripts/eval/runner.py — run reconstruction error handling

> +    try:
> +        revision = reconstruct(original, candidate)
> +        second_rev = _second_pass_revision(revision, second_pass)
> +    except RunError as err:

Only `RunError` is converted to FIXTURE_ERROR. `parse_edits` and `apply_edits` can instead raise `EditError`, base64 decoding errors, `KeyError`, `ValueError`, or `TypeError`; malformed candidate input therefore crashes the evaluation rather than producing the documented fail-closed state and JSON result.

**Recommendation:** Validate envelope structure explicitly and catch the edit-script decoding/validation exception types in `run`, converting them to a `reconstruct` gate with FIXTURE_ERROR. Keep unexpected internal exceptions distinct so programming defects are not mislabeled as fixture errors.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._