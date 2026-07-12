# Adversarial Review — increment-3-scanner-design.md

- Date: 2026-07-12
- Artifact type: design
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 8 (Critical 0, High 1, Medium 7, Low 0)

## Summary

The brief defines a standalone prose scanner, vendored Markdown parsing, extraction rules, metrics, and capability-failure behavior. Its main risks are an installation test that does not exercise the real package/configuration, unproven parser-token assumptions, and several contracts that remain internally inconsistent or underspecified.

## Findings

### 1. [High] feasibility · high confidence — Folded decisions, item 4

> Copy the plugin to a temp layout, run
>    `scripts/scan_prose.py` under `python -I -S` (ignores `PYTHONPATH` + site-packages, so the env
>    markdown-it-py is invisible and only the vendored copy is reachable), cwd outside the plugin, cleared
>    env, scan a markdown fixture ⇒ assert `status=ok` + vendored origins.

This tests a copied source tree, not the artifact produced and installed by the project's real packaging mechanism. It can pass even if packaging excludes `vendor/python`, resolves symlinks differently, or the actual plugin sandbox does not permit the assumed Python subprocess, flags, file access, or temporary layout. The shipped scanner can therefore report `capability_unavailable` despite the declared packaged-layout test passing.

**Recommendation:** Replace Folded decision 4 with an end-to-end test that builds and installs the actual plugin artifact through the project's real installer, then executes the installed entry point under the declared capability/manifest and CI configuration. Cite that configuration and a passing spike; separately retain the copied-layout test only as an import-isolation unit test.

### 2. [Medium] ambiguity · high confidence — Folded decisions, item 8

> count a prefix once when it occurs in ≥3 distinct sentences in the window; canonicalize by
>    prefix+maximal contiguous range (no overlap double-count).

The counting unit is unresolved when the same prefix qualifies in several overlapping eight-sentence windows. “Maximal contiguous range” is undefined when matching sentences are separated by nonmatches, and “no overlap double-count” does not say whether adjacent qualifying windows merge. Different reasonable implementations will emit different counts, rates, and locations.

**Recommendation:** In `references/scanner-metrics.md`, define a deterministic event algorithm: how qualifying windows merge, what starts and ends a range, whether gaps are allowed, which location is emitted, and the exact numerator and eligible-unit denominator. Include overlapping-window and separated-occurrence fixtures.
**Ambiguity:** The range and deduplication rules permit multiple reasonable counting algorithms.

### 3. [Medium] completeness · high confidence — Folded decisions, item 1

> Same stable JSON envelope on EVERY path (`{status, format, ...}`),
>    diagnostics on stderr.

The “every path” guarantee does not define handling for ordinary CLI and I/O failures such as an unknown option, multiple file arguments, a missing or unreadable file, stdin read failure, or output serialization failure. Default argument-parser and uncaught I/O behavior commonly exits with non-JSON output, so implementations and acceptance tests cannot determine how the guarantee applies.

**Recommendation:** Add an Error envelope table under Capability contract covering every argument-parse and input-open/read failure, with status, `error_kind`, exit code, stdout JSON, and stderr behavior. Require the CLI parser and top-level I/O boundary to translate those failures into that table and add one fixture per path.

### 4. [Medium] completeness · high confidence — Folded decisions, item 4

> scan a markdown fixture ⇒ assert `status=ok` + vendored origins.

No success-envelope field or documented diagnostic exposes module origins, so the proposed black-box subprocess test has nothing specified to inspect for the “vendored origins” assertion. A test may fall back to implementation internals, weakening the promised packaged-layout verification.

**Recommendation:** Add a stable capability diagnostic to the success JSON, such as `capabilities.markdown_commonmark.modules` with resolved origins and versions, or define a test-only diagnostic flag and its output contract. Update the packaged-layout test to assert that specified output.

### 5. [Medium] consistency · high confidence — MVP metrics and Folded decisions, item 7

> Every result names `metric_version, extraction_profile, threshold_profile, confidence,
>    purpose=candidate_selection_only`.

This conflicts with both the earlier result envelope, which lists neither `metric_version`, `extraction_profile`, `confidence`, nor `purpose`, and the immediately preceding statement that confidence is recorded inside `threshold_profile.confidence`. Implementers must choose incompatible field placement, producing unstable JSON for consumers and fixtures.

**Recommendation:** Replace the result-shape statement in MVP metrics and Folded decision 7 with one normative JSON schema. Specify whether `confidence` and `purpose` are top-level or members of `threshold_profile`, and provide separate schemas for distribution metrics and scalar metrics.
**Ambiguity:** The artifact defines multiple incompatible locations and inventories for the same result metadata.

### 6. [Medium] correctness · high confidence — Folded decisions, item 13

> **If PyPI is
>     unreachable in this run, fall back to vendoring the host's installed 3.0.0/0.1.2, record that source
>     honestly in PROVENANCE, and flag a follow-up to re-vendor from the sdist (does not block — the
>     version-gate + origin check still hold).**

A host installation can contain downstream patches, missing files, or locally modified code while still exposing the expected version. The runtime version and origin checks prove only name, location, and declared version—not equivalence to the immutable upstream artifact—so this fallback defeats the stated content-pinning and repeatable provenance goals while being declared non-blocking.

**Recommendation:** Change Folded decision 13 so lack of the verified sdist blocks the vendoring update. If an emergency host-copy path must exist, require hashing every copied file against a trusted upstream RECORD or previously approved manifest and reject the copy when that verification is unavailable; do not describe version and origin checks as sufficient.

### 7. [Medium] feasibility · high confidence — Folded decisions, item 5

> Walk block+inline tokens with source-LINE maps (promise
>    line ranges; columns only where deterministic). Drop fenced/indented code, HTML blocks, blockquotes,
>    inline code, link destinations; retain visible link labels, headings, list text, emphasis metadata,
>    paragraph boundaries.

The design assumes the exact token objects emitted by the vendored parser expose sufficient maps and nesting information for every promised exclusion, retained structure, and source line range. No exact token-kind call site or spike is cited, so this dependency is unverified from the provided text. If inline children or synthesized text lack the assumed maps, reproducible locations and exclusion boundaries cannot be implemented as specified.

**Recommendation:** Add an extraction-spike appendix to the Markdown extraction section showing, for every supported construct, the exact `markdown-it-py==3.0.0` token types and fields consumed (`type`, `tag`, `nesting`, `map`, `children`, `content`, and relevant metadata), plus fixture assertions produced under the vendored packaged runtime.

### 8. [Medium] internal-consistency · high confidence — Folded decisions, item 3

> Any origin/version mismatch ⇒
>    `capability_unavailable` with the reason — it NEVER mutates `sys.modules`.

This conflicts with the preceding requirement to import `markdown_it` and `mdurl`: normal Python imports populate and may update `sys.modules`. Implementers cannot literally satisfy both statements, creating uncertainty about whether imported modules must be removed, retained, or merely not manually replaced.

**Recommendation:** Change Folded decision 3 to say that the scanner never deletes, replaces, or aliases existing `sys.modules` entries manually; explicitly acknowledge that normal imports populate the fresh CLI process's module cache and define whether failed capability checks leave those entries untouched until process exit.
**Ambiguity:** “Never mutates” could intend “never manually rewrites,” but the text states the broader impossible requirement.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._