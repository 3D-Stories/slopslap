# Voiceprint for slopslap — Claude's independent design (pre-Sol-round-2)

## The reframe that changes everything: the voiceprint is DEFENSIVE, not generative

The obvious reading of "learn how I talk and write like me" is *generative* — reproduce
the user's voice in rewrites. That's the weak framing, because (a) it's what a prompt
corpus is worst at, and (b) it invites caricature.

The strong framing: in a **slop-stripping** tool, the voiceprint's primary job is a
**whitelist of the user's genuine habits so the stripper doesn't delete real voice as
AI-tell.** Humanizer's core flaw is it can't tell the user's deliberate em-dash from an
AI em-dash, so it flattens both. A voiceprint that says "this author uses em-dashes,
fragments, and the word 'honestly' deliberately — those are NOT tells for him" directly
fixes the over-correction failure mode. It's mostly **permissive/subtractive** ("leave
this, it's his") not **additive** ("inject his tics"). That's safer, more honest, and
uses the prompt corpus for exactly what it's good at.

So: the voiceprint SUBTRACTS from the tell-list per-author before stripping, and only
secondarily biases diction toward the user's register. It never manufactures voice.

## Source honesty: what a prompt corpus can and cannot teach

Prompts are the appealing corpus (continuous, free, zero-effort) but a BIASED sample:
- Register mismatch — prompts are terse imperatives ("fix this", "cut the PR"); the prose
  slopslap edits is long-form expository. Prompt-voice ≠ prose-voice.
- Mode artifacts — prompts have typos, lowercase, dropped apostrophes ("cant", "u").
  These are prompt-MODE, not desired prose style. Learning them as style = disaster.
- Domain-noun bleed — prompts are full of project nouns (rawgentic, WF2). Not voice.

**Therefore split features into two zones + honest UNKNOWNs:**
- **Register-invariant** (transfers prompt→prose): diction level, hedging vs commitment,
  directness, humor/edge, profanity tolerance, concrete-vs-abstract preference, genuine
  pet phrases.
- **Prompt-mode-only** (observed, flagged DO-NOT-APPLY-to-prose): typos, lowercase,
  dropped apostrophes, extreme brevity.
- **UNKNOWN from prompts** (never guessed): long-form paragraph rhythm, prose punctuation
  habits, section structure. Marked explicitly unknown, not fabricated.

**Better corpora (recommend beyond prompts):**
1. Prompts → seed the register-invariant layer (auto, continuous).
2. **Accepted rewrites** (slopslap output the user keeps/tweaks) → the GOLD signal: the
   user endorsing prose in their voice. A real feedback loop; teaches the prose layer.
3. **Opt-in long-form samples** (user points at their real writing) → the only thing that
   teaches rhythm/structure. Best source for what prompts can't give.

Honest verdict: a prompt-ONLY voiceprint is a WEAK, low-confidence voiceprint useful
mainly for the defensive whitelist + diction; the prose layer needs (2)/(3).

## Representation: an inspectable descriptor, not embeddings/fine-tuning

Human-readable, editable file the model reads as context. Each feature carries a VALUE +
CONFIDENCE + SOURCE + EVIDENCE, so it's debuggable and correctable. Sketch:

```
# voiceprint (slopslap) — <user> — updated <date>, N=<prompts>, M=<accepted rewrites>
## register-invariant (apply to prose)
contractions:  uses            conf:high  src:prompts+rewrites  ev:"can't","don't"
hedging:       low/commits      conf:high  ev:"X is wrong","just do it"
directness:    high, imperative conf:high
humor:         dry, occasional  conf:med
profanity:     casual-ok / shipped-docs-no  conf:med
diction:       plain>ornate; concrete>abstract  conf:high
pet_phrases:   ["honestly","the thing is"]  conf:low  (permit, don't inject)
## prompt-mode-only (DO NOT apply to prose)
lowercase_starts, dropped_apostrophes, 5-word-fragments  — artifacts, ignore for prose
## unknown (needs long-form corpus)
prose_rhythm: UNKNOWN   prose_punctuation: UNKNOWN   section_structure: UNKNOWN
## pinned (user-asserted, never auto-overwritten)
(empty)
```

## Update mechanism: buffered distill, recurrence-gated, decaying

- NOT per-prompt (noisy/expensive). A **buffer** accrues prompts; a **periodic distill
  pass** (every N prompts or on demand) updates the descriptor.
- Two-stage distill: a cheap **deterministic script** computes the measurable facts
  (contraction rate, profanity presence, punctuation freq, top non-domain content words,
  prompt sentence-length stats) → then an **LLM pass** turns the buffer + facts into the
  qualitative fields, explicitly separating stable traits from mode-artifacts.
- **Recurrence gate:** one swear ≠ "profane style"; promote a trait only on a pattern
  across many prompts. Single samples never flip a high-confidence field.
- **Recency-weight + decay:** recent prompts weigh more; stale traits fade — style drifts
  slowly, so track it slowly.
- Versioned/append so drift is auditable.

## Precedence: voiceprint governs HOW, never WHAT

Strict order at rewrite time, voiceprint near the bottom:
**invariant ledger (claims/numbers/modality) > genre profile (a spec stays a spec) >
voiceprint (register/cadence/diction) > neutral default.**
Genre gates WHICH voiceprint features even apply: personal essay → full voiceprint;
normative spec → diction-level only, no humor/fragments/profanity. A maximally-learned
voiceprint can't make a legal clause casual or inject a tic into a requirement.

## Anti-caricature guards
- Permissive not additive (whitelist habits to KEEP; don't sprinkle tics).
- Confidence-gated: thin corpus → lean neutral default, apply only high-conf invariant
  traits; grows with corpus.
- Domain nouns stripped from diction analysis.
- slopslap SHOWS applied traits ("kept your em-dashes per voiceprint") → auditable.

## Storage / consent / control
- Local, per-user file (e.g. `~/.claude/slopslap/voiceprint.md`), never leaves machine.
- **Opt-in** — capturing prompts is sensitive; off by default.
- Inspectable + editable; `pin` a user-asserted trait (never auto-overwritten); `reset`.

## Capture mechanism (honest architectural note)
The slopslap SKILL can't capture prompts by itself. Prompt-learning needs a companion
**UserPromptSubmit hook** that appends prompts to the buffer (same hook pattern rawgentic
uses for mempalace recall). That hook is an opt-in install, separate from the skill.

## Staging: v1 manual, v2 learned
- **v1 (MVP):** manual voice calibration — user pastes/points at a sample (humanizer
  already does this); + neutral default. No learning, no hook. The defensive whitelist
  works from a pasted sample immediately.
- **v2:** the auto-learned, evolving voiceprint (prompt hook + accepted-rewrites loop +
  distill/decay). Deferred because it needs the core engine working AND slopslap-in-use
  to generate the accepted-rewrites signal.

## Failure modes → guard
| Failure | Guard |
|---|---|
| Learns typos/lowercase as style | register-invariant vs prompt-mode-only split; prose habits UNKNOWN |
| Caricature (over-applies tics) | permissive-not-additive + confidence gates |
| Domain-noun bleed | strip project/technical nouns |
| Staleness | recency-weight + decay |
| Privacy | opt-in, local, inspectable, deletable |
| Wrong voiceprint edits toward wrong voice | inspect/pin/reset + show-applied-traits |
| Voiceprint overrides meaning/genre | strict precedence: ledger>genre>voiceprint>default |
