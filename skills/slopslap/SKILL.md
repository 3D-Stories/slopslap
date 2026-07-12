---
name: slopslap
description: Use when asked to repair, de-slop, tighten, or edit prose (essays, specs, PRDs, ADRs, READMEs, docs) for editorial quality WITHOUT losing meaning, requirements, uncertainty, or the author's voice. Diagnoses genericness, unsupported claims, synthetic cadence, obscured responsibility, and voice discontinuity, then proposes minimal passage-local repairs. NOT an AI-authorship detector — never strips a stylistic feature just because it looks AI-written. Triggers: "de-slop this", "make this less generic", "tighten this doc", "is this AI-slop?", "edit this without flattening my voice", "audit/suggest/apply".
---

# slopslap — repair editorial harm, preserve everything else

<!-- anchor:anti-slap -->
**FIRST, AND ABOVE EVERYTHING ELSE: repair only demonstrated editorial harm; do not punish prose
for matching a stylistic tell.** The name says "slap" — ignore that impulse. An em-dash, a
fragment, a tricolon, the word "delve", a passive verb: none of these is harm. Harm is when the
prose does less than it claims, hides who is responsible, asserts what it has not shown, or buries
its own meaning. You are here to remove *that*, and to leave a distinctive human voice more intact
than you found it. When in doubt, change nothing.

<!-- anchor:keystone -->
## Keystone rule (governs everything)
**Edit authorization comes only from demonstrated editorial harm; the scanner, genre, ratings, and
voiceprint never authorize an edit.** Diagnosis authorizes the SCOPE of an edit; genre and voiceprint
only choose among already-safe REALIZATIONS. None of them may independently authorize an edit or widen
its boundary. This is the anti-normalization guard: "make it sound better / like me" can never become
whole-document rewriting.

<!-- anchor:protected-spans -->
## Protected spans (default-DENY edits)
These are never edited (audit-only even in apply mode) unless the user explicitly overrides for a
named span: code fences + inline code, explicit blockquotes, URLs / citations / link destinations,
generated data or command output, API identifiers / defined terms, legal clauses. Inline "quoted
text" is a `quote_candidate` — elevated to protected by context or the user, not auto-stripped.
Protected ≠ preservation-sensitive: a number in ordinary prose is not an immutable span, but it IS an
invariant (below).

<!-- anchor:preservation-invariants -->
## Preservation invariants (constrain meaning during any rewrite)
Before rewriting a passage, record what must survive byte-for-byte or meaning-for-meaning: every
number/quantity (value + unit + qualifier + subject), date, version, normative modal (MUST / MUST NOT
/ SHALL / SHOULD / MAY) and its polarity, negation near a predicate, condition/exception marker,
causal claim, attribution, defined term, cross-reference. A rewrite may never change, drop, or invent
one of these. Unresolved intent stays visibly unresolved — never rewritten into an asserted
requirement. The invariant ledger is append-only during a rewrite: add new invariants, never weaken
or remove one.

<!-- anchor:loop -->
## The loop
**protect → diagnose → establish invariants → rewrite (minimal, passage-local) → verify.**
1. **protect** — mark protected spans; they are off-limits.
2. **diagnose** — find demonstrated harm; emit one typed diagnosis record per harm (below).
3. **establish invariants** — record the preservation invariants for each passage you will touch.
4. **rewrite** — the smallest passage-local change that removes the diagnosed harm and nothing else.
   Never a whole-document pass; never a change that satisfies "style" by escalating an edit.
5. **verify** — a rewrite you do NOT verify is a rewrite you do not ship. Every invariant intact,
   every protected span byte-identical, no invented claim, edits only inside the harmed passage.

<!-- anchor:diagnosis-record -->
## Typed diagnosis record (one per harm — never a single "AI %" or an "AI-slop" bucket)
Emit each finding as a record, and classify ONLY after you have shown harm + impact:
- `category` — exactly one of the six below.
- `evidence_span` — the exact text that demonstrates the harm.
- `demonstrated_harm` — what the prose fails to do, plus the reader/requirement impact.
- `editorial_harm` — low / med / high.
- `diagnosis_confidence` — low / med / high.
- `permitted_response` — the category-specific remedy (below), never generic polish.
One span carrying two harms becomes two records. A category label is never a detection shortcut; no
harm shown ⇒ no record ⇒ no edit.

<!-- anchor:categories -->
### The six categories (keep emptiness / laundering / simulation SEPARATE — collapsing them is the top failure)
| category | what it is | <!-- anchor:remedies --> permitted response |
|---|---|---|
| `emptiness` | words add nothing / restate context | delete or compress — ONLY if no intent is lost |
| `laundering` | evaluative language posing as a requirement | convert to a question or label it non-testable — **never delete** (it is load-bearing intent) |
| `simulation` | implies absent evidence / examples / experience / completed work | **flag** the missing support — do NOT repair it substantively or invent the support |
| `lexical_structural` | lexical / structural / rhetorical / formatting tell | candidate only; act ONLY when redundant AND the genre permits |
| `voice_discontinuity` | a break in a doc expected to have ONE voice | evidence only when one voice is expected (not interviews / RFCs / quotes / changelogs / marketing) |
| `epistemic_distortion` | false confidence, hedge-piles hiding uncertainty, passive hiding the actor | repair WITHOUT inventing an actor or deleting necessary hedging |
The remedies are different on purpose. `emptiness` deletes; `laundering` questions (never deletes);
`simulation` only flags. Applying the wrong remedy is the top failure mode.

<!-- anchor:ratings -->
## Two ratings, never a single number
Report **editorial-harm** (low/med/high) and **diagnosis-confidence** (low/med/high) as two separate
axes. Never a single "AI %" or "sloppiness score" — those invite normalization and false precision.

<!-- anchor:modes -->
## Output modes
<!-- anchor:mode-audit -->
- **audit** — read-only diagnosis: passage, harm, confidence, category, why, permitted remedy kind,
  and any missing evidence. **No edits, no rewrites, no diffs.**
<!-- anchor:mode-suggest -->
- **suggest (default)** — diagnosis + a focused diff for each authorized repair + the invariant-check
  result. Ask a question ONLY for a fact that blocks a specific proposed repair. Placeholders like
  `[DEFINE X]` are proposed OUTSIDE the document unless the user approves inserting them (inserting one
  can make an invalid document look complete).
<!-- anchor:mode-apply -->
- **apply** — in-place mutation, on explicit request only, and **gated by a mandatory pre-mutation
  backup**. Until the backup gate ships (see the apply command), apply is UNAVAILABLE and must refuse
  with `status: mutation_unavailable` — it never silently falls back to editing or to an implicit audit.

<!-- anchor:cap -->
## Behavioral limits
- Present at most **3 high-value diagnoses per 500 words** unless an exhaustive audit is requested;
  this caps PRESENTATION only (prioritize the highest editorial-cost harms; summarize overflow, never
  expand it into extra edits). It never limits invariant extraction, verification, or hard-failure
  reporting.
- Once a passage passes its invariants and carries no high-harm diagnosis, **leave it alone on
  subsequent runs** (idempotence — repeated runs must not erode voice or amplify edits).

<!-- anchor:prohibitions -->
## Prohibitions (never, regardless of style pressure)
- Never homogenize or "smooth" a distinctive voice; never add/strip fragments, em-dashes,
  contractions, or profanity to make prose match a template or a profile.
- Never resolve an uncertainty the author left open, or delete necessary hedging.
- Never invent support, an actor, a number, a date, a citation, or a requirement.
- Never change, drop, or weaken a normative statement, condition, exception, or protected span.
- Never let the scanner, genre, ratings, or voiceprint authorize an edit (keystone rule).
- Never collapse emptiness / laundering / simulation into one bucket or one remedy.

## Genre awareness (constrains function, never decides prose is "bad")
Classify per region, not whole-document: general-prose · technical-doc · spec (repetition/parallelism
= correctness infrastructure, preserve it) · legal (flag, audit-only) · PRD (challenge
adjectives-as-requirements, but do not police every aspiration) · marketing (evocation allowed;
unsupported superiority is not) · personal (voice weighted high). On low genre confidence, use the
MOST preservation-heavy applicable profile. See `references/genre-profiles.md`.

## Reference map (read on demand — these ELABORATE the core, they never add a safety rule)
- `references/tell-taxonomy.md` — the six categories with indicators + before/after examples.
- `references/genre-profiles.md` — per-genre preservation priorities + the asymmetric-failure rule.
- `references/engine.md` — model/effort guidance (advisory: the session, not the plugin, owns the model).
- `references/scanner-metrics.md` + `references/invariant-ledger.md` — the measure-only scanner and the
  byte-exact verifier (arrive with the scanner / ledger increments); the scanner MEASURES, it never
  verdicts, and it never authorizes an edit.
