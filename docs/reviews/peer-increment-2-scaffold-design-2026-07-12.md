# Peer Consult — increment-2-scaffold-design.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Build the scaffold around a compact, self-sufficient judgment protocol. SKILL.md should be executable without loading references: begin with “Repair only demonstrated editorial harm; do not punish prose for matching a stylistic tell.” Then define edit authorization, the five-step loop, protected-span default-deny behavior, three distinct harm categories, category-specific remedies, invariant verification, output modes, rating semantics, and behavioral limits. References should elaborate rather than qualify this core: examples, genre-specific heuristics, longer tables, and engine-selection details. Commands should only bind a mode and arguments to the same protocol. Audit is read-only; suggest returns diagnoses and focused proposed changes; apply refuses mutation until backup gating exists, while optionally directing the user to suggest for a non-mutating preview. Voiceprint remains visible as a deferred identity-bearing stub. Add structural validation plus a small judgment-contract test that needs neither scanner nor ledger.

## Key decisions

- Make demonstrated editorial harm the sole edit-authorization predicate. Scanner signals, stylistic tells, genre profiles, ratings, and future voiceprints may support investigation but can never independently authorize a rewrite.
- Keep the always-on core in SKILL.md: anti-slap opening instruction; keystone authorization rule; protect → diagnose → establish invariants → rewrite → verify loop; protected-span default deny; separate emptiness, laundering, and simulation categories; permitted response per category; preservation invariants; audit/suggest/apply semantics; two rating definitions; maximum three diagnoses per 500 words; idempotence; and prohibitions against homogenizing voice, resolving uncertainty, inventing support, or changing requirements.
- Put only expandable material in references: tell-taxonomy.md owns richer indicators and before/after examples; genre-profiles.md owns profile detail and asymmetric-failure guidance; engine.md owns model-selection policy and the conditional Fable 5 path. No reference may introduce a safety rule required for correct baseline behavior.
- Represent each diagnosis as a typed record: category, exact evidence span, demonstrated harm, reader or requirement impact, confidence rating, intervention rating, and permitted action. Requiring one category per diagnosis prevents an undifferentiated “AI-slop” bucket; multiple harms require multiple records, even when they share evidence.
- Define category-specific interventions: emptiness permits removal or concretization only when substance is absent; laundering permits restoring attribution, uncertainty, provenance, or scope; simulation permits removing unsupported claims of experience, evidence, consensus, or completed work. A generic polish operation is not a valid remedy.
- Make apply fail closed before backup support exists. It should clearly state that mutation is unavailable in MVP, perform no implicit audit, and offer an explicit `/slopslap:suggest $ARGUMENTS` next action. Silent fallback would violate the requested mode and could mislead automation about whether a mutation occurred.
- Ship voiceprint.md because the future hook is part of the plugin’s conceptual interface. Declare show, reset, export, and delete as reserved operations, but return a consistent “not implemented in MVP” result and perform no storage or inference.
- Use suggest as the default mode, but require every suggested edit to include its diagnosis and invariant check. Audit emits no replacement prose; apply emits no changes until backup gating exists.
- Add a cheap behavioral contract alongside structural checks: feed a neutral passage containing stylistic tells but no demonstrated harm and assert an audit-shaped result with zero diagnoses and no rewrite. Also validate that three synthetic harms remain three separately typed diagnoses. These are prompt-contract smoke tests, not scanner or ledger evaluations.
- Keep manifest metadata minimal and convention-compatible: version 0.1.0, name, description, and author only where auto-discovery supplies skills and commands.

## Risks

- Repeating the keystone rule in every command can drift from SKILL.md. Commands should use one canonical sentence verbatim and avoid duplicating the wider policy.
- A model may treat category labels as detection shortcuts. The typed diagnosis must require evidence of harm and impact before classification or intervention.
- A hard-refusing apply command may surprise users, but audit fallback is more dangerous because it falsely appears to honor an explicit mutation request.
- Behavioral smoke tests against unconstrained model text can be flaky. Test semantic properties or a narrowly defined output schema rather than exact prose.
- Progressive disclosure can fail if references contain hidden normative exceptions. Structural tests should assert that required safety concepts appear in SKILL.md, not merely somewhere in the package.
- The diagnosis cap may suppress important findings in unusually dense harmful text. Define it as prioritization of the highest-cost harms, with overflow summarized but not expanded into extra edits.
- Engine language such as “best available” may become stale or non-deterministic. Treat it as runtime selection policy and expose the selected engine in output metadata when execution machinery exists.
- A visible voiceprint stub could imply persistence already exists. Every operation must state that no voiceprint data is stored, read, modified, or deleted in MVP.

## Sketch

.claude-plugin/plugin.json
  version: 0.1.0
  minimal metadata; rely on auto-discovery

skills/slopslap/SKILL.md
  1. Anti-slap instruction
  2. Keystone authorization rule
  3. Protected spans and preservation invariants
  4. Five-step judgment loop
  5. Typed diagnosis contract
     - one of: emptiness | laundering | simulation
     - evidence span
     - demonstrated harm and impact
     - confidence rating
     - intervention rating
     - permitted response
  6. Mode contracts
     - audit: diagnoses only
     - suggest: diagnoses + focused diff + invariant report
     - apply: backup-gated; unavailable in MVP
  7. Behavioral limits and prohibitions
  8. Optional reference-loading map

commands/audit.md
  frontmatter: description, argument-hint
  bind mode=audit; target=$ARGUMENTS; restate keystone

commands/suggest.md
  frontmatter: description, argument-hint
  bind mode=suggest; target=$ARGUMENTS; restate keystone

commands/apply.md
  frontmatter: description, argument-hint
  bind mode=apply; target=$ARGUMENTS
  refuse mutation because backup gate is unavailable
  point explicitly to suggest; do not silently execute it

commands/voiceprint.md
  frontmatter: description, argument-hint
  parse $ARGUMENTS as show|reset|export|delete
  return not-implemented status; guarantee no data operation

references/tell-taxonomy.md
  separate category tables, evidence tests, permitted remedies, before/after examples

references/genre-profiles.md
  profiles, preservation priorities, asymmetric-failure rule

references/engine.md
  best-available Claude at high effort by default
  Fable 5 only when an API capability is actually available

Tests
  - required paths and parseable frontmatter
  - valid manifest and exact version
  - always-on SKILL contains required safety concepts
  - neutral-tell golden: zero authorized edits
  - category-separation golden: three harms remain three typed diagnoses

---
_Peer proposal (report-only). Synthesize at your discretion._
