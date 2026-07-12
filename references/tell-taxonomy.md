# Tell taxonomy — indicators + before/after (elaborates SKILL.md; adds no safety rule)

The authoritative categories, remedies, and prohibitions live in `skills/slopslap/SKILL.md`. This
file only gives richer indicators and worked examples. If anything here seems to permit more than the
SKILL allows, the SKILL wins — a reference never widens edit authority.

Every finding is still a **typed diagnosis record** and is classified only after harm + impact are
shown. Keep `emptiness` / `laundering` / `simulation` separate; their remedies differ.

## emptiness — words add nothing / restate context
Remedy: delete or compress, ONLY if no intent is lost.
- Indicators: "In today's fast-paced world…", "It is important to note that…", "plays a key role",
  restating the heading as a sentence, a paragraph that could be deleted with zero information loss.
- Before: *"In today's fast-paced world, it is important to note that logging remains a valuable and
  essential practice for developers."*
- After: *"Log at boundaries you'll actually grep."* (or delete, if the section already says it)
- NOT emptiness: a plain sentence that carries a real fact, even if simply worded. Simplicity ≠ harm.

## laundering — evaluative language posing as a requirement
Remedy: convert to a question or label non-testable. **Never delete** — it encodes real intent.
- Indicators: "the system should be robust / intuitive / user-friendly / seamless / best-in-class",
  adjectives standing in for a metric, a "requirement" with no observable pass/fail.
- Before: *"The API must be fast and easy to use."*
- After: *"[Requirement unclear] What is the latency budget and the target caller? 'fast/easy' is not
  testable as written."* (a question — the intent to be fast is preserved, not deleted)

## simulation — implies absent evidence / experience / completed work
Remedy: **flag** the missing support; do NOT repair it substantively or invent it.
- Indicators: "studies show", "it is widely known", "we have extensively tested", "users love",
  cited-sounding claims with no citation, described results that were never produced.
- Before: *"Extensive benchmarking shows a 10x improvement."* (no benchmark exists)
- After: *"[Unsupported] No benchmark is present. State the measurement or remove the '10x' claim."*
  Do not invent a number, a study, or a benchmark.

## lexical_structural — a lexical / structural / rhetorical / formatting tell
Remedy: candidate only; act ONLY when redundant AND the genre permits.
- Indicators: rule-of-three lists, negative parallelism ("not X, but Y"), repeated sentence openers,
  em-dash/semicolon runs, heading-per-paragraph density, bold-label lists. These are **signals, not
  harm** — a spec's parallelism is correctness infrastructure; a personal essay's em-dashes are voice.

## voice_discontinuity — a break in a document expected to have one voice
Remedy: evidence only when one voice is expected — NOT interviews, RFCs, quotes, changelogs, or
marketing sections that legitimately shift register.

## epistemic_distortion — false confidence, hedge-piles, passive hiding the actor
Remedy: repair WITHOUT inventing an actor or deleting necessary hedging.
- Before: *"Mistakes were made and the data was affected."*
- After: *"The migration script dropped column X."* — only if the doc already establishes who ran it;
  otherwise flag the missing actor, never invent one.

## Second-order failures to avoid (see `references/eval-cases.md`)
diagnosis-theater · taxonomy-leakage (printing "specification-laundering" at the user instead of plain
language) · scanner-anchoring (treating a soft metric flag as proof) · non-native normalization ·
dialect suppression · uncertainty deletion · responsibility reassignment · vision-policing ·
question-explosion · iterative-sanding · diff-fragmentation · false-idempotence.
