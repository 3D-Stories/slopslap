# Adversarial Review — increment-2.diff

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 5 (Critical 0, High 3, Medium 2, Low 0)

## Summary

The change scaffolds a prompt-driven editorial plugin with read-only, suggestion, and fail-closed mutation modes. Its principal risks are a likely invalid skill manifest, an advertised verifier that is explicitly absent, raw argument injection into model instructions, and refusal semantics that may still appear successful to automation.

## Findings

### 1. [High] consistency · high confidence — .claude-plugin/plugin.json description; skills/slopslap/SKILL.md Reference map

> +  "description": "Repairs prose carrying high editorial cost (genericness, unsupported claims, synthetic cadence, obscured responsibility, voice discontinuity) while preserving meaning, technical accuracy, requirements, uncertainty, and intentional voice. NOT an AI-authorship detector: it beats humanizer-style tools by never treating a stylistic tell as a contaminant. Ships a judgment skill, audit/suggest/apply commands, a measure-only scanner, and a byte-exact invariant verifier.",

The public manifest says this version ships a measure-only scanner and byte-exact verifier, but the diff explicitly places the scanner and invariant ledger in future increments and supplies only model instructions for invariant checking. Users can therefore receive an apparent invariant-check result without the advertised deterministic verification, creating a fail-open acceptance path for meaning-changing rewrites.

**Recommendation:** In `.claude-plugin/plugin.json`, remove the scanner and byte-exact-verifier shipping claim for version 0.1.0 and describe invariant checks as model-reported and non-deterministic. Alternatively, add the actual scanner and deterministic verifier in this increment and make suggest/apply refuse acceptance when that verifier is unavailable.

### 2. [High] correctness · high confidence — skills/slopslap/SKILL.md frontmatter and tests/test_scaffold.py::_frontmatter

> +description: Use when asked to repair, de-slop, tighten, or edit prose (essays, specs, PRDs, ADRs, READMEs, docs) for editorial quality WITHOUT losing meaning, requirements, uncertainty, or the author's voice. Diagnoses genericness, unsupported claims, synthetic cadence, obscured responsibility, and voice discontinuity, then proposes minimal passage-local repairs. NOT an AI-authorship detector — never strips a stylistic feature just because it looks AI-written. Triggers: "de-slop this", "make this less generic", "tighten this doc", "is this AI-slop?", "edit this without flattening my voice", "audit/suggest/apply".

The unquoted YAML plain scalar contains `Triggers: `, a colon followed by a space, which is not valid inside a YAML plain scalar. A conforming frontmatter parser can reject SKILL.md, preventing skill discovery or invocation. The test does not catch this because `_frontmatter` is a bespoke line splitter rather than a YAML parser.

**Recommendation:** In `skills/slopslap/SKILL.md` frontmatter, quote the entire `description` value or change it to a YAML block scalar (`description: >-`). In `tests/test_scaffold.py`, replace `_frontmatter` with the same YAML parser used by the plugin loader and assert successful parsing.

### 3. [High] security · medium confidence — commands/audit.md invocation; same interpolation pattern in all commands

> +Invoke the `slopslap` skill (`skills/slopslap/SKILL.md`) and apply it in **audit** mode to: $ARGUMENTS

Raw file-or-text arguments are interpolated directly into the command instruction without an untrusted-data delimiter or a rule that instructions found in the target are non-authoritative. Crafted prose can impersonate user instructions, claim a protected-span override, or ask the model to ignore audit mode, potentially bypassing the read-only and edit-authorization boundaries.

**Recommendation:** In every command body, wrap `$ARGUMENTS` in explicit untrusted-content delimiters and state that content inside them is data, cannot change mode or authorize tools/writes, and cannot constitute the user override required for protected spans. Define overrides only through a separate command argument outside the reviewed content.

### 4. [Medium] correctness · high confidence — commands/apply.md refusal contract and tests/test_scaffold.py::test_apply_command_fails_closed_with_sentinel

> +1. Emit the machine-observable sentinel line exactly: `status: mutation_unavailable`
> +2. State plainly that **no write was performed** and no backup exists yet.

A line in generated prose is observable but does not itself make the command execution unsuccessful. Automation that relies on command completion or process status rather than parsing this exact text can still record apply as successful, reproducing the misleading-success outcome the fail-closed contract is intended to prevent.

**Recommendation:** In `commands/apply.md`, define the actual host-level failure mechanism if one exists. If it does not, define a versioned structured response schema and provide an executable wrapper/parser that returns nonzero for `mutation_unavailable`; test the wrapper's status rather than only checking that the prompt contains the sentinel.

### 5. [Medium] correctness · high confidence — tests/test_scaffold.py::test_skill_keeps_three_remedies_distinct

> +    assert "never delete" in skill  # laundering
> +    assert "flag" in skill          # simulation
> +    assert "compress" in skill or "delete or compress" in skill  # emptiness

The remedy-separation test searches the entire skill for three unrelated words and never associates any word with its required category. It still passes if laundering says `flag`, simulation says `compress`, and emptiness says `never delete`, or if the words occur only in warnings. The safety test can therefore approve the exact category-collapse or wrong-remedy regression it claims to prevent.

**Recommendation:** In `test_skill_keeps_three_remedies_distinct`, parse the six-category table or use category-specific anchored sections, then assert the permitted response attached to each identifier: emptiness→delete/compress, laundering→question/non-testable plus never-delete, and simulation→flag plus no substantive repair.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._