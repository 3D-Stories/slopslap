# 05 — llmbestpractices.com — "Anti-Slop Writing Rules"

- **Source URL:** https://llmbestpractices.com/writing/anti-slop
- **Date:** 2026-07-06
- **License:** none stated (community/reference site). Treat as fair-use quotation with attribution; NOT clearly reusable/relicensable. Flagged in SOURCES.md.
- **Notable:** explicitly says apply "whether the draft was written by a person, a model, or a person editing a model" — aligns with slopslap's stance that the tell, not authorship, is what's addressed. 5 clean before→after pairs (dev/technical register).

## Before → After (verbatim, technical-blog register)

**1. Em-dash parenthetical → lexical_structural (em-dash overuse)**
- Before: "The migration — which had to land before the freeze — touched every service."
- After: "The migration had to land before the freeze. It touched every service."

**2. "It's not X, it's Y" → synthetic cadence (negative parallelism) — HIGH PRIORITY**
- Before: "It's not a framework, it's a runtime."
- After: "Bun is a runtime, not a framework."
- Rule (verbatim): "Always reach for the affirmative form. 'Y' alone, or 'Y, more than X.' The contrastive frame is a rhythm crutch."

**3. Slop preamble → emptiness (signposting)**
- Before: "In today's fast-paced world of frontend development, let's dive into the basics of Astro."
- After: "Astro is a static site framework. Start here."

**4. Hollow transition + summary closer → emptiness**
- Before: "Postgres is a powerful database. Moreover, it scales well. Furthermore, it has a rich ecosystem. In conclusion, Postgres is a great choice for your next project."
- After: "Use Postgres for app data. It scales, the ecosystem is deep, and the operational story is well-understood."

**5. Three-item filler → synthetic cadence (rule-of-three)**
- Before: "Tailwind is fast, flexible, and developer-friendly."
- After: "Tailwind ships small CSS, because it generates only the utilities you use."

## Supporting rule catalog (patterns → fix; useful tell taxonomy)

- "Delve / delve into / dive in / let's dive in" → "read/look at/open/study, or just start."
- "Navigate the landscape of" → "work with / use / ship."
- "Unlock the power of" → delete; state what the tool does.
- "In today's fast-paced world / in an era where" → delete.
- "Boasts" → "has." "Leverage" (verb) → "use."
- "Robust solutions / comprehensive guide / seamless experience" → specific nouns; "If you cannot answer [what is robust], the word is filler."
- Every paragraph ending in a takeaway ("And so, X matters." / "This is why Y is essential.") → end on the last fact.
- False balance ("While X has its merits, Y is the better choice.") → if Y is better, say so; the hedge is a tell.
- Hedge stacking ("It may be possible that, in some cases, you might want to consider.") → pick one hedge or none.
- Adjective pairs glued together ("fast and reliable," "robust and scalable") → pick one.
- Voice positives: lead with the verb; use specific nouns ("Cloudflare Workers," not "edge functions"; "Postgres 17," not "modern relational databases"); name the thing (`pg_dump`); rule first, reason after.
