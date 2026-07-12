# slopslap — reconciled design spec (r1+r2 consult + Claude research + independent voiceprint pass)

A Claude Code **plugin** (not a bare skill — see Packaging) that repairs prose carrying
**high editorial cost** (genericness, unsupported claims, synthetic cadence, obscured
responsibility, voice discontinuity) while preserving meaning, technical accuracy,
requirements, uncertainty, and intentional voice. NOT an AI-authorship detector. Must
beat the `humanizer` skill by *not treating stylistic features as contaminants*.

## Revisions — owner review round 3 (2026-07-12)
Three review findings folded in before the cross-model WF5 pass:
1. **Per-hunk selective rollback + byte-offset edit-map machinery → IN MVP** (was
   deferred). The edit map was already MVP-required for multi-hunk verification; shipping
   the selective-revert that reuses it is now MVP scope, not a follow-on.
2. **Scanner Markdown dependency resolved via gpt-soul (gpt-5.6-sol) peer consult** — see
   `docs/reviews/peer-2026-07-12-scanner-dependency-consult-2026-07-12.md` and the
   Scanner-dependency subsection below. Verdict: capability-gate by format; vendor the
   pinned parser (never runtime-pip, never a home-grown stdlib subset); fail loud when
   absent.
3. **Build order is fixtures-first** — the 3 canonical eval fixtures are the red test /
   acceptance contract and get pinned BEFORE scaffolding (see Build order below).

**WF5 cross-model review (2026-07-12, Codex gpt-5.6-sol, report
`docs/reviews/2026-07-12-slopslap-reconciled-spec-md-2026-07-12.md`): 8 findings (0 Critical
/ 4 High / 4 Medium), all confirmed vs cited text, ALL FOLDED** — eval decision rule,
valid-JSON capability payload, byte-offset ledger schema (was line-based), backup
containment (was falsely "git-ignored"), explicit `--format` contract, verification
isolation contract, post-tokenization bare-URL rule, cadence-params routed to
`scanner-metrics.md`. No Criticals; the spine (keystone rule, separate tell-categories,
backup-gated apply) passed intact. Tags `(WF5 #n)` mark each folded fix inline.

## Packaging: plugin, not skill (owner decision 2026-07-12)
Reframed from a lone skill to a plugin because the pieces belong together and a bare
skill can't hold them: the v2 **voiceprint capture needs a UserPromptSubmit hook**
(hooks live in plugins, not skills — this is the deciding constraint); the
audit/suggest/apply modes + voiceprint management (show/disable/reset/export/delete) are
natural **slash commands**; it bundles a **script** (scan_prose.py); and a plugin is
installable/shareable. The core judgment still lives in one `SKILL.md` inside the plugin.

## Engine (owner decision 2026-07-12): best available Claude; Fable = bonus, not required
slopslap runs on whatever Claude tier the session provides. **Default = Opus 4.8 (or the
session model) at high reasoning effort** for the entangled-constraint diagnosis/verify
AND the rewrite. **Claude Fable 5 is a BONUS for the rewrite pass IF API access is
available — never a requirement** (Fable is going API-only, so it can't be assumed
present via the normal Claude Code path; treating it as required would strand
subscription users). Rationale from research: Claude leads editing with a "light hand"
(the minimal-edit rule) and low re-slop; Fable tops prose/low-slop boards but its
availability is conditional. The eval loop decides empirically across the available
tiers (Opus 4.8 / Sonnet 5, + Fable 5 only when API access exists).

## Keystone rule (governs everything)
**Edit authorization comes from demonstrated editorial harm. Invariants constrain
meaning; genre constrains function; the voiceprint only chooses among safe phrasings.**
Diagnosis authorizes SCOPE; genre and voiceprint authorize REALIZATION; neither may
independently authorize an edit or expand its boundary. This is the anti-normalization
guard — "make it sound like me" can never become whole-document rewriting.

## Loop
protect → diagnose → establish invariants → rewrite (minimal, passage-local) → verify.
Invariant ledger is append-only during rewrite (new invariants may be added, never
weakened/removed).

## Taxonomy (clustered confidence; no single tell dispositive) — keep categories SEPARATE
| Condition | Permitted response |
|---|---|
| Semantic emptiness (words add nothing/repeat context) | delete or compress — only if no intent lost |
| Specification-laundering (evaluative language posing as a requirement) | convert to a question or label non-testable — do NOT delete (it's load-bearing intent) |
| Content-simulation (implies absent evidence/examples/analysis) | flag missing support — do NOT repair substantively |
| Lexical / structural / rhetorical / formatting tells | candidates only; safe to act on only when redundant AND genre permits |
| Voice-discontinuity | evidence ONLY when the doc is expected to have one voice (not interviews/RFCs/quotes/changelogs/marketing sections) |
| Epistemic distortion (false confidence, hedge-piles hiding uncertainty, passive hiding the actor) | repair without inventing an actor or deleting necessary hedging |
Collapsing emptiness / laundering / simulation is the top failure — they need different remedies.

## Ratings: two separate axes, never a single "AI %"
- **editorial-harm**: low / med / high
- **diagnosis-confidence**: low / med / high

## Protected spans (default-DENY edits; explicit override only)
code fences + inline code, explicit blockquotes, URLs/citations/link destinations,
generated data/output, API identifiers/defined terms, legal clauses (→ audit-only for
those spans even in apply mode). Inline "quote marks" = `quote_candidate`, elevated by
context/user, not auto-protected. Protected ≠ preservation-sensitive: a number in prose
isn't an immutable span but IS an invariant.

## Invariant ledger (machine-readable JSON, shared by rewrite + verify)
Closed `kind` enum: literal · number_or_quantity · normative_statement · condition ·
exception · causal_claim · attribution · defined_term · cross_reference ·
unsupported_intent · missing_support · intentional_repetition · protected_span.
Closed `preservation` enum: byte_exact · lexically_exact · semantic_exact ·
relationship_exact · surface_only (= preserve that it's UNRESOLVED, not the vague words).
Each entry: id, kind, source{start_byte,end_byte,text_hash} — **byte offsets are canonical
(WF5 #3); any start_line/end_line are DERIVED display-only fields, never used for matching
or rollback** — the extracted content (subject/predicate/object/modality/qualifiers as
applicable), preservation, confidence. Plus protected_spans[] with byte offsets + sha256.
**Canonical coordinates (round-3 fix):** ALL positions — ledger sources, protected-span
offsets, authorized edit ranges, post-edit proposition matching — use **original-byte
offsets** as the single canonical system, and the rewrite carries an **original→revision
edit map**. Without this, multi-hunk verification misattributes passages that shifted
when an earlier hunk changed length.

## Verification — 3 layers, NOT one self-check; rewriter never verifies itself
**Isolation contract (WF5 #7):** the adversarial semantic pass (layer 3) runs in a FRESH
context that never saw the rewriter's chain-of-thought or justifications — it receives only
the original text, the revision, and the invariant ledger. It MAY use a different model;
at minimum it is a separate invocation, never the rewrite turn continued. Layer 1
(deterministic) is code, not a model, and OWNS the hard accept/reject decision — no model
output can override a deterministic hard failure.
1. **Deterministic integrity:** protected-span hashes; URLs/citations/identifiers/
   numbers/units/dates/defined-terms preserved; normative modal inventory by source
   region; balanced fences; no new placeholders; edits only within authorized ranges.
2. **Extraction-then-compare:** re-extract propositions from the revision into the same
   ledger shape; match by id else subject/predicate/object + source neighborhood.
3. **Adversarial semantic check (separate pass):** dropped/weakened claims? unsupported
   new claims? changed conditions/exceptions/actors/responsibility? unresolved intent
   turned into an asserted requirement?
**Decision rule:** hard failure (protected-span mutation, changed number/unit/identifier/
modality, invented claim, removed condition/exception) → auto-reject the edit. Ambiguous
semantic → don't apply, surface original+proposal+concern. Soft style → keep safer
version, never escalate an edit to satisfy style. Ledger uncertainty (source ambiguous)
→ ask, don't resolve by rewriting. suggest mode: mark proposal `BLOCKED`. apply mode:
revert only the failing hunk (or the containing passage if hunks are inseparable).

## Scanner `scan_prose.py` — measures, never verdicts
Uses a CommonMark parser (`markdown-it-py`) for Markdown; excludes fenced/indented code,
HTML blocks, blockquotes (default), link destinations (keeps visible text), autolinks/
bare URLs, inline code; retains headings/list text with structural type. Plain-text
scanner ships first; Markdown requires the parser (explicit limitation, no silent
approximate fallback). Emits per metric: eligible_units, count, rate, locations,
soft_flag, threshold_profile. Metrics: sentence-word-count distribution (min/p10/p25/
median/p75/p90/max/mean/sd); sentence_length_dispersion (IQR/median, CoV when mean≠0,
median adjacent-diff) — NOT called "burstiness"; repeated openers (normalize first 1/2/3
lexical tokens, lowercase, strip list punctuation, keep negation, rolling 8-sentence
window, ignore <2-token openers); transition clusters (rate per 1k eligible words);
rule-of-three candidates (heuristic); negative-parallelism regex (occurrences only);
em-dash/semicolon rates per 1k; heading density + heading:paragraph ratio; bold-label
density; passive-looking (be/get + participle, low-conf); vague-attribution clusters;
stock lexical clusters (named cluster + phrase, not isolated common words); paragraph
cadence similarity (10-feature clipped vector → weighted Manhattan → similarity=1−dist;
flag only if both paras eligible AND similarity>0.88 AND ≥1 other repetition signal);
paragraph sentence-count runs (≥3 adjacent equal); closing-pattern repetition. Thresholds
are versioned triage aids (`purpose: candidate_selection_only`) — no cross-doc percentiles
in MVP (needs a genre reference corpus). **Every metric's exact parameters — the cadence-
similarity 10 features / clip-bounds / Manhattan weights / "other repetition signal" set,
opener normalization, stock-cluster lists — are pinned in `references/scanner-metrics.md`
with fixtures BEFORE that metric ships (WF5 #6); the formulas above are structure, not the
full parameterization.**

### Scanner dependency — capability-gate + vendor, never runtime-pip (gpt-soul consult 2026-07-12)
Claude Code plugins have no managed venv, so a bare `import markdown_it` would fail for most
users. Resolution (peer consult, `docs/reviews/peer-2026-07-12-scanner-dependency-consult-2026-07-12.md`):
- **Capability-gate by input format.** The plain-text path is stdlib-only and always
  available. Markdown is EITHER parsed by a conforming CommonMark parser OR reported
  unavailable — Markdown input is NEVER routed through the plain-text path (that would be
  the forbidden silent-approximate fallback).
- **Format is explicit, never guessed (WF5 #5).** The scanner takes a mandatory
  `--format text|markdown` — no extension/content sniffing that could mis-route. Absent or
  ambiguous input (extensionless, stdin without `--format`) FAILS with a `format_required`
  status; it never silently falls back to the plain-text path.
- **Machine-readable capability contract (valid JSON, WF5 #2).** On an absent/incompatible
  parser the scanner emits valid JSON
  `{"status":"capability_unavailable","format":"markdown","capability":"markdown_commonmark","metrics":null}`
  + a stderr notice + a dedicated advisory-skip **exit code 10** (reserving `0`=ok,
  `1`=malformed-input/scanner-defect; `format_required` is its own distinct non-zero code)
  the caller converts into "skip these metrics". Never zero-valued or partial metrics that
  could read as authoritative.
- **Vendor the parser for real Markdown support** — pinned, tested `markdown-it-py` + its
  transitive runtime deps (`mdurl`) under a plugin-private `vendor/python/`, with licenses
  (`THIRD_PARTY_LICENSES/`), provenance (upstream version / source / hashes / update
  procedure), and CommonMark fixture tests (fenced/indented code, HTML blocks, blockquotes,
  links, autolinks, bare URLs, inline code, headings, lists) run from the ACTUAL installed
  plugin layout on Linux/macOS/Windows. Version-gate the import so an environment-installed
  copy can't silently change tokenization.
- **Rejected:** runtime pip-install-on-first-use (depends on network / writable env / index
  / mutating the user's Python); a home-grown stdlib CommonMark subset (the exclusion rules
  cross block+inline boundaries — a "subset" just becomes an approximate parser under
  another name, recreating the silent-wrong-region risk). A manual system `pip install`
  stays an advanced/dev-only option, version-validated, never the normal path.
- **Extraction still needs its own tests:** correct token parsing ≠ correct visible-prose
  regions; keep extraction fixtures. **Bare-URL exclusion is a post-tokenization rule
  (WF5 #8)** — NOT a dependency on a parser linkify extension: after tokenizing, a
  deterministic URL matcher excludes bare URLs from eligible prose, bound to explicit
  extraction fixtures so counts/locations stay reproducible across parser versions.
- **slopslap-specific MVP call (derived — flagged for WF5):** because slopslap's primary
  inputs — specs, PRDs, essays — ARE Markdown, Markdown IS a first-release requirement, so
  the vendored parser is pulled INTO MVP (gpt-soul deferred vendoring only "if Markdown
  support is not required for the first release" — here it is). The capability contract is
  the fail-loud guard if the vendored import breaks on some platform; the plain-text path
  remains the `format:text` scanner.

## Genre — hierarchical / per-region, not whole-doc
document_genre{primary,confidence} + regions[]{lines,genre,confidence,evidence}.
Classification precedence: explicit user declaration > file/repo context > structural
markers > content inference. Segment at headings/blocks, merge adjacent same-profile.
Profiles: general-prose · technical-doc · spec (repetition = correctness infra, preserve
normative vocab/parallelism/enumerations) · legal (flag, audit-only) · PRD (challenge
adjectives-as-requirements) · marketing (evocation allowed; unsupported superiority not) ·
personal (voice preservation weighted high). **Asymmetric failure: low confidence →
use the most preservation-heavy applicable profile** (stiffening marketing < changing a
spec). Genre modifies diagnosis/rewrite constraints; it never decides prose is "bad."

## Output modes
- **audit** — read-only diagnosis (passage, harm, confidence, class, why, repair kind,
  missing evidence). No edits.
- **suggest (default)** — diagnosis + focused diff + questions ONLY for facts that block
  a specific proposed repair + invariant-check result. Placeholders (`[DEFINE X]`)
  proposed OUTSIDE the document unless approved (inserting them can make an invalid doc
  look complete).
- **apply (v1, backup-gated)** — in-place, writable source only, on explicit request.
  **Takes a mandatory pre-mutation backup FIRST** — by default a timestamped copy in a
  user-local backup dir OUTSIDE the repo (the plugin's state dir), so original prose can't
  be swept into a commit. If a project overrides to an in-tree `.slopslap/backups/`, the
  implementation MUST create AND verify an effective ignore rule first, detect an
  already-tracked backup path, and **fail closed (no backup ⇒ no mutation)** if containment
  can't be guaranteed (WF5 #4 — an in-tree dir is NOT git-ignored merely by living in the
  tree). Prints the restore path + a one-line restore command, keeps the last N. The backup is the universal safety net
  (works for git AND non-git AND dirty files), so a verify-miss is always recoverable.
  Approval/placeholders still required for deep repairs needing absent facts. **Per-hunk
  SELECTIVE rollback** (revert one failing hunk, keep the rest) is **IN MVP** (owner
  decision 2026-07-12) — it reuses the byte-offset + edit-map machinery the MVP already
  builds for multi-hunk verification (see Invariant ledger §canonical coordinates), so the
  marginal cost is the revert logic, not new infrastructure. It layers ON TOP of the
  backup, which is still the universal safety net (the backup covers safety even if
  selective rollback itself has a bug).

## Behavioral limits (anti-over-editing)
- ≤3 high-value diagnoses per 500 words unless exhaustive audit requested. (Caps
  candidate PRESENTATION only — never limits invariant extraction, verification, or
  hard-failure reporting.)
- Once a passage passes invariants and has no high-harm diagnosis, leave it alone on
  subsequent runs (idempotence).
- First instruction, countering the name's "slap" priming: *"Repair only demonstrated
  editorial harm; do not punish prose for matching a stylistic tell."*

## Voiceprint (v2 — deferred; the DEFENSIVE reframe is the headline)
**Primary purpose = defensive:** a per-author whitelist of genuine habits (their
em-dashes, fragments, pet words) so slopslap doesn't strip real voice AS IF it were
AI-tell — the thing humanizer can't do. Secondarily biases diction among *already-safe*
phrasings. Never generative, never manufactures voice.
- **Source honesty:** prompts are weak/interaction-level (teach diction/directness/
  hedging/profanity-tolerance) and BLIND to long-form rhythm; full of mode-artifacts
  (typos/lowercase) that must never become prose style. Evidence weights: user long-form
  1.0 · user edits to a rewrite 0.9 · rewrite accepted-as-voice 0.6 · prompt instruction
  shell 0.35 · unchallenged model output 0.0 · pasted/quoted 0.0. Ingest only the
  instruction shell (strip quotes/paste/code/logs/domain-nouns), classified `interaction`.
- **Descriptor:** human-readable YAML — observable features + confidence + source +
  transfer limit + negative_constraints; NO personality labels ("witty"). Zones:
  register-invariant (apply) / prompt-mode-only (ignore for prose) / UNKNOWN (never
  guessed) / pinned (user-asserted, no decay). Store derived counts + short approved
  examples, NOT raw prompts.
- **Update:** buffered, not per-prompt — propose an update at 5 new eligible samples OR
  1000 tokens; weighted exponential update; time-decay the evidence weight only
  (180-day half-life), not the stored preference; manual fields don't decay; cap one
  session ≤20% of effective evidence.
- **Authority order:** protected spans > invariant ledger + no-fabrication > genre >
  **user's current explicit instruction** > voiceprint > neutral default. (Current
  instruction beats history: "make this formal" overrides a casual profile.) Voiceprint
  consulted ONLY after a passage has an independently-justified edit; selects among
  meaning-equivalent realizations; never expands the edit boundary.
- **Thin-corpus gates:** <10 samples/1000 tokens → show tentative observations only, no
  auto-apply. Prompt-shell evidence, no long-form → ≤25% influence (register/contraction/
  punctuation/directness only). ≥3 long-form or substantial edited-rewrites in genre →
  ≤60%. Never 100% (genre + local-document continuity always active).
- **Overfitting guards:** trait must recur across ≥3 sessions; never inject a tic just
  because frequent; never copy catchphrases; never add profanity/fragments/command-syntax
  to long-form; on voiceprint-vs-local-document conflict prefer local continuity;
  anti-caricature check ("which features exaggerated beyond observed range?"); idempotence
  (repeat runs must not amplify contractions/fragments/dashes/directness).
- **Consent/control:** opt-in; local only; commands show/disable/reset/export/delete;
  never learn while handling sensitive material; explicit profile path if per-user
  storage isn't reliably identifiable.
- **Capture:** the SKILL can't capture prompts itself — needs a companion opt-in
  UserPromptSubmit hook (rawgentic's mempalace-recall pattern) that appends derived
  observations (not raw prompts) to the buffer.

## MVP cut (ship first — NOT audit-only; audit proves naming, not safe repair)
audit + suggest modes · passage-local edits · protected-span extraction · minimal
invariant ledger · deterministic + separate-semantic verification · ~8 reliable scanner
metrics (sentence-length distribution, repeated openers, transition clusters, punctuation
rates, paragraph sentence-count runs, vague attribution, bold-label density, stock lexical
clusters) · 3 genre profiles (general, PRD/spec, personal) · 3 hard evals + clean-document
controls · **apply mode gated by a mandatory pre-mutation backup** (universal safety net —
git-independent) · **byte-offset edit-map + per-hunk SELECTIVE rollback** (revert one
failing hunk, keep the rest — owner decision 2026-07-12; reuses the edit-map machinery MVP
already needs for multi-hunk verification) · **Markdown scanning via a vendored CommonMark
parser** (see Scanner dependency) · NO persistent learning (accept an explicit voice
sample / provisional descriptor + disclose prompt-evidence transfers poorly).
**Then, in order:** mixed-region genre → expanded scanner → persistent voiceprint
learning → legal profile (only after dedicated tests).

## Evals
Fixtures carry: canonical original, editable ranges, protected spans, expected-invariants.
**Programmatic:** protected spans byte-identical; URLs/citations/identifiers/defined-terms
exact; numeric multiset (value,unit,qualifier,subject) preserved; dates/versions preserved;
modal inventory preserved; negation preserved near predicate; condition markers preserved;
no edits outside authorized ranges; no new numbers/dates/proper-nouns/endpoints/thresholds/
quoted-authorities/citations; no new placeholders unless allowed; Markdown parses pre+post;
code hashes match; diff under fixture budget; **idempotence** (2nd run no material diff);
scanner JSON schema-valid + locations map to source. **LLM-judge (blinded A/B vs humanizer
AND vs original-unchanged, must cite spans):** meaning preservation; unsupported-claim
introduction; actor/responsibility preservation; unresolved-intent stays visible;
editorial-cost reduction; voice distance from samples; genre fitness; edit locality/justification;
seeded defect fixed WITHOUT normalizing surrounding distinctive prose. **Clean-document
controls** (a system that always finds something to fix fails these; "original unchanged"
should sometimes win).

## Evaluation decision rule (WF5 #1)
Makes "beat humanizer / let the original win / pick a tier" a reproducible pass/fail, not a
vibe:
- **Hard gates (any failure ⇒ fixture FAIL, overrides all judge scores):** every
  programmatic check above passes — protected spans byte-identical, no changed
  number/unit/modality, no invented claim, no edit outside authorized ranges, idempotent
  2nd run, Markdown parses pre+post. Prose quality can never outscore a hard-gate failure.
- **Per-dimension score:** each LLM-judge dimension scored 0/1/2 (harmful / neutral /
  better-than-baseline) over ≥3 blinded trials per (fixture × engine × baseline); take the
  per-dimension median to damp judge variance.
- **Beat criterion + ties:** a fixture BEATS a baseline iff it passes all hard gates AND
  its median dimension-sum ≥ the baseline's on that fixture AND it strictly wins ≥1
  dimension with none worse by >1. A tie (equal sums) resolves to the MORE
  preservation-heavy output (fewer edits / closer to original) — never the more-edited one.
- **Clean-document controls:** on clean/stylized fixtures the pass criterion is
  ABSTENTION — `original-unchanged` must win or tie; ANY material edit is a fixture FAIL
  regardless of judge scores.
- **Engine selection:** choose the tier passing the most fixtures' hard gates, tie-broken
  by aggregate dimension-sum across fixtures; record per-tier results, never a single
  blended number.

## Second-order failures (in eval-cases.md)
diagnosis-theater · taxonomy-leakage (outputting "specification-laundering" vs plain
language) · scanner-anchoring (treating a soft flag as proof) · non-native normalization ·
dialect suppression · competence-laundering (cleaner prose making weak reasoning look
authoritative) · uncertainty deletion · responsibility reassignment (invented actor) ·
vision-policing (challenging every PRD aspiration) · question-explosion · iterative-sanding
(runs erode voice) · self-referential slop (the audit itself is sloppy) · corpus
contamination (pasted text learned as user voice) · acceptance-ambiguity (unchallenged ≠
endorsed) · genre-boundary-bleed · protected-span-laundering (hiding bad prose in quotes/
code) · diff-fragmentation (many safe micro-edits jointly shift tone) · false-idempotence.

## Build order (fixtures-first, owner decision 2026-07-12)
1. **Pin the 3 canonical eval fixtures FIRST** (distinctive-essay / normative-spec /
   underspecified-PRD + clean-document controls) — canonical original, editable ranges,
   protected spans, expected-invariants. They ARE the red test and the acceptance contract;
   the ledger + verify + apply mechanics are built to satisfy them. Round 3 flagged them
   unpinned — this is the gate, not a later step.
2. Scaffold the plugin (`.claude-plugin/plugin.json`, `skills/slopslap/SKILL.md`,
   `commands/`, `references/`).
3. Build the scanner (`scripts/scan_prose.py`) — plain-text path first, then the vendored
   CommonMark parser per Scanner dependency.
4. Run the eval loop (see Evals): slopslap vs `humanizer` vs `original-unchanged` across the
   available Claude tiers.

## Layout (PLUGIN)
```
slopslap/                        (a Claude Code plugin)
├── .claude-plugin/plugin.json   (manifest)
├── skills/slopslap/SKILL.md     (the judgment: loop + keystone + prohibitions + modes)
├── commands/                    (slash commands: audit · suggest · apply ·
│                                 voiceprint show/reset/export/delete)
├── hooks/                       (v2: UserPromptSubmit capture for the voiceprint —
│                                 the reason this is a plugin, not a skill)
├── scripts/scan_prose.py        (the measurer; plain-text + capability-gated markdown)
├── scripts/slopslap_scan/       (markdown adapter over the vendored parser)
├── vendor/python/               (pinned markdown-it-py + mdurl — plugin-private, v1)
├── THIRD_PARTY_LICENSES/        (vendored-dep licenses + provenance)
└── references/
    ├── invariant-ledger.md   (schema + verification + decision rule + canonical coords)
    ├── scanner-metrics.md    (exact metrics + markdown handling)
    ├── tell-taxonomy.md      (categories + before/after, kept separate)
    ├── genre-profiles.md
    ├── voiceprint.md         (v2 design)
    ├── engine.md             (default Opus 4.8 hi-effort; Fable 5 = bonus-if-API)
    └── eval-cases.md         (define the 3 CANONICAL fixtures — distinctive-essay,
                               normative-spec, underspecified-PRD — + clean controls +
                               model A/B + second-order list; round-3 flagged the 3 unpinned)
```
v1 ships the skill + commands + script + references; the hooks/ (voiceprint capture)
arrives with the v2 persistent-learning phase.

## Name / baseline
Name `slopslap` (owner's). Baselines: `humanizer` (not an oracle — compare invariant
violations, edit locality, invented detail, defect removal, clean-doc abstention, voice
preservation) AND `original-unchanged` (should win on clean/stylized prose).
