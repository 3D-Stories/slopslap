# slopslap de-slop pivot — detect everything, recommend by genre, user decides, learn from feedback

**Date:** 2026-07-13 · **Base:** v0.2.2 · **Status:** design v2 — **RATIFIED** (owner, 2026-07-13:
keystone v2, apply/edit/discard review, de-claim alternatives, rec-action buttons, learning loop)
**Supersedes** the v0.3 hardening-only roadmap as the primary line; that plan
(`2026-07-13-v03-hardening-and-voiceprint-plan.md`) becomes secondary backlog with three items
pulled forward (#31a, #43, #31b — the verifier becomes load-bearing for whole-passage rewrites).

## The decision (owner, verbatim intent)

1. **"Better than humanizer" means MORE than humanizer, not more timid.** v0.2's keystone forbade
   touching stylistic tells; that was the wrong reading. Confirmed: aggressive, verifier-safe,
   genre-gated.
2. **Detect everything, everywhere.** Genre no longer suppresses *detection*. Every tell and slop
   signal becomes a **finding**, prepared with a strip-ready rewrite.
3. **Genre gates the RECOMMENDATION, not the finding.** Each finding carries a genre-gated
   recommendation (strip / keep) + rationale.
4. **The user is the final gate — apply, EDIT, or discard.** A **review stage** lets the user apply
   or discard ANY finding — including overriding a "keep" to strip and a "strip" to keep — and
   **modify the proposed rewrite** before applying (owner example: adjective-pile proposal
   "robust, scalable, and innovative" → "distributed", hand-tuned to "innovative distributed" when
   "innovative" is a claim the author stands behind). A user-edited replacement routes through the
   SAME verifier gate as a machine proposal.
5. **It learns.** User decisions, false-positive marks, and "this genre should have included X"
   corrections feed back into the plugin and tune the genre-gated recommendations over time.

## Why slopslap wins this fight

Humanizers strip hard and break facts — mangle a number, drop a `MUST`, invent a claim. slopslap's
moat was never the timid policy; it is the **byte-exact invariant verifier**. Keep it, and the
product is: *strip the slop-voice as hard as any humanizer, with a machine guarantee that no number,
requirement, negation, condition, or protected span changed.* No humanizer can promise that.

## Keystone v2 (RATIFIED by the owner 2026-07-13 — P0 gate cleared)

> **Every tell is detected and prepared for removal; genre and learned feedback set each finding's
> recommendation; the user's review decision — not the scanner, not the genre, not the learning —
> authorizes the edit; and the byte-exact verifier guarantees no applied edit changes a number,
> requirement, negation, condition, defined term, or protected span. Recommendations may learn;
> authorization never does.**

Notes on the inversion:
- Detection is now universal (old keystone forbade scanner-driven action; new one channels it into
  findings + recommendations).
- Authorization moves from "demonstrated harm only" to **the user's explicit per-finding decision**
  (batch modes may later allow "apply all recommended-strip", still a user decision).
- The verifier stays the hard gate even over user-approved edits: an approved strip that would break
  an invariant is **blocked and surfaced**, never silently applied.
- **Blast radius:** the keystone sentence is pinned verbatim in `tests/test_scaffold.py`, SKILL.md,
  and all four command files — they rewrite together in Phase 1.

## The new loop

```
detect (universal) → recommend (genre + learned feedback) → REVIEW (user decides per finding)
      → apply (approved hunks only, verifier + backup gated) → learn (decisions feed calibration)
```

### 1. Detect — universal
- `GENRE_SUPPRESS` (metrics.py:277) polarity flips: genre never zeroes a metric's locations again.
  Suppression survives only inside the *recommendation* layer.
- Every finding ships **strip-ready**: `{id, category, span(start,end), evidence, genre,
  recommendation: strip|keep, rationale, confidence, proposed_rewrite, verifier_precheck}` — the
  proposed rewrite is pre-cleared through verifier Layers 1+2 where possible, so the review UI can
  show "safe to strip" vs "strip would be blocked" per finding.
- **New detector (the "finds more" payload):** generic diction + filler — stock openers ("In today's
  fast-paced world", "it is important to note"), corporate adjective piles (robust · scalable ·
  innovative · best-in-class · seamless · leverage · empower), empty intensifiers. This is where
  v0.2 found nothing.

### 2. Recommend — genre-gated, learning-tuned, with de-claim alternatives

**Alternatives menu (owner-directed 2026-07-13).** Claim-carrying findings (`simulation`,
laundered superlatives) don't reduce to strip-or-flag. Each such finding offers a small menu:

1. **strip** — delete the claim ("delivers results").
2. **flag** — keep + annotate the missing support.
3. **de-claim rewrites (1–3 candidates)** — keep the evocation, drop the unverifiable assertion:
   - *subjectivize* (asserts nothing external): "best-in-class results" → "results we stand behind";
   - *describe intent/design* (no ranking claim): → "built to deliver fast, accurate parses";
   - *scope to the verifiable* (claims only what the doc/system can support): → "results that pass
     the full 3-layer verification suite".

**Hard rule — no lateral swaps:** an alternative may NEVER introduce a new unsupported factual
claim ("best-in-class" → "industry-leading" is a lateral swap, not a fix). Enforced by the existing
**Layer-1 `no_new_claim_atoms` gate**: a candidate whose claim atoms aren't in the original (or in
`allowed_claim_atoms`) is rejected by the verifier, machine-checked, not model-honor. Each
alternative in the review UI carries a claim-status chip ("no external claim" / "claims X — doc
supports it") so the user picks with eyes open; picking an alternative behaves like apply, and it
remains hand-editable before applying.
| genre | default recommendation for tells | rationale |
|---|---|---|
| general-prose, marketing | **strip** | the target case; corporate-slop voice killed |
| PRD (prose) | **strip** fluff; **keep** constraints/unresolved decisions | never assert a decision |
| technical-doc | **strip** filler; **keep** identifiers/exact terms | precision preserved |
| spec | **keep** (parallelism = correctness infra) | user can still override to strip |
| legal | **keep** (flag-only posture) | user override still possible, verifier still gates |
| personal | **keep** (voice-floor) | voice weighted high; user may strip anyway |
| low genre confidence | **keep** | asymmetric-failure rule, now advisory instead of absolute |

Learned feedback shifts these defaults per user over time (below). Recommendations are advisory
metadata — they never gate what the user can do.

### 3. Review — the interactive stage (owner-requested)
Two delivery mechanisms, one schema:

- **A. Local review server (product path).** `slopslap review <target>` → engine writes
  `findings.json`, serves a self-contained review page on `127.0.0.1:<random port>` (stdlib
  `http.server`; single-use token in the URL; binds loopback only; idle-timeout + shutdown after
  finish). The page lists every finding — evidence span in context, category, recommendation +
  rationale, the proposed rewrite, and the verifier precheck — with per-finding **apply / discard**
  (and reason-capture on discard: `false_positive | keep_voice | genre_wrong | other`). "Finish
  review" POSTs the decision set; the engine writes `decisions.json` bound to the audit's
  `source_sha256` and exits. No new dependencies.
- **B. Static export fallback (works as a claude.ai artifact / any browser).** Same UI; artifact CSP
  blocks POST, so "Export decisions" downloads / copies `decisions.json` to the clipboard; the user
  feeds it to `/slopslap:apply --decisions decisions.json`.

Review-stage rules:
- **The recommended action is always a labeled one-click button** — actions are named by their
  semantic outcome ("apply strip", "keep original", "keep + flag"), never by mechanism ("discard"),
  and the button matching the recommendation carries a visible `rec` badge. A recommendation that
  maps to no button is a UI defect (caught by the owner in the 2026-07-13 demo review).
- Per-finding actions are **apply / edit / discard**. `edit` opens the proposed replacement for
  hand-tuning; the edited text becomes that finding's replacement in the edit-script and is
  verifier-gated identically to a machine proposal (an edit that weakens an invariant is blocked
  and surfaced, exactly like an apply).
- The user can override ANY recommendation in either direction (strip a "keep", keep a "strip").
- Findings whose proposed rewrite failed the verifier precheck are shown as **blocked** with the
  reason (e.g. `entry_weakened e23_numbers`) — selectable only for the feedback signal, never
  applicable.
- `decisions.json` is UNTRUSTED input to apply: schema-validated, finding-ids matched against the
  audit snapshot, whole-file `source_sha256` binding (existing `digest_mismatch` machinery) rejects
  replay against a drifted file.

### 4. Apply — unchanged engine, new input
Only user-approved hunks route to `apply_selective`; the 3-layer verifier + mandatory verified
backup + atomic pathname replacement are untouched. A user-approved hunk the verifier rejects is
reported blocked (per-hunk selective rollback already exists).

### 5. Learn — decisions ARE calibration labels
The #25 calibration harness shipped measure-only because the corpus had **0 labeled points**. The
review stage manufactures exactly what it was starved of:

- Every decision appends to a local **feedback ledger** (`~/.local/state/slopslap/feedback.jsonl`):
  `{ts, finding_id, category, metric, genre, recommendation, user_action, replacement?, reason, doc_sha}`
  where `user_action ∈ {apply, edit, discard}` and `edit` carries the user's replacement.
- **Edits are the richest labels** — a hand-tuned replacement is a partial-accept that shows which
  tokens of the tell the user kept (e.g. keeping "innovative" out of an adjective pile = that word
  was a real claim, not filler, in that context). The tuner treats kept-token patterns as
  per-genre/per-metric evidence, worth more than a binary apply/discard.
- `slopslap_corpus.calibrate` consumes the ledger as labeled points: false-positive marks lower a
  metric's confidence / raise its threshold in that genre; repeated strip-overrides in a genre flip
  that genre's default recommendation for that tell ("genre exclusions that should have been
  included" — the owner's case).
- **Never auto-promote stays structural** for *authorization*: learning tunes recommendation
  defaults and thresholds only. The user gate remains final forever; the verifier remains the hard
  gate forever. (The #25 no-auto-promote design survives intact — it was about verdicts, and
  verdict-power now belongs to the user.)
- Privacy: the ledger stores spans' hashes + metric metadata, not whole documents; local-only;
  purgeable (`slopslap feedback reset`).

## Honest costs (stated on the tin)
- The verifier guarantees invariants, **not taste**: a rewrite can be invariant-clean and still
  flatten a nuance the ledger doesn't track. Bounded by: recommendations (keep-biased in voice
  genres), the user review gate (nothing applies unseen), Layer-3 semantic, and idempotence.
- The review UI is new surface (localhost server): loopback-only + token + shutdown; no remote
  exposure. Static fallback has no server at all.
- Learning is per-user local state — it will diverge across users/machines by design.

## Phases

- **P0 — gate (this doc).** Keystone v2 wording **ratified 2026-07-13**; remaining P0 work: freeze
  the decisions/feedback JSON schemas + eval strategy (slop→clean golden PAIRS; qa-* fixtures
  extended with paired before/after).
- **P1 — universal detection + findings schema.** Flip `GENRE_SUPPRESS` polarity into the
  recommendation layer; findings-with-recommendations envelope; keystone rewrite across SKILL.md +
  4 commands + `test_scaffold.py` (high blast, pinned sentence).
- **P2 — generic-diction/filler detector.** The "finds more" payload; calibrate via the corpus
  harness.
- **P3 — review stage.** findings.json → local review server + static-export fallback →
  `decisions.json` round-trip (schema + sha binding + untrusted-input validation).
- **P4 — apply-from-decisions.** Approved-hunks-only routing through the unchanged
  verifier/backup engine; blocked-hunk surfacing.
- **P5 — feedback ledger + learning.** Ledger, calibrate-consumption, per-genre recommendation
  tuning, `feedback reset`. The deferred voiceprint gets its real job here: protecting a
  demonstrated personal voice from aggressive defaults.
- **Pulled-forward hardening (verifier now load-bearing):** #31a semantic-verifier neutrality,
  #43 edit-script preimage, #31b injection suite. Secondary backlog: #47, #36, #46, #42, #31c–e.

Every PR: red-before-green, full suite vs recorded baseline, version bump + Changelog, files staged
by name, no merge without a scoped grant.
