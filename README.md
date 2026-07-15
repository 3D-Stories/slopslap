# slopslap

A Claude Code **plugin** that repairs prose carrying **high editorial cost** — genericness,
unsupported claims, synthetic cadence, obscured responsibility, voice discontinuity — while
preserving meaning, technical accuracy, requirements, uncertainty, and the author's intentional
voice.

**slopslap is NOT an AI-authorship detector.** It beats humanizer-style tools precisely by *not*
treating a stylistic feature as a contaminant. Its whole discipline is the keystone rule:

> **Every tell is detected and prepared for removal; genre and learned feedback set each finding's
> recommendation; the user's review decision — not the scanner, not the genre, not the learning —
> authorizes the edit; and the byte-exact verifier guarantees no applied edit changes a number,
> requirement, negation, condition, defined term, or protected span. Recommendations may learn;
> authorization never does.**

The name says "slap" — ignore that impulse. An em-dash, a fragment, a tricolon, a passive verb:
none is harm on its own. Harm is prose that does less than it claims, hides who is responsible,
asserts what it hasn't shown, or buries its own meaning. When in doubt, slopslap changes nothing.

## Overview

The **visual plugin overview** — the skill, the four commands, the
protect→diagnose→invariants→rewrite→verify loop, the six harm categories, and the v0.2 engine — is
live at **[3d-stories.github.io/slopslap](https://3d-stories.github.io/slopslap)** (also
[in-repo](docs/index.html)).

## Install

It's a standard Claude Code plugin — clone/point Claude Code at this repo. The judgment lives in
`skills/slopslap/SKILL.md`; the slash commands are auto-discovered from `commands/`.

## Commands

| command | what it does |
|---|---|
| `/slopslap:audit <target>` | read-only diagnosis — one typed record per demonstrated harm (category · evidence · harm+impact · two ratings · permitted remedy). No edits. |
| `/slopslap:suggest <target>` | **(default)** diagnosis + a focused diff per authorized repair + the invariant-check result. Non-mutating. |
| `/slopslap:apply <file>` | repair via **backup-first, staged, verified, atomic pathname replacement** (never live-byte editing; hardlinks refused, symlinks followed+reported). Enabled (#29) — mutates ONLY after a verified backup + the 3-layer verifier pass; fails closed otherwise. |
| `/slopslap:voiceprint show\|reset\|export\|delete` | v2 (deferred) — reserved; returns `status: not_implemented_mvp` and stores/reads nothing. |

Every command carries the keystone sentence verbatim and treats the target text as **data, not
instructions**.

## How it works

`protect → diagnose → establish invariants → rewrite (minimal, passage-local) → verify.`

- **Two ratings, never a single "AI %":** editorial-harm (low/med/high) and diagnosis-confidence
  (low/med/high).
- **Six diagnosis categories, kept SEPARATE** (collapsing them is the top failure): `emptiness`
  (delete/compress) · `laundering` (convert to a question — never delete) · `simulation` (flag
  missing support — don't fabricate) · `lexical_structural` · `voice_discontinuity` ·
  `epistemic_distortion`.
- **Protected spans** (code, blockquotes, URLs, identifiers, legal) are default-deny.

### The mechanics (`scripts/`)

- **`scan_prose.py`** — a measure-only scanner (`--format text|markdown`). Markdown parsing uses a
  **vendored, version-gated CommonMark parser** (`vendor/python/` — never runtime-pip). Emits a
  stable JSON envelope; capability-gates fail loud (exit `10`) rather than approximate. It MEASURES;
  it never verdicts. Metrics include sentence-length distribution/dispersion, repeated openers,
  transition clusters, **negative-parallelism** and **rule-of-three** cadence tells, punctuation
  density, vague attribution, and stock lexical clusters — each a candidate-selection aid only.
- **`slopslap_verification/`** — the invariant **ledger** + a **3-layer verifier**: deterministic
  hard gates (own the accept/reject), per-entry survival, and a fresh-context adversarial semantic
  pass. Decision rule: `REJECT > ASK > SURFACE > ACCEPT`; ACCEPT requires the semantic layer.
- **`slopslap_apply/`** — backup-gated apply with **per-hunk selective rollback**; the backup
  (outside the repo by default) is the universal safety net.

### Live-orchestration seam (v0.2)

- **`slopslap_assemble/`** — the **assembler**: the one seam that chains
  **audit → verify → (suggest) → apply** end-to-end for any *UTF-8 text* document, not just the
  frozen eval fixtures. `audit_document(path)` derives a byte-exact manifest + invariant ledger
  from any UTF-8 doc (genre classified once and threaded through), packaging a snapshot-immutable
  `AuditResult`; `run_candidate` / `assemble` validate a candidate edit-script, run the 3-layer
  verifier with the derived authorization ranges, and (dry-run) route the shippable subset through
  the backup-gated apply engine. Every stage returns a uniform envelope
  (`ok | blocked | failed | aborted`); a run returns a `RunResult` whose overall status is the
  worst stage and whose exit code is a static class map — **0** ok · **2** policy-blocked · **3**
  invalid input/contract · **4** stage execution failure. A **policy** block (out-of-range edit,
  weakened invariant, ambiguous verdict) reads differently from an **execution** failure, and a
  semantic *invocation* failure is never laundered into a policy verdict. Thin JSON CLI:
  `python3 scripts/slopslap_assemble/assemble.py audit --path P` and
  `… run --path P --edits EDITS.json --dry-run` each emit exactly one JSON `RunResult` (no source
  bytes; the ledger as `{canonical, sha256}`). `run` is dry-run only until the apply-flip
  (`write=False`, source never mutated).

## The working proof

`scripts/eval/run_eval.py` replays frozen candidate edit-scripts through the production runner +
verifier. Results: `docs/reviews/2026-07-12-slopslap-eval-results.md` (+ `-visual.html`). slopslap
clears the decision-rule hard gates on 3 canonical fixtures, **abstains** on clean controls, is
idempotent, repairs the real 421-line kukakuka PRD (flagging its `X, not Y` ×16 cadence, tightening
2 local inflations, **zero invariant violations**), and beats a documented humanizer-emulation
policy. The kukakuka path now runs **Layer 3 end-to-end** — the fold reaches a shippable `ACCEPT`
(`semantic_status: clean`) via a real fresh-context `claude -p` pass under `SLOPSLAP_LIVE=1`.
Offline (default) it uses a hardcoded `clean` stub (the frozen faithful candidate is asserted
clean; `scripts/eval/semantic.py`), so offline the run exercises the full L3 fold plumbing — not a
real semantic judgement. Run it: `pytest -q` (the gate) or `python3 scripts/eval/run_eval.py --write`.

## In action

Illustrative before → after repairs, one per harm class. In every case the demonstrated harm is
removed and **nothing else is touched** — facts, numbers, requirements, and voice survive. These
show the *judgment*; the machine-checked proof on a real 421-line document is in **The working
proof** above.

### Emptiness + simulation — cut the filler, flag the unbacked claim (don't invent support)

> **Before.** In today's rapidly evolving landscape, it is important to note that our platform
> leverages a robust, scalable, and cutting-edge architecture to deliver best-in-class performance
> that our users have come to know and love. Whether you are a seasoned professional or just
> starting out, our solution empowers you to unlock your full potential and achieve remarkable
> results across a wide range of use cases.

> **After.** Our platform runs on a distributed architecture. `[claim: "best-in-class performance" —
> no benchmark or measurement shown]` `[claim: "users have come to know and love" — no evidence of
> adoption cited]`

slopslap deletes the empty framing (`In today's rapidly evolving landscape…`, `Whether you are a
seasoned professional…`) because removing it loses no intent, collapses the `robust, scalable, and
cutting-edge` tricolon to the one word carrying meaning, and **flags** the two simulated claims
rather than repairing or inventing evidence for them. It does not assert the platform *isn't*
best-in-class — only that the prose hasn't shown it. `editorial-harm: high · confidence: high`.

### Laundering — convert the vague ask to a question; preserve the real requirement byte-for-byte

> **Before.** The retry subsystem should be robust, intuitive, and user-friendly under all
> conditions, providing a seamless and delightful experience for operators. The client MUST retry a
> failed request at most 5 times, waiting no less than 200 ms and no more than 2000 ms between
> attempts, and MUST NOT retry a `429` before the `Retry-After` interval has elapsed.

> **After.** `[non-testable — what does "robust, intuitive, and user-friendly under all conditions"
> require an operator to be able to do? name the observable behavior]` The client MUST retry a
> failed request at most 5 times, waiting no less than 200 ms and no more than 2000 ms between
> attempts, and MUST NOT retry a `429` before the `Retry-After` interval has elapsed.

The first sentence is evaluative language wearing a requirement's clothes, so slopslap converts it
to a question — it **never deletes** laundered text, because the intent behind it is load-bearing.
The genuine normative sentence is preserved exactly: every number (`5`, `200 ms`, `2000 ms`), every
modal (`MUST`, `MUST NOT`), the negation, and the protected `` `429` ``/`` `Retry-After` `` spans
are byte-identical. `editorial-harm: med · confidence: high`.

### Epistemic distortion — restore the hidden actor without inventing one; keep the honest hedge

> **Before.** It was determined that a configuration error had been introduced, and it is believed
> that the outage may have possibly been caused by an unrelated deployment that was rolled out around
> the same timeframe. Mistakes were made, and steps are being taken to ensure this will never happen
> again.

> **After.** We introduced a configuration error. The outage **may** have been compounded by an
> unrelated deployment rolled out around the same time — `[actor unclear: who rolled out the
> unrelated deployment?]` we have not confirmed this. We have added a pre-deploy config check to
> catch this class of error.

The passive `It was determined` / `Mistakes were made` hides who acted, so slopslap restores the
first-person actor where the source implies it and **flags** the one it genuinely can't resolve
rather than fabricating a name. It keeps the real uncertainty (`may have`) — that hedge is honest,
not slop — while cutting the hedge-*pile* (`may have possibly been`) and the empty
`never happen again` promise, replacing it with the concrete step the text actually supports.
`editorial-harm: high · confidence: med`.

### What it leaves alone

> A short, sharp fragment. An em-dash for a sudden turn — like this. A deliberate second-person
> aside, because that's how this author writes.

slopslap changes **nothing** here. None of these is harm: the fragment is intentional, the em-dash
earns its place, the voice is distinctive and consistent. The keystone holds — no demonstrated harm,
no edit. *When in doubt, it changes nothing.*

## Status

- **Version:** 0.13.1 — edit textarea auto-resizes with its content (UAT feedback; field-sizing + JS fallback, no inner scrollbar). Previous: 0.13.0 — alternatives authoring contract + learning (#84, epic #85 C4, closes the
  epic): the model lane authors alternatives for `simulation`-class findings in three sanctioned
  shapes, every candidate pre-checked via the new `findings.precheck_replacement`; the
  no-new-claims gate stays exemption-free by design; alternative-pick provenance rides the
  feedback ledger and the keep-only learning overlay is proven un-flippable. Previous: 0.12.0 —
  review-UI de-claim alternatives (#83, epic #85 C3): findings carrying
  `alternatives` render the mockup's pick-buttons with claim-status chips (banned = disabled);
  a pick seeds the edit textarea and rides into decisions as edit provenance; plus the
  proposed-rewrite render fix (b64 dict decoded, empty = delete marker). Previous: 0.11.0 —
  no-new-claims lexeme tier (#82, epic #85 C2): `verify()` Layer 1 now also
  rejects a replacement that INTRODUCES a corporate buzzword or borrowed-authority phrase absent
  from the original (token-boundary, case-insensitive; removals/reuse never trip) — the mockup's
  "lateral swap = banned" rule, deterministic. Previous: 0.10.0 — de-claim alternatives schema
  (#81, epic #85 C1): findings MAY carry
  `alternatives` (`{id,text,claim_status∈{none,scoped,kept,banned},label?}`, validated at the
  payload boundary), a decision's `alternative` is edit-only and bound to what its finding
  actually offered, and the provenance label rides into the feedback ledger. All
  additive-optional — alternative-less payloads stay byte-identical. Previous: 0.9.0 — review
  page rebuilt in the ratified pivot design language
  (`docs/planning/2026-07-13-deslop-pivot-design.html` §02): cream/dark editorial theme, serif
  passages with strike→proposal rendering, mono category/recommendation chips, ✂/✎/✋ outcome
  buttons with a `· rec` marker, inline edit textarea, live tally + progress, theme toggle. The
  server startup line now prints the `ssh -L` tunnel command for remote browsers
  (`SLOPSLAP_TUNNEL_HOST`, default `claude-code`). Engine behavior unchanged. Builds on #43
  (v0.8.4), #46 (v0.8.3), #36 (v0.8.2), #47 (v0.8.1).
- **Engine:** whatever Claude tier the session provides (Opus 4.8 / Sonnet 5) at high effort;
  Fable 5 is a bonus rewrite tier *if* API access exists — never required.
- **Deferred (v2):** persistent voiceprint learning + its UserPromptSubmit capture hook; a live
  cross-model LLM-judge A/B (currently secondary/not-run). Scanner thresholds stay measure-only until
  a licensed calibration corpus with verbatim text clears the validation bar.

## Changelog

- **0.13.1** — review-page edit textarea auto-resizes to its content instead of scrolling (UAT feedback 2026-07-15): native `field-sizing: content` plus a JS fallback that also fires on programmatic fills (alternative picks, edit-open); `overflow: hidden`, no manual resize handle.

- **0.13.0** — alternatives authoring contract + learning (#84, epic #85 C4, 2026-07-15): the
  authoring contract lands in `skills/slopslap/SKILL.md` (`anchor:alternatives-authoring`, drift-
  guarded by one anchored test) — the MODEL lane authors alternatives only for `simulation`-class
  findings, in three sanctioned shapes (subjectivize / describe-intent / scope-verifiable), and
  pre-checks every candidate through the new `findings.precheck_replacement` (a `blocked` verdict
  naming `no_new_claim_atoms` ⇒ `claim_status: banned`). Deliberate decision: the no-new-claims
  gate keeps NO exemption path (`allowed_claim_atoms` stays unplumbed through `verify()`) —
  alternatives compose from claims the original span already carries. Learning:
  alternative-labeled ledger lines (label on the line since #81) are consumed by
  `learn_from_feedback` as ordinary edits — the provenance is a record, not a distinct learning
  signal — and keep-only is STRUCTURAL: the overlay exposes only `keep_classes`, so no feedback
  volume can turn a keep into a strip (tested: 20 alternative-labeled edits soften a strip base
  to keep; nothing can move the other way). Recommendations may learn; authorization never does.
- **0.12.0** — review-UI de-claim alternatives (#83, epic #85 C3, 2026-07-15): a finding carrying
  `alternatives` (#81 schema) renders the ratified mockup's `.alts` block — one pick-button per
  alternative with its claim-status chip (`no external claim` / `claims what the doc supports` /
  `kept` / `BLOCKED …`); `banned` alternatives render disabled and are never selectable. Picking
  one seeds the inline edit textarea, sets the card to `edit`, and records the alternative id as
  the edit's provenance (`decisions[].alternative`, bound server-side to what the finding actually
  offered per #81). Selection authorizes nothing — Finish is the decision, the verifier the gate.
  Also fixes the proposed-rewrite render: the page now decodes the real
  `{start,end,replacement_b64}` shape (empty = "∅ span deleted" marker) instead of a never-true
  string type-test, so strike→proposal rendering actually fires. Rendering stays textContent-only.
- **0.11.0** — no-new-claims lexeme tier (#82, epic #85 C2, 2026-07-15): the deterministic
  no-new-claims gate (already live in `verify()` Layer 1 for hard atoms — numbers, dates, urls,
  citations, thresholds) gains the LEXEME tier: a replacement that introduces a corporate
  buzzword (`tables.CORPORATE_BUZZWORDS`) or a borrowed-authority phrase
  (`tables.VAGUE_ATTRIBUTION`) absent from the original span now fails Layer 1 with the lexeme
  named — the mockup's "lateral swap = banned" rule (best-in-class → industry-leading), made
  deterministic. Token-boundary + case-insensitive, no inflection matching ("robustness" is not
  "robust"); removals and reuse of existing claims never trip; the gate only ever ADDS a
  rejection reason. Tables stay single-sourced in `slopslap_scan.tables` (leaf module, no cycle).
- **0.10.0** — de-claim alternatives schema (#81, epic #85 C1, 2026-07-15): additive-optional
  `alternatives` on findings (`{id, text, claim_status ∈ {none, scoped, kept, banned}, label?}`,
  shape owned by `schema.validate_alternatives` and ENFORCED at the payload boundary — a malformed
  list from any producer fails loud, never reaches the UI); a decision's `alternative` is edit-only
  (it labels the provenance of an alternative-seeded edit) and, at the finish + apply boundaries, is
  bound to the set its finding actually offered (a stale/fabricated label is rejected, protecting
  learning attribution); `decisions_from_actions` copies the label on presence (an empty value fails
  closed at the validator instead of vanishing); the label rides into the feedback ledger line.
  Alternative-less payloads stay byte-identical. Cross-model adversarial diff review: 3 Medium
  findings, all verified and applied red-before-green.
- **0.9.0** — review page rebuilt to the ratified mockup (UAT feedback, 2026-07-15): the interactive
  review page now carries the pivot design language from
  `docs/planning/2026-07-13-deslop-pivot-design.html` §02 — cream/dark editorial paper (grid
  background, serif display header), per-finding cards with mono category + recommendation chips,
  serif passage rendering that strikes the original and shows the engine's proposal in green,
  ✂ apply / ✎ edit / ✋ keep outcome buttons (the recommended one carries a `· rec` marker), an
  inline edit textarea pre-filled with the visible span (replacing the old `window.prompt`; an empty
  replacement never emits — Finish refuses and points at the finding), re-click to unset, tinted
  card states, a live `N strip · N edited · N keep · N undecided` tally + progress counter, a theme
  toggle, and blocked findings showing the verifier reason with feedback-only buttons. The server
  startup message now also prints the exact `ssh -L <port>:127.0.0.1:<port> <host>` tunnel command
  for reviewing from a remote browser — host from `SLOPSLAP_TUNNEL_HOST` (default `claude-code`);
  the server itself stays loopback-only by design. Rendering stays `textContent`-only (XSS-safe);
  no engine, schema, or authorization change.
- **0.8.4** — v0.4 hardening (#43, Epic #67 Wave 3): a self-checking edit-script. The wire shape
  `{start_byte,end_byte,replacement_b64}` carried no expected preimage, so an in-bounds offset at the
  WRONG bytes — a stale/drifted script whose offsets happened to stay valid, and that still preserved
  every invariant — was not caught structurally. `Edit` gains an optional `preimage_sha256`, parsed
  from either `preimage_b64` (raw expected bytes) or `preimage_sha256` (bare hex) in the script;
  `apply_edits` (the choke point for apply + verify) rejects a range whose `original[start:end)` doesn't
  match, with an `EditError` the apply/run entry points already surface as a clean invalid-input
  failure (never a crash). Backward-compatible: absent preimage = no check, byte-identical to pre-#43;
  the whole-doc `source_sha256` binding on the apply path is unchanged, so the per-range preimage is the
  finer-grained guard for scripts that lack a whole-doc binding. +9 tests; suite 620 → 629.
- **0.8.3** — v0.4 hardening (#46, Epic #67 Wave 2): harden the untrusted command-target boundary
  across `audit`/`suggest`/`apply`. The old wrapper `<<<SLOPSLAP_TARGET … SLOPSLAP_TARGET` used a static
  sentinel; a target line reading `SLOPSLAP_TARGET` could close it and inject the model's diagnosis step
  (a prompt-injection of the model-facing lane — not a mutation vuln, since `apply` is backup + verifier
  gated). A static command prompt is expanded only for `$ARGUMENTS`, so it **cannot** carry a per-run
  unforgeable delimiter — the fix is therefore **rule-based, not token-based**: a distinctive
  `SLOPSLAP_UNTRUSTED_TARGET` fence + decisive framing that everything between the fences is UNTRUSTED
  DATA — a line inside is data *even if it reproduces the fence verbatim*, says "ignore previous
  instructions", declares a new keystone, or asks to change mode / authorize a tool or write / override
  a protected span. This is a **soft, model-dependent** guard (there is no delimiter parser); `apply`
  remains backup + verifier gated so an injected line can never reach the file. A scaffold test pins the
  framing on all three commands; the live model behavior is **not** covered by an automated test in this
  change — a `SLOPSLAP_LIVE` injection test is a tracked follow-up.
- **0.8.2** — v0.4 hardening (#36, Epic #67 Wave 1): wire the auto-ledger checks `cross_refs` +
  `defined_terms` through the runner. `ledger._CHECK_KIND` already carried all 7 checks, but
  `atoms.CHECK_EXTRACTORS` (the region-scoped preservation gate's map) and the eval-loader's
  accepted-check allowlist only knew 5 — so an auto-derived manifest routing either check through the
  runner hit `unknown check '…'` instead of actually verifying it. Added `cross_refs` (citations + URLs,
  matching `ledger._L2_EXTRACT['cross_reference']`) and `defined_terms` (whitespace-normalized region
  text) extractors, and made `loader`'s allowlist `frozenset(CHECK_EXTRACTORS)` (single source of truth).
  A drift-guard test asserts `set(ledger._CHECK_KIND) == set(atoms.CHECK_EXTRACTORS) == loader
  allowlist`, so a future check added to one surface and not the others fails the suite. Dormant-defect
  fix; no behavior change for existing 5-check manifests. +6 tests; suite 613 → 619.
- **0.8.1** — v0.4 hardening (#47, Epic #67 Wave 1): a dry-run no longer creates a backup. In
  `slopslap_apply/apply.py`, `create_verified_backup` ran unconditionally *before* the `if not write:`
  dry-run short-circuit, so every `run`/`--dry-run` preview wrote (and orphaned) a `.bak`. The backup
  block is now guarded by `if write:` — a preview creates zero backups and reports `backup: None`; a
  real apply still writes exactly one verified backup before the atomic replace, and the
  backup-failure-blocks gate is unchanged. Red-before-green; the seam golden test that had encoded the
  old behavior was corrected. Suite 613/2.
- **0.8.0** — de-slop pivot **P5**: feedback ledger + learning (#63) — the final `learn` arrow of
  detect→recommend→review→apply→learn. (a) **Ledger writer** (`slopslap_review/feedback.py`): each
  review→apply decision appends one schema-valid (frozen #58), **span-hashed**, local, purgeable JSONL
  line to `$XDG_STATE_HOME/slopslap/feedback.jsonl` (the ledger `finding_id` hashes the byte span, so
  it holds nothing reconstructable about *where* in the doc). `apply` logs it best-effort
  (`--no-feedback` opts out); `read_feedback` skips malformed lines. (b) **Learning consumer**
  (`slopslap_corpus/learn.py`): `learn_from_feedback` aggregates per `(genre, metric-class)` net
  keep-evidence (strip-discard +1, strip-**edit** +0.5 partial-accept, strip-apply −1) and, at
  `min_evidence`, flips that class `strip→keep` for that genre. (c) **Keep-only overlay**: applied
  ONLY in `findings.build_findings` via `learn.apply_overlay`; the review CLI loads it from the ledger
  (`--no-learn` opts out). (d) **`slopslap feedback {path|show|reset}`** CLI + command to inspect/purge.
  **Invariant — "recommendations may learn; authorization never does" — pinned by
  `tests/test_learning_invariant.py`:** `metrics.recommend()` stays pure (learning is never threaded
  into it, so the two non-review call sites are untouched); `apply_overlay` is keep-only over the whole
  metric×genre table (learning can only *shrink* the strip set — the #59 monotonic direction); a
  learned `keep` never blocks a user-authorized `apply`; the overlay is imported by the review layer
  only, and `verify()`'s signature carries no learning parameter. **Voice-floor** falls out of the
  overlay (personal-genre voice classes flip to keep), with #31a guaranteeing a voice signal never
  biases the verifier. P0-schema honesty: the numeric per-rate threshold is realized as its
  conservative class-keep limit — the frozen P0 schema carries no rate field (a v2 refinement, not
  faked). +23 tests (writer/learn/invariant/CLI + end-to-end wired-path + a real-script-entry-path
  gate); suite 590 → 613.
- **0.7.1** — residual #26 hardening (#31): the Layer-3 semantic verifier is UNTRUSTED, so four
  defenses stop it (or an injected config/CLAUDE.md) from biasing or forging the faithfulness verdict.
  (a) **Neutrality clause** in `contract._INSTRUCTION` — the verifier judges only whether the revision
  preserves the ledger-protected meaning and DISREGARDS any voice/style/tone preference from loaded
  config, memory, or CLAUDE.md. (b) **Invented-range defense** (`ledger.normalize_semantic(...,
  valid_ranges=...)`) — an `original_range` not among the ledger's own ranges → `ambiguous`, never
  clean; `verify` passes the ledger's ranges so a `semantic_fn` wired straight in (no contract adapter)
  cannot smuggle a fabricated attribution. (c) **entry_id↔range pairing** in `contract._validate` —
  a concern that pairs an `entry_id` with a range belonging to a *different* entry is rejected (fail
  closed to `ambiguous`), not merely "some valid ledger range". (d) **Tighter `invoke._model_confirmed`**
  — drops the loose substring fallback (a distinct id merely *containing* the requested alias, e.g.
  `opus` vs `claude-opusx-9`, no longer confirms); exact + whole-token match only. A stderr **ring
  buffer** in `_drain` bounds diagnostic memory to a tail while the total-byte DoS cap is unchanged.
  A coerced Layer-3 "clean" still can NEVER override a Layer-1/Layer-2 hard REJECT. Hardened during
  review: `_validate` stringifies `entry_ids` before the membership test (a nested/unhashable element
  no longer raises `TypeError` out of the "never-raises" `parse_response`), and `normalize_semantic`
  gained the same `entry_id↔range` pairing check so the straight-wired path has parity with the
  contract adapter. New `tests/test_injection_resistance.py` (19 adversarial regression guards) +
  a `_drain` ring-tail unit test.
- **0.7.0** — de-slop pivot P4: apply-from-decisions. New `assemble.py apply --path PATH --decisions decisions.json`
  (+ `apply_from_decisions` in `scripts/slopslap_assemble/assemble.py`) applies ONLY the user-approved
  (apply/edit) hunks from a review `decisions.json`. `decisions.json` is UNTRUSTED — schema-validated
  (`validate_decisions_for_apply`), its finding-ids matched against the document's own findings, and
  bound to the audit's `source_sha256` (a drifted file → `digest_mismatch`, which also makes a replayed
  second pass a safe no-op). The **authorization ranges come from the user's accepted findings, not the
  genre strip-gate** (keystone v2 — resolving the #59/#61 P4 forward-risk). The 3-layer verifier +
  mandatory verified backup + atomic pathname replacement are the byte-for-byte unchanged engine
  (`run_candidate` → `apply_selective`); a user-approved hunk the verifier rejects is surfaced blocked,
  never silently applied, and an all-discard/undecided set is a clean no-op. E2E golden coverage:
  safe-applies / invariant-breaking-blocks / discard-untouched / replay-rejected / unknown-id-rejected.
- **0.6.0** — de-slop pivot P3: the interactive review stage. New `slopslap review <target>` command +
  `scripts/slopslap_review/review.py`: the engine writes `findings.json`, then serves a self-contained
  review page on `127.0.0.1:<random port>` (stdlib `http.server`, per-run URL token via
  `secrets.compare_digest`, loopback-only bind, idle-timeout, shutdown after Finish; no filesystem
  serving → no path-traversal surface; no new dependencies). Per finding: a labeled one-click button
  per outcome (**apply strip / edit / keep original**, the recommended one rec-badged), with blocked
  prechecks shown read-only + selectable as false-positive feedback. The page is XSS-safe by
  construction — the findings payload is an inert `<script type="application/json">` blob rendered with
  `textContent` only (no HTML-string concatenation). **Finish** POSTs the decision set → the engine
  writes `decisions.json` (frozen #58 schema, bound to `source_sha256`, schema-validated) and exits;
  **`--static`** / **Export** produces the same file for a no-server browser (feed to
  `apply --decisions`, #62/P4). The review stage authorizes nothing itself — it only records the
  user's per-finding decision; the byte-exact verifier still hard-gates every applied edit.
- **0.5.0** — de-slop pivot P2: the generic-diction / filler detector (the "finds more" payload).
  New `generic_diction` scanner metric (`scripts/slopslap_scan/metrics.py` + pinned `CORPORATE_BUZZWORDS`
  / `EMPTY_INTENSIFIERS` tables): flags corporate-slop buzzwords and empty intensifiers as escaped
  word-boundary literals (no ReDoS), measure-only with a calibratable `GENERIC_DICTION_FLAG_AT` threshold.
  Classified into the `filler` metric-class, so it feeds the P1 genre recommendation layer (strip under
  general/prd/technical; the user's review decision still authorizes, the verifier still hard-gates) and
  is registered in the `calibrate.py` tell map (`genericness`) for threshold fitting once P5 review-decision
  labels arrive. The `pair-corporate-adjective-pile` / `pair-generic-diction` golden fixtures carry
  labeled `generic_diction` slop; the detector's behavior is exercised by `tests/test_scanner_metrics.py`.
- **0.4.0** — de-slop pivot P1: universal detection + findings-with-recommendations + keystone v2.
  `GENRE_SUPPRESS` polarity flips — genre never empties a metric's `locations`; suppression survives
  only as a per-finding `recommendation` (a new per-(genre, metric-class) `recommend()` table whose
  keep-sets are seeded from the prior suppress profiles). `authorized_ranges_from_diagnoses` now gates
  editable ranges on `recommendation == "strip"`, so a genre-KEPT passage can never leak into the
  verifier's authorized edit set — genre still never authorizes. New `scripts/slopslap_review/findings.py`
  builds a strip-ready `Finding` per tell `{id, category, span, evidence, genre, recommendation,
  rationale, confidence, proposed_rewrite, verifier_precheck}`; each `proposed_rewrite` is pre-cleared
  through verifier Layers 1+2 (`decision == "ACCEPT"` ⇒ "safe", else "blocked") so a review UI can show
  safe-vs-blocked per finding. **Keystone v2** (pinned verbatim across SKILL.md, the four command files,
  and `tests/test_scaffold.py`): the user's review decision — not the scanner, genre, or learning —
  authorizes the edit; recommendations may learn, authorization never does. P1 ships universal
  detection + the findings envelope + this keystone rewrite; the *enforced* review→apply loop the
  keystone describes is built across the later phases (review UI #61/P3, apply-from-decisions #62/P4,
  feedback learning #63/P5).
- **0.3.0** — de-slop pivot P0: frozen review-loop data contracts. Adds
  `scripts/slopslap_review/schema.py` with two stdlib validators (no new dependency) that ARE the
  contract for the pivot's REVIEW → LEARN stages: `validate_decisions` for `decisions.json` (the
  user's per-finding apply/edit/discard set — **untrusted** input to `apply`, so the validator is a
  fail-closed boundary: strict key/enum allowlists, 64-hex `source_sha256` binding that rejects
  replay against a drifted file, base64-only replacement payloads, optional finding-id matching
  against an audit snapshot) and `validate_feedback_line` for the local `feedback.jsonl` ledger.
  Also seeds the `tests/fixtures/eval/pair-*` **slop→clean golden pair** fixture family (before/after
  labels the calibration harness was starved of) with a hermetic `pair-*` glob guard. Schema versions
  frozen at 1. No user-facing command yet — this is the groundwork P1–P5 build on.
- **0.2.2** — doc-honesty fix. The seam ingests **UTF-8 text only** (`--format markdown|text`; a
  non-UTF-8/binary input exits `3` `genre_error`), so the "arbitrary / any documents" copy was an
  overclaim — corrected to "any UTF-8 text document" across the overview page, README, and the plugin
  manifest. Surfaced by pointing the tool at a `.pptx` and at its own HTML page, both of which had to
  be text-extracted before the seam would run. Format adapters (pptx/html/pdf → text) are tracked
  separately as a feature.
- **0.2.1** — real-world QA calibration fixtures. Captures three eval cases from a live audit/suggest
  run on an aviation-SMS deck, labeled by the document owner: two must-abstain controls (first-pass
  false positives — a numeric "contradiction" whose figures have different referents; an honest
  `has/could` hedge on an illustrative example) and one flag-only true positive (an unsupported
  benchmark; remedy = flag, never fabricate a citation). Data-only under `tests/fixtures/eval/qa-*`
  with a hermetic validity guard (`tests/test_qa_fixtures.py`); not yet in the pinned `run_eval`
  inventory (that needs a live-model first-pass digest — tracked follow-up). Encodes two calibration
  lessons: a numeric contradiction that only appears once you assume a shared referent is a pass, and
  an explicit could/may hedge on an example is honest marking, not `simulation`.
- **0.2.0** — scanner threshold calibration + the v0.2 epic close (#25, final Tier-4 child). Ships
  `scripts/slopslap_corpus/calibrate.py`, the calibration harness: it fits per-metric thresholds on the
  #30 corpus CALIBRATION partition only, reports precision/recall/abstention per stratum
  (tell/genre/length) on the HELD-OUT partition, and **never tunes against held-out** (structural). It
  **never auto-promotes** — the scanner stays measure-only until an explicit validation bar is met AND
  a human signs off. Honest current verdict (`docs/reviews/2026-07-13-25-scanner-calibration-report.md`):
  the reference corpus tunable items carry no verbatim text (metadata/inspiration-only under their
  licensing) → 0 usable calibration points → **measure-only**; the harness fires when the corpus gains
  licensed text. The plugin manifest description is rewritten off the stale "invariant checks are
  model-reported ... until ... land" hedge — the scanner, byte-exact 3-layer verifier, and apply are
  all wired as of v0.2. **v0.2 epic #16 complete:** live model-in-the-loop audit → verify → suggest →
  apply for any UTF-8 text document.
- **0.1.13** — live audit/suggest end-to-end validation golden (#28). A `tests/test_e2e_validation_golden.py`
  drives the real command surface (`assemble.py audit` + `run`) on a fixture and asserts the full
  **safety** contract, not just output shape: a safe in-range invariant-preserving repair is ACCEPTed,
  and every unsafe-edit class is BLOCKED — number/modality invariant weakening (`entry_weakened`),
  protected-span violation, and locality violation (`edit_locality`) — via the real deterministic
  verifier. A `SLOPSLAP_LIVE`-gated case asserts the live semantic layer blocks a meaning-change
  (skipped without a model). Test-only; no production change (the seam + verifier already exist).
- **0.1.12** — one-shot manual voice sample (#24). A user can paste a short voice sample inline with a
  suggest/apply request; `scripts/slopslap_scan/voiceprint.py::extract_voice_features` returns
  **measure-only** diction signals (register / contraction rate / punctuation profile /
  first-second-third-person lean) used ONLY to bias the choice among ALREADY-SAFE phrasings. No
  persistence, no learning, no hook (that's the deferred v2 capture). The voiceprint's fixed place in
  the authority order — `protected > invariants + no-fabrication > genre > current instruction > voiceprint >
  default` — means it never authorizes an edit, never widens a boundary, and never adds
  fragments/profanity to long-form to match a sample; the keystone holds. SKILL.md + suggest.md carry
  the contract; voiceprint.md already pointed here.
- **0.1.11** — apply command **enabled** (#29, WF5 F4 enablement half). The v0.1.8 dry-run write-fence
  is removed; the mutating path is reached via an explicit `apply` CLI subcommand
  (`assemble.py apply --path … --edits …`) — `run` stays dry-run-only (the safe default preview), so a
  real file mutation can never be triggered by a flag typo. Every apply stays **backup-gated +
  verifier-gated**: it mutates only after a mandatory verified backup and the 3-layer verifier both
  pass, and fails closed on a backup failure. `commands/apply.md` rewritten from the disabled
  `mutation_unavailable` sentinel to the real flow (dry-run-first, exit-code contract 0/2/3/4, "never
  claim an unconfirmed mutation"). Offline (`SLOPSLAP_LIVE` unset) apply rests on the deterministic
  layers only and says so — a real write on a non-live semantic layer emits an "applied on the
  deterministic layers only" warning + `semantic_mode`; set `SLOPSLAP_LIVE=1` for a model-verified
  apply (adversarial-diff fold). Reviewed: Opus diff PASS + Codex adversarial diff (3 High + 1 Med
  folded). Live safety golden is #28.
- **0.1.10** — apply write-strategy hardening (#21, WF5 F4). The backup-gated apply engine's model-C
  edge cases are closed with failure-injection tests: **hardlinked** sources are refused fail-closed
  (before the backup, and re-checked at the pre-replace boundary — a link created mid-flight can't
  slip through); the file **mode is preserved exactly** via `os.fchmod` (umask-independent; a platform
  without `os.fchmod` degrades to owner-only 0o600 + a warning rather than crashing); **symlinks** are
  followed to their target and reported; **extended attributes** (xattr/ACL/security labels), lost
  across the inode replacement, are detected and warned; **EXDEV** and any `os.replace` failure abort
  cleanly and never copy over the live source. The misleading "in-place" spec prose is rewritten to
  "backup-first, staged, verified, atomic pathname replacement" (SKILL.md, commands/apply.md,
  backup.py metadata policy). No `os.chown` (ownership-change scope creep / partial-chown hazard,
  dropped). Durability still requires `SLOPSLAP_FSYNC=1` in production (opt-in default is a sandbox
  workaround; read-back is the correctness net). The apply COMMAND remains disabled pending enablement
  (#29). Strategy peer-settled model C; design adversarially reviewed (4 High + 3 Med folded).
- **0.1.9** — suggest's invariant-check is now the **deterministic verifier**, not a model claim (#23,
  WF5 F2 deterministic half). The suggest command routes its proposed diff through the #27 seam and
  presents `slopslap_verification`'s real `verify` verdict (Layers 1+2 — numbers, units, modality,
  negation, conditions, protected spans); a diff that violates an invariant is BLOCKED regardless of
  any model. Retires the "model-reported / verifier arrives in a later increment" language in
  `SKILL.md` and `references/engine.md`. Deterministic tests lock verifier input construction, verdict
  handling, and rejection behavior (modality / negation / protected-span violations blocked with no
  model in the loop) + the CLI entry path. No new production logic — the wiring is the #27 seam; this
  makes the suggest *contract* authoritative. (The `plugin.json` description's stale "model-reported"
  clause is retired in #25 per the v0.2 plan.) Live semantic golden is #28.
- **0.1.8** — live-orchestration seam, the assembler (#27). New `scripts/slopslap_assemble/` chains
  **audit → verify → (suggest) → apply** end-to-end for an ARBITRARY document — the missing seam
  the v0.2 epic needs (WF5 finding F1: `#17–#24` were components with no assembler). `build_manifest`
  derives a `build_ledger` manifest from any UTF-8 doc; `audit_document` packages a
  snapshot-immutable `AuditResult` (genre resolved once and threaded to both the metrics run and the
  range deriver; `audit_status` `clean`/`flagged` preserved distinct from the `reject_all`
  authorization overload); `run_candidate` / `assemble` validate a candidate edit-script (parse +
  bounds/overlap BEFORE verify), re-check source identity at the run boundary (path + digest, so an
  `AuditResult` can't be replayed against a different file with identical bytes), run the 3-layer
  verifier with the derived authorization ranges, and (dry-run) route the shippable subset through
  the backup-gated apply engine — re-verifying against the untouched original each attempt. Uniform
  stage envelope (`ok | blocked | failed | aborted`) + a `RunResult` whose exit code is a static
  class map (0 ok · 2 policy-blocked · 3 invalid input/contract · 4 execution failure); a semantic
  INVOCATION failure (`semantic_invocation_failed`, exit 4) is kept distinct from a policy block
  (exit 2) via an additive, default-inert `status_sink` out-param on `invoke_semantic`. Thin JSON
  CLI (`assemble.py audit|run`) emits exactly one `RunResult` with no source bytes (ledger as
  `{canonical, sha256}`). Ships with an end-to-end dry-run acceptance golden (ACCEPT flows clean +
  REJECT blocks mutation, offline stub; the source stays byte-identical). `run` is dry-run only
  (`write=False`) until the apply-flip (#29). `SLOPSLAP_LIVE=1` selects a real fresh-context
  `claude -p` semantic pass; offline (default) uses a hardcoded `clean` stub — no model call.
- **0.1.7** — genre classifier + genre-constrained diagnoses (#22). Genre is no longer inert. New
  `scripts/slopslap_scan/genre.py::classify_genre(doc: bytes, *, declared=None, path=None)` returns
  `{genre, confidence, reason}` over `general · spec · prd · personal`, honoring the
  `references/genre-profiles.md` precedence (explicit declaration > file/repo context > structural
  markers > content inference) and the asymmetric-failure fallback (no usable signal → the
  most-preservation-heavy profile, **spec**). Genre now ACTUALLY constrains diagnosis via a new
  `metrics.compute_all(..., genre=None)` seam (threaded through
  `diagnoses.authorized_ranges_from_diagnoses(..., genre=None)`, so it reaches `verify`'s locality):
  **spec** suppresses the parallelism/repetition cadence flags (`negative_parallelism`,
  `rule_of_three`, `repeated_openers`) that would flatten a spec's intentional repetition;
  **personal** suppresses those plus `punctuation_rates` (em-dashes/cadence are the voice);
  **PRD** adds an `adjective_requirements` laundering candidate ("must be fast") but never flags
  aspiration/vision language (no vision-policing). Suppression flips `soft_flag`→False and clears
  `locations` (with a `suppressed_by_genre` marker) while `count`/`rate` stay as-measured — the
  scanner never lies about what it counted, it only re-scopes what is an editing candidate. Genre
  NEVER authorizes an edit or weakens a hard invariant / protected span (keystone rule); it only
  re-weights candidate selection. Default (`general` / `genre=None`) output is byte-identical to
  0.1.6. Non-UTF-8 fails loud (`GenreError`).
- **0.1.6** — live passage-local locality from diagnoses (#20). New
  `scripts/slopslap_scan/diagnoses.py::authorized_ranges_from_diagnoses(doc: bytes, fmt="markdown")`
  derives `[{start_byte, end_byte}]` byte spans of the DIAGNOSED passages — every eligible
  `extract.Unit` a scanner metric emitted a per-passage `locations` entry for (any confidence
  tier; the scanner is candidate-selection-only) — and feeds them straight to
  `verify(..., authorized_ranges=<result>)` so `gates.edit_locality` is enforced DETERMINISTICALLY
  on a live doc. Previously locality only fired on a hand-authored fixture `editable_ranges`; a
  live doc had none, so `authorized_ranges=None` left it prompt-guided (the `locality_unverified`
  ASK, #17). An edit inside a diagnosed passage passes locality; an edit outside every derived
  range REJECTs. The three doc-level metrics (sentence-length distribution/dispersion, punctuation
  rates) carry no per-passage location and never contribute a range — no fabrication; a doc with
  no located diagnosis yields `[]` and verify then REJECTs any edit (a clean doc is left alone).
  Byte offsets are exact (UTF-8 line-start table, not char) and non-UTF-8 fails loud
  (`DiagnosisError`); the markdown path is version-checked in-process like `protected.py`.
- **0.1.5** — invariant-ledger auto-build for arbitrary prose (#19). New
  `scripts/slopslap_verification/autoledger.py::build_invariant_regions(doc: bytes)` derives
  manifest `invariant_regions` from arbitrary UTF-8 prose — numbers+units, dates, normative modals
  (MUST/SHALL/SHOULD/MUST NOT), negation, conditions, cross-references, and defined terms (explicit
  definitional phrases only — markdown bold is emphasis, not a definition) — instead of
  hand-declaring them. It REUSES the `atoms.py` detectors (no second parser) and defers
  kind/preservation/confidence to the ledger's `_CHECK_KIND` R3 table (extended with `cross_refs`
  and `defined_terms` checks). Segmentation is sentence-level so a multiset-preserving edit is
  checked against the whole sentence; byte offsets are exact (UTF-8, not char) and non-UTF-8 fails
  loud (`LedgerBuildError`). Output drops straight into `build_ledger`, and a weakening edit
  (a changed number, a MUST→SHOULD downgrade) then REJECTS at verify.
- **0.1.4** — protected-span auto-extractor for arbitrary input (#18). New
  `scripts/slopslap_scan/protected.py::extract_protected_spans(doc: bytes)` REUSES the scan
  tokenizer (the vendored/pinned markdown-it parser + `extract.py`'s URL matchers) to emit
  `protected_spans[]` of `{start_byte, end_byte, sha256, kind}` — covering code fences, inline
  code, URLs/link destinations, blockquotes, and identifiers — for **any UTF-8 text** document,
  instead of the fixtures + kukakuka PRD being hand-authored. Byte offsets are exact (UTF-8, not
  char) and spans are pairwise non-overlapping, so the output drops straight into `build_ledger`;
  a bad edit inside an extracted span then REJECTS at verify. Fails loud (`ProtectedSpanError`) on
  non-UTF-8 input or an unavailable pinned parser rather than silently mis-/under-protecting; an
  escape-unaware inline-code count mismatch skips that block's inline code with a logged warning
  (observable, never silent).
- **0.1.3** — eval exercises Layer 3 end-to-end (#17): the "working proof" now drives the full
  fold on the kukakuka PRD through the real Layer-3 semantic seam, not just Layers 1–2. `_kukakuka()`
  passes the seeded candidate's demonstrated repair spans as the authorized editable ranges and a
  `semantic_fn`, so the fold reaches a **shippable `ACCEPT`** (`semantic_status: clean`,
  `proposal_status: ACCEPT`) with **zero invariant violations** preserved. New helper
  `scripts/eval/semantic.py::eval_semantic_fn` binds `functools.partial(invoke_semantic, …)` LIVE
  (env `SLOPSLAP_LIVE=1` — a real fresh-context `claude -p` pass) and OFFLINE (default) returns a
  hardcoded `clean` stub — no recording artifact, the frozen faithful candidate is asserted clean —
  so the proof stays reproducible without a model call (offline it exercises the fold plumbing, and
  the candidate-span locality + clean verdict pass by construction; the real semantic judgement is
  the `SLOPSLAP_LIVE=1` path). A new DONE criterion (`kukakuka_l3_shippable`) and the
  `semantic_status`/`proposal_status`/`decision` fields are surfaced in the results object and both
  rendered reports.
- **0.1.2** — corpus integration (#30): a provenance-first, lane-separated foundation for the
  before/after AI-slop corpus. `scripts/slopslap_corpus/` adds a fail-closed manifest loader
  (`manifest.py`) and a **source-family** disjoint split (`split.py`) — the leak guard is keyed
  on `source_family`, not passage or content hash, so near-duplicate passages can never scatter
  across the calibration/held-out boundary. `research/ai-slop-corpus/corpus_manifest.jsonl`
  catalogs the corpus per ITEM with license assigned from each item's real origin (never per
  file-number): Wikipedia (CC BY-SA, share-alike) and humanizer (MIT, CC-BY-SA derivative) as
  fixture/calibration lanes; commercial blogs + research datasets as `inspiration` (metadata
  only, zero verbatim bytes). Two-sided licensing + hash-drift tests
  (`tests/test_corpus_licensing.py`) fail closed in both directions. Five authored thin-tell
  fixtures (`tests/fixtures/eval/authored-*`) exercise the eval loader + `verify()` unchanged —
  semicolon, false-range, voice-seam, laundering-question — plus a **negative preservation
  anchor** whose fabricated number drives `verify()` to REJECT via `no_new_claim_atoms`, proving
  it can never become a golden.
- **0.1.1** — platform-feasibility spike (epic #16 / #26): `scripts/slopslap_invoke/` proves ONE
  fresh-context model invocation under the real plugin config — a subprocess `claude -p` adapter
  (`invoke_semantic`) that feeds the Layer-3 `verify(semantic_fn=…)` seam. Fresh context is
  machine-proven (the CLI `init` event reports zero tools + zero MCP servers under
  `--tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}'`; a sentinel-file positive
  denial test confirms no file access). Every transport/parse/timeout failure fails closed to
  verdict `ambiguous` (never a silent `clean`); one live invocation + a recorded fixture are
  checked in (`tests/fixtures/invoke/`), with a `SLOPSLAP_LIVE=1`-gated integration test.
- **0.1.0** — MVP: eval fixtures + two-stage runner; plugin scaffold (SKILL + commands +
  references); measure-only scanner with a vendored CommonMark parser; invariant ledger + 3-layer
  verify + decision rule; backup-gated apply + per-hunk selective rollback; the eval loop RUN
  (working proof); scanner cadence metrics (negative-parallelism / rule-of-three / punctuation
  density).

## Layout

```
.claude-plugin/plugin.json   manifest
skills/slopslap/SKILL.md      the judgment (keystone + loop + taxonomy + modes)
commands/                     audit · suggest · apply · voiceprint
references/                   tell-taxonomy · genre-profiles · engine · scanner-metrics · invariant-ledger · eval-cases
scripts/scan_prose.py         measure-only scanner (CLI)
scripts/slopslap_scan/        scanner adapter + metrics + protected-span extractor
scripts/slopslap_verification/ ledger + 3-layer verify + edit-map
scripts/slopslap_apply/       backup + selective apply
scripts/eval/                 fixtures runner + candidates + run_eval
vendor/python/                pinned markdown-it-py + mdurl (THIRD_PARTY_LICENSES/)
tests/                        pytest suite (the `pytest -q` gate)
```
