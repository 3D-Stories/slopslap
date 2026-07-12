# Adversarial Review — .rawgentic-diff-30.patch

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 4 (Critical 0, High 3, Medium 1, Low 0)

## Summary

The change adds a corpus manifest, family-level partitions, licensing checks, and authored verification fixtures. Several fail-closed and licensing claims are not enforced by the implementation, allowing incomplete partition metadata and unlicensed verbatim content to pass validation; one regression test is also tautological.

## Findings

### 1. [High] correctness · high confidence — scripts/slopslap_corpus/manifest.py, _validate_item split validation

> +    split = item.get("split")
> +    if split is not None:

Split validation runs only when `split` is non-null. A calibration- or judge-reference-lane item can omit `split` or set it to null, load successfully, and then be silently excluded from both `calibration_items()` and `held_out_items()`. This directly contradicts the stated fail-closed behavior and can make calibration or held-out evaluation incomplete without an error.

**Recommendation:** In `manifest.py::_validate_item`, require `split` to be one of `VALID_SPLIT` whenever `artifact_lanes` intersects `SPLIT_ELIGIBLE_LANES`; require `split` to be null for all other lanes. Add tests for an eligible item with both an absent and null split.

### 2. [High] security · high confidence — tests/test_corpus_licensing.py, test_redistributable_lanes_are_licensed_and_attributed

> +        if lanes & {"fixture", "calibration"}:

The redistribution gate is based on lane labels rather than whether bytes are actually committed. A `judge_reference`-only item can name a `verbatim_path` while declaring prohibited redistribution and still pass this licensing test; likewise, any mislabeled item outside the two selected lanes bypasses the check. The separate hash test verifies integrity but not permission, so committed unlicensed content can pass the suite.

**Recommendation:** In `test_corpus_licensing.py`, apply the redistribution and attribution requirements to every item with a non-null `verbatim_path` or non-null content hash, independent of lane. In `manifest.py`, reject any verbatim-bearing item whose redistribution is not permitted or share-alike.

### 3. [High] security · high confidence — research/ai-slop-corpus/corpus_manifest.jsonl, humanizer entries

> +{"source_id": "02", "item_id": "hum-negative-parallelism", "source_family": "humanizer", "citation": "humanizer skill (Wikipedia-derived), SKILL.md v2.5.1", "revision": "v2.5.1; fetched 2026-07-12", "license": "MIT", "allowed_uses": ["fixture", "calibration"], "redistribution": "permitted", "attribution": "humanizer skill (MIT); derivative of Wikipedia 'Signs of AI writing' (CC BY-SA 4.0) -- share-alike + attribution obligations flow through", "direction": "ai_to_human", "tells": ["synthetic_cadence"], "genre": "encyclopedic", "control": false, "after_validity": "faithful", "artifact_lanes": ["fixture", "calibration"], "content_hashes": {"before": null, "after": null}, "lineage": "local skill; upstream Wikipedia CC BY-SA guide", "notes": "'X, not Y' negative parallelism pair (the #1 tell)", "split": "calibration", "verbatim_path": null}

The item explicitly records that CC BY-SA share-alike obligations flow through, but classifies redistribution as merely `permitted`. The licensing test accepts `permitted` without enforcing a CC BY-SA license notice or share-alike classification, so future redistributed humanizer-derived bytes can pass under weaker MIT-style handling despite the artifact's own stated obligation.

**Recommendation:** Change every Wikipedia-derived humanizer item’s `redistribution` to `share-alike` and represent the effective derivative license as CC-BY-SA-4.0, with MIT recorded separately for upstream component licensing. Add a test requiring `share-alike` and the applicable license notice whenever `lineage` identifies a CC BY-SA derivative.

### 4. [Medium] correctness · high confidence — tests/test_authored_fixtures.py, test_positive_fixture_idempotence_gate_fires

> +    second = helpers.make_second_pass(first_pass, [])  # no-op second pass == idempotent
> +    result = runner.run(fixture_dir, envelope, second_pass=second)

The idempotence test manufactures an empty second-pass edit list instead of running the transformation again. It therefore proves only that an explicitly supplied no-op is a no-op; an implementation that repeatedly changes or oscillates on these fixtures would still pass, so the claimed idempotence coverage is vacuous.

**Recommendation:** In `test_positive_fixture_idempotence_gate_fires`, obtain the second pass by invoking the same candidate-generation/transformation path on `first_pass`, then assert that the generated second-pass edits are empty and that the gate passes.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._