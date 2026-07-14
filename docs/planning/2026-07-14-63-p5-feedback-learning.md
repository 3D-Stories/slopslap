# P5 (#63) — feedback ledger + learning (recommendations only; authorization never learns)

**Epic:** #57 de-slop pivot · **Deps:** P4 (#62, decisions flowing) + #31a (semantic-verifier neutrality) — both merged.
**Parent design:** `docs/planning/2026-07-13-deslop-pivot-design.md`. This note is the implementation design for the P5 child.

## The loop this closes

`detect (universal) → recommend (genre + learned) → review (user decides) → apply (approved hunks) → **learn**`.
P5 adds the final arrow: the user's review decisions feed a local ledger, and the ledger tunes the
*recommendation* the next review shows — never the authorization, never the verifier.

## Invariant (the keystone's teeth) — how "authorization never learns" is made true

`metrics.recommend(genre, metric)` feeds **three** sites: findings-build (the review recommendation),
`diagnoses._diagnosed_line_ranges`, and `assemble.authorized_ranges_from_diagnoses` (the audit-time
authorization ceiling). If learning touched `recommend()` itself, it would leak into the authorization
ceiling. So:

1. **`metrics.recommend()` stays PURE** — genre-only, no learning parameter. All three sites keep
   calling the identical pure function.
2. **The learned overlay is applied ONLY at findings-build** (`findings.build_findings`, the
   recommendation the user reviews) via a separate `learn.apply_overlay(base_rec, …)` helper. It is
   imported by `slopslap_review.findings` and NOWHERE in `slopslap_assemble` / `slopslap_verification`.
3. **The overlay is keep-only** — it can flip a `strip` recommendation to `keep`, NEVER `keep→strip`.
   So learning can only make the tool *more conservative* (shrink the strip set). This is the same
   monotonicity direction #59's genre-keep proof established: learning can never authorize an edit that
   was not already generally authorized; it can only propose fewer.
4. On the apply path, authorization already comes from the **user's accepted findings** (#62), not the
   genre/recommendation gate. Learning changes what the user *sees*; the user still decides; the
   byte-exact verifier still hard-gates. Three tests pin all of this.

## Components

- **`slopslap_review/feedback.py`** — the ledger writer/reader/purge.
  - `feedback_path()` → `$XDG_STATE_HOME/slopslap/feedback.jsonl` (default `~/.local/state/…`).
  - `append_feedback(decisions_payload, findings, genre, *, path=None, now=…)` — one schema-valid
    JSONL line per decision (`schema.validate_feedback_line` must pass). **Hashed span:** the ledger
    `finding_id` is `"{metric}:{sha256(start:end)[:16]}"` — the position is hashed, so the ledger
    carries no reconstructable offsets (local + purgeable; `doc_sha` identifies the doc, learning keys
    on `(genre, metric)` only). `replacement` (b64) is kept only for `edit` (local, purgeable).
  - `reset_feedback(path=None)` — unlink the ledger (the `slopslap feedback reset` purge).
  - `read_feedback(path=None)` — yield validated lines; malformed lines are counted + skipped, never
    crash learning.
  - Wired best-effort into `assemble.apply_from_decisions` (apply is where the review's decisions are
    finalized); a write failure is logged and NEVER fails the apply.
- **`slopslap_corpus/learn.py`** — the ledger consumer.
  - `learn_from_feedback(lines, *, min_evidence=3) -> Overlay`. Per `(genre, metric)` it accumulates
    **keep-evidence**: a `false_positive` discard (weight 1), a strip-override discard
    (`recommendation=="strip"` + `user_action=="discard"` with a keep-ish reason, weight 1), and an
    `edit` of a strip rec (**partial-accept, weight 0.5** — kept tokens are real claims). When the
    weighted keep-evidence for a `(genre, metric)` reaches `min_evidence`, that metric's **class** is
    added to `overlay.keep_classes[genre]` (a strip→keep flip for the whole class in that genre).
  - `apply_overlay(base_rec, genre, metric, overlay) -> str` — keep-only: returns `keep` iff
    `base_rec=="strip"` AND the metric's class is in `overlay.keep_classes.get(genre)`; otherwise
    returns `base_rec` unchanged. Never turns `keep` into `strip`.
  - **P0-schema honesty:** the AC asks false-positive marks to "raise that metric's threshold." The
    frozen P0 feedback schema (#58) carries no per-finding rate/value field, and the ledger stores no
    doc text to re-scan — so a *numeric* per-rate threshold is not derivable here. We realize the
    threshold-raise as its conservative LIMIT: a class-keep flip (stop recommending strip for that
    metric+genre). A data-driven numeric threshold needs a `rate` field the P0 schema froze without —
    recorded as a v2 schema refinement, not silently faked.
- **`slopslap_review/findings.py`** — `build_findings(audit, doc, *, overlay=None)` threads the overlay
  into the single `recommend()` seam at line 166 via `apply_overlay`. `overlay=None` → byte-identical
  to today.
- **Voice-floor** — no new machinery (persistent voiceprint stays deferred v2). It falls out of the
  overlay: in the `personal` genre, repeated keeps of the `voice_punctuation`/`cadence` classes flip
  those classes to keep — protecting a demonstrated voice from aggressive defaults. #31a guarantees a
  voice signal can never bias the verifier; a test asserts a learned voice-keep only changes the
  recommendation and never reaches authorization/verify.
- **CLI + command** — `slopslap_review/feedback.py` gains a `main()`: `feedback reset` (purge),
  `feedback path` (print the ledger path), `feedback show` (print the learned overlay). New
  `commands/feedback.md` (keystone + untrusted-data guard + skill reference); `feedback` added to the
  scaffold command list + skill `mode-feedback` anchor.

## Tests (TDD, red-before-green)

1. writer: a decisions payload → N schema-valid lines; span is hashed (no raw offsets); `edit` keeps a
   b64 replacement; `reset` purges; malformed lines skipped by the reader.
2. learn: FP discard → keep flip at threshold; strip-override → keep flip; edit = 0.5 partial (two
   edits reach the bar, one does not); below-threshold does NOT flip; unknown metric ignored.
3. **invariant (HIGH):** (a) `apply_overlay` is keep-only over the whole `(genre,metric)` table —
   never `keep→strip`; (b) a populated ledger does NOT change `apply_from_decisions` authorized ranges
   (authorization derives from user decisions, not learning); (c) grep/import test: `learn.apply_overlay`
   is not imported by `slopslap_assemble` / `slopslap_verification`.
4. voice-floor: a `personal` ledger of voice-punctuation keeps flips that class to keep in the review
   recommendation, and that flip never propagates to authorization/verify.

## Out of scope (explicit)

- Numeric per-rate threshold learning (needs a P0-schema `rate` field — v2).
- Persistent voiceprint capture hook / UserPromptSubmit (deferred v2, per README).
- Promoting learned thresholds into the scanner (`calibrate` stays measure-only).
