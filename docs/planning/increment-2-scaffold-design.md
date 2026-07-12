# Increment 2 design brief — #scaffold (plugin manifest + SKILL + commands + references)

Context: slopslap is a Claude Code **plugin** that repairs high-editorial-cost prose while preserving
meaning/requirements/uncertainty/voice (NOT an AI detector). Increment 1 shipped the acceptance
contract (fixtures + two-stage hard-gate runner). This increment scaffolds the plugin the judgment
runs inside. Spec: `docs/planning/2026-07-12-slopslap-reconciled-spec.md` (§Packaging, §Keystone rule,
§Loop, §Taxonomy, §Ratings, §Protected spans, §Output modes, §Genre, §Behavioral limits, §Engine,
§Layout). This is the judgment layer; it emits NO code — it drives the model + the increment-1/scanner
machinery.

## Deliverables
- `.claude-plugin/plugin.json` — manifest, **version 0.1.0** (name/description/author; skills + commands
  auto-discovered, matching the local rawgentic/caveman plugin convention).
- `skills/slopslap/SKILL.md` — THE judgment: loop (protect → diagnose → establish invariants → rewrite
  → verify) + keystone rule + prohibitions + the 3 modes + taxonomy (categories SEPARATE) + two ratings
  + behavioral limits. **First instruction counters the name's "slap":** *"Repair only demonstrated
  editorial harm; do not punish prose for matching a stylistic tell."*
- `commands/` — `audit.md`, `suggest.md`, `apply.md` (the 3 modes) + `voiceprint.md` (v2-deferred stub:
  show/reset/export/delete declared, clearly "not implemented in MVP"). Frontmatter `description` +
  `argument-hint`, body uses `$ARGUMENTS`.
- `references/tell-taxonomy.md` (the 3 categories + before/after, kept separate), `references/genre-profiles.md`
  (the profiles + asymmetric-failure rule), `references/engine.md` (default best-available Claude at high
  effort; Fable 5 = bonus-if-API).

## Proposed design
- **Progressive disclosure.** SKILL.md (always loaded) carries the load-bearing judgment that must never
  be skipped: keystone rule, the loop, the SEPARATE tell-categories + permitted responses, the two
  ratings, protected-span default-deny, behavioral limits (≤3 diagnoses/500w; idempotence; the
  anti-slap first instruction). The `references/*.md` (read on demand) carry the long tables / before-
  after examples / genre profile details, so SKILL.md stays scannable.
- **Commands are thin mode-selectors** that invoke the SKILL judgment with a fixed mode + wire the
  increment-1 acceptance machinery: `audit` = read-only diagnosis; `suggest` (default) = diagnosis +
  focused diff + invariant-check via the verification package; `apply` = deferred to #apply-backup
  (present but MUST refuse to mutate until backup gating exists — points at the backlog).
- **Keystone everywhere:** every command + the SKILL restate that the scanner/genre/voiceprint NEVER
  authorize an edit — authorization is demonstrated editorial harm only.
- **Structural-load test only** this increment (manifest valid JSON, skill/command frontmatter parse,
  required files exist, version==0.1.0). No behavioral eval yet (that's #eval-run once the scanner +
  ledger land).

## Questions for the peer
1. What belongs in SKILL.md vs `references/` so the model reliably honors the anti-over-editing
   discipline WITHOUT the reference being loaded? (i.e., what is the irreducible always-on core?)
2. How should `apply.md` behave in MVP before #apply-backup exists — hard-refuse with a pointer, or
   audit-only fallback? (Spec: apply is backup-gated; the backup machinery isn't built yet.)
3. Voiceprint commands are v2-deferred. Stub-that-declares-deferred vs omit-until-v2? (Spec says the
   plugin exists BECAUSE of the future voiceprint hook, so the commands are part of the identity.)
4. Any framing that measurably reduces the top failure — collapsing emptiness / laundering /
   simulation into one "AI-slop" bucket — beyond just listing them separately?
5. Is a structural-load test the right scope-floor here, or is there a cheap behavioral guard worth
   adding now (e.g. a golden "audit output shape" contract) without the scanner/ledger?

## Folded decisions — post peer-consult (gpt-5.6-sol, `docs/reviews/peer-increment-2-scaffold-design-2026-07-12.md`)

1. **Typed diagnosis contract** (the anti-bucket guard). Every diagnosis is a typed record:
   `{category (exactly one of: emptiness | laundering | simulation | lexical_structural | voice_discontinuity | epistemic_distortion), evidence_span, demonstrated_harm + reader/requirement impact, editorial_harm rating, diagnosis_confidence rating, permitted_response}`. One category per record; when one span carries two harms it becomes two records. Classification is only allowed AFTER evidence of harm+impact — a category label is never a detection shortcut.
2. **Category-specific interventions, never generic polish:** emptiness → delete/concretize *only if no intent lost*; laundering → restore attribution/uncertainty/provenance/scope, or convert to a question — **never delete** (load-bearing intent); simulation → flag missing support, **do not repair substantively**; lexical/structural → act only when redundant AND genre permits; voice/epistemic → per spec taxonomy.
3. **apply fails closed in MVP:** states mutation is unavailable (backup gate not built), performs **no implicit audit**, points explicitly to `/slopslap:suggest $ARGUMENTS`. No silent fallback (would mislead automation about whether a mutation happened).
4. **voiceprint.md** ships as a deferred identity-bearing stub: `show|reset|export|delete` reserved, returns a consistent "not implemented in MVP" result, and **guarantees no voiceprint data is stored, read, modified, or deleted**.
5. **One canonical keystone sentence, verbatim** in each command (no wider-policy duplication that could drift from SKILL.md): *"Edit authorization comes only from demonstrated editorial harm; the scanner, genre, ratings, and voiceprint never authorize an edit."*
6. **Progressive disclosure with a safety floor:** SKILL.md (always-on) holds the irreducible core — anti-slap opener, keystone, protected-span default-deny + preservation invariants, the 5-step loop, the typed-diagnosis contract + separate categories + per-category remedies, the two ratings, mode contracts, behavioral limits/prohibitions. `references/*.md` ELABORATE only (examples, tables, genre detail, engine policy) and may **never introduce a safety rule**. The structural test asserts the required safety concepts appear **in SKILL.md itself**, not merely somewhere in the package.
7. **Diagnosis cap = prioritization** of the highest-cost harms (≤3/500w for presentation), overflow **summarized, never expanded into extra edits**; never limits invariant extraction/verification/hard-failure reporting.
8. **Scope floor = structural + safety-concept-presence tests** (manifest valid + version 0.1.0; skill/command frontmatter parse; required files exist; SKILL.md contains keystone + anti-slap + the three separate categories + apply-is-backup-gated). **Live behavioral goldens** (neutral-tell passage ⇒ zero diagnoses; three harms ⇒ three typed records) are deferred to **#eval-run**, where the model harness exists — the increment-1 clean-document controls already encode clean-prose abstention at the eval layer.
9. **plugin.json minimal + convention-compatible** (name/description/author/version 0.1.0; skills + commands auto-discovered).

## Post-review resolutions — WF5 on the scaffold design (`docs/reviews/increment-2-scaffold-design-md-2026-07-12.md`, 0 Crit / 2 High / 3 Med, all confirmed)

- **R1 (H1) — full safety-concept assertion matrix.** The structural test asserts EVERY item of the
  irreducible core is present in `skills/slopslap/SKILL.md`, keyed on stable `[[anchor]]` markers embedded
  in the skill (anti-slap opener, keystone, protected-span default-deny, preservation invariants, the
  5-step loop, the typed-diagnosis record fields, per-category remedies, the two ratings, the three mode
  contracts, the diagnosis cap, the prohibitions) — not loose substring matching. It also asserts the
  canonical keystone sentence appears verbatim in each command, and the apply/voiceprint refusal contracts.
- **R2 (H2) — explicit skill invocation, no implicit-load assumption.** Claude Code does NOT auto-load a
  skill's SKILL.md for a slash command. So every command body **explicitly** instructs: "Invoke the
  `slopslap` skill (`skills/slopslap/SKILL.md`) and apply it in `<mode>` mode," AND restates the canonical
  keystone sentence itself as a floor if the skill somehow isn't loaded. A structural test asserts every
  command references `skills/slopslap/SKILL.md`.
- **R3 (M3) — machine-observable apply failure.** `apply.md` emits a structured sentinel line
  `status: mutation_unavailable` and states no write occurred; the test asserts the sentinel is present and
  that apply performs no implicit audit.
- **R4 (M4) — engine selection is ADVISORY, not enforceable.** A plugin cannot force the host model/effort;
  the session owns them. `engine.md` states this explicitly: slopslap runs on whatever Claude tier the
  session provides; the tier/effort guidance is advisory; Fable 5 is a bonus only if API access exists.
- **R5 (M5) — six categories, three-separate rule.** The diagnosis taxonomy has **six** category
  identifiers: `emptiness`, `laundering`, `simulation`, `lexical_structural`, `voice_discontinuity`,
  `epistemic_distortion`. Three of them — emptiness/laundering/simulation — carry DISTINCT remedies and
  their collapse into one bucket is the top failure. Tests enumerate all six identifiers and assert the
  three distinct remedies. All "3 categories" wording is corrected to this.

## Post-diff-review resolutions — WF5 on the built diff (`docs/reviews/increment-2-diff-2026-07-12.md`, 0 Crit / 3 High / 2 Med, all confirmed + fixed)

- **H1** — `plugin.json` over-claimed a shipped scanner + byte-exact verifier at v0.1.0. Description now
  states v0.1.0 ships the judgment skill + commands only; invariant checks are **model-reported** in
  suggest mode until the deterministic verifier is wired (SKILL suggest-mode wording matched).
- **H2 (real load bug)** — SKILL.md `description` was an invalid YAML plain scalar (`Triggers: `
  colon-space) that a conforming loader rejects; rephrased to valid YAML. The scaffold test now parses
  ALL frontmatter with a real YAML loader (`yaml.safe_load`), so this can't regress silently.
- **H3** — raw `$ARGUMENTS` interpolation was a prompt-injection surface. Every command now wraps the
  target in untrusted-data delimiters and states the content is DATA — it cannot change the mode,
  authorize a tool/write, or serve as the protected-span override (overrides come only from the user's
  request outside the content). Added `anchor:untrusted-input` to SKILL.md + a test.
- **M4** — the apply sentinel is prose, and a slash command has no host exit code; apply.md now requires
  the sentinel `status: mutation_unavailable` as the FIRST output line and names the limitation, so
  automation gates by parsing position.
- **M5** — the remedy-separation test searched the whole skill; it now binds each remedy to ITS
  category table row (emptiness→delete/compress, laundering→question+never-delete, simulation→flag) and
  asserts the wrong remedy is absent from the wrong row.

## Out of scope
Scanner (#scanner), ledger/verify (#ledger-verify), apply/backup (#apply-backup), the voiceprint hook
+ learning (v2). No LIVE behavioral eval here (deferred to #eval-run).
