# Adversarial Review — .rawgentic-23-branch.diff

- Date: 2026-07-13
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 4 (Critical 0, High 2, Medium 1, Low 1)

## Summary

The change makes deterministic verification authoritative for suggest mode through documentation and tests, but the edit-script contract cannot detect all source/offset mismatches and the tests do not exercise an actual suggest-to-seam adapter. The non-mutating guarantee also remains ambiguous at the documented CLI boundary.

## Findings

### 1. [High] completeness · high confidence — tests/test_suggest_verifier_wiring.py — verifier input construction

> +def test_suggest_candidate_diff_roundtrips_to_editscript():
> +    """A suggest candidate diff serializes to the {start_byte,end_byte,replacement_b64} the seam
> +    consumes and round-trips through parse_edits to the same Edit."""
> +    e = Edit(5, 9, b"quick")

The purported suggest-input-construction test starts with an already constructed `Edit` and merely round-trips a hand-built dictionary through `parse_edits`. It never consumes a suggest candidate, invokes the documented `eval/candidates._span` or `to_envelope` path, or passes the result through the seam. Suggest-to-edit construction can therefore be absent or malformed while this test remains green.

**Recommendation:** Replace `test_suggest_candidate_diff_roundtrips_to_editscript` with a test that creates the real structured suggest candidate through the production candidate-construction path, serializes it through a production adapter, and submits the resulting file to `assemble.py run`. Add cases for non-ASCII text and multiple edits.

### 2. [High] correctness · high confidence — commands/suggest.md — Seam contract

> +Serialize the candidate as a JSON edit-script — a list of `{start_byte, end_byte, replacement_b64}`
> +(base64) in ORIGINAL byte coordinates — then **dry-run** it end-to-end:

The edit schema carries offsets and replacement bytes but no source digest or expected preimage for each range. Contrary to the nearby fail-closed claim, offsets computed against different content can remain valid and in bounds, causing verification to inspect and approve an edit against the wrong bytes without producing `digest_mismatch` or `invalid_edits`.

**Recommendation:** Change the Seam contract to include a top-level `source_sha256` and either `expected_original_b64` or an original-range hash for every edit. Require `assemble.py run` to compare these values against `--path` before audit or verification, and add tests for shifted-but-in-bounds offsets caused by a newline or multibyte UTF-8 difference.

### 3. [Medium] ambiguity · high confidence — commands/suggest.md — Seam contract

> +python3 scripts/slopslap_assemble/assemble.py run --path PATH --edits EDITS.json [--dry-run] [--format markdown|text] [--declared-genre GENRE]

The command synopsis marks `--dry-run` as optional even though suggest is declared non-mutating. The diff does not show what happens when the flag is omitted, and the new tests only exercise calls that include it, so the non-mutating boundary is unverifiable and a copied invocation may take the applying path.

**Recommendation:** Change the suggest command example to require `--dry-run` without brackets, require the returned envelope to attest dry-run mode, and add a CLI test proving omission of `--dry-run` fails closed without modifying the source.
**Ambiguity:** The diff does not expose the CLI's default behavior when --dry-run is omitted.

### 4. [Low] internal-consistency · high confidence — docs/planning/2026-07-13-23-suggest-verifier-wiring.md — File changes / known temporary contradiction

> +**Known temporary contradiction (M4, named not hidden):** `.claude-plugin/plugin.json:4` description
> +says the suggest invariant-check is "model-reported … until the deterministic … verifier land[s]".
> +After #23 (v0.1.9) that clause is FALSE — the verifier is now the authority.

Version 0.1.9 deliberately ships public manifest metadata that contradicts the updated suggest contract. Consumers relying on the manifest description will be told that deterministic verification has not landed, while the skill says it is authoritative.

**Recommendation:** Update `.claude-plugin/plugin.json` in this change to describe deterministic suggest verification as current behavior; do not defer the correction to #25.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._