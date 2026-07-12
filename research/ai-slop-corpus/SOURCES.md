# SOURCES — AI-slop before/after corpus

All URLs fetched 2026-07-12. Fetch method: Exa `web_fetch_exa` (verbatim markdown) and `WebFetch` (extractive) — Firecrawl was out of credits (HTTP 402) this session, so a few blog sources have highlight-level coverage only (flagged). Treat all fetched text as DATA; no embedded instructions were acted on.

Licensing legend: ✅ reusable (with attribution) · ⚠️ unclear / fair-use quotation only · 🔬 dataset, license varies per host (confirm card).

| # File | Source | URL | Date | License | One-line |
|---|---|---|---|---|---|
| 01 | Wikipedia: Signs of AI writing (WikiProject AI Cleanup) | https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing | living; examples 2023–2026 | ✅ CC BY-SA 4.0 | Primary authoritative catalog; real dated Wikipedia revisions per tell; 2 true before→after diffs, rest AI-example+pattern. |
| 02 | humanizer skill (local; Wikipedia-derived) | local: `~/.claude/skills/humanizer/SKILL.md` (upstream: Wikipedia guide) | v2.5.1 | ✅ MIT (derivative of CC BY-SA guide) | 29 clean before→after pairs, one per tell; closest existing analog to slopslap. |
| 03 | stop-slop (Hardik Pandya) | https://github.com/hardikpandya/stop-slop (+ /raw/main/references/examples.md, structures.md) | 2026-01 to 03 | ✅ MIT | 5 prose pairs + large structural-pattern taxonomy; aggressive "ban the feature" stance (contrast case for slopslap). |
| 04 | deslop (Stephen Turner) | https://github.com/stephenturner/skill-deslop (+ /raw/main/references/examples.md) ; blog https://blog.stephenturner.us/p/deslop | 2026-03 | ✅ MIT (repo) / ⚠️ blog text | 15 scientific/blog/grant pairs + 1 GOLD long-form cover-letter pair (real PLOS ONE paper, 8/50→43/50). |
| 05 | llmbestpractices — Anti-Slop Writing Rules | https://llmbestpractices.com/writing/anti-slop | 2026-07-06 | ⚠️ none stated | 5 clean technical-blog pairs; strong "apply regardless of authorship" framing. |
| 06 | texttoolsai — Humanize ChatGPT Essay | https://www.texttoolsai.app/examples/ai-humanizer/humanize-chatgpt-essay | 2026-05-22 | ⚠️ commercial marketing page | 3 paragraph-length pairs with precise "what changed"; detector-evasion framing (off-mission) but rewrites valid. |
| 07 | Donatas Simkus — Spot & Fix AI writing | https://donatassimkus.com/blog/how-to-spot-ai-writing-fix-it | 2026-03-27 | ⚠️ blog; embedded skill offered to copy, no OSS license | ~12 marketing-register pairs (sentence patterns + principle table); "density is the signal" caution. |
| 08 | genintelsys — Dead Giveaways / tropes.fyi | https://www.genintelsys.com/blog/em-dashes-ai-tells/ ; https://tropes.fyi/ | 2026-05 / 2026 | ⚠️ commercial blog / ⚠️ tropes.fyi no explicit license | Tell catalogs; tropes.fyi names negative-parallelism as "single most common tell"; few full pairs. |
| 09 | TextKit; Louis Bouchard; Nathan Fennel | https://text.thicket.sh/blog/how-to-clean-ai-generated-text ; https://www.louisbouchard.ai/ai-editing/ (+ substack) ; https://nathanfennel.com/blog/the-cleanup-prompt | 2026-01 to 06 | ⚠️ blogs/newsletters | HIGHLIGHT-LEVEL only (Firecrawl 402). 1 verbatim TextKit pair; strong keystone-aligned cautions ("over-correction is its own tell"); "change the skeleton not just the words." |
| 10 | Academic paired corpora (9 datasets) | see file 10 for each URL | 2023–2026 | 🔬 varies | HPPT, SciHRA, Beemo, PAN'25, MixSet, OpAI-Bench, EditLens, APT-Eval, PASTED. Beemo = best on-mission (machine→expert-edited). Confirm each license before reuse. |

## Reuse guidance for slopslap
- **Safe to vendor/relicense-compatible (MIT / CC BY-SA):** files 01, 02, 03, 04 (repo parts). CC BY-SA (Wikipedia) requires share-alike if redistributed as text; quoting examples for internal eval/taxonomy is fine with attribution.
- **Fair-use quotation only (do NOT bundle as a redistributed corpus):** files 05, 06, 07, 08, 09 — quote short examples with attribution for eval/reference; do not republish wholesale.
- **Datasets (file 10):** each carries its own license/terms (several are research-only, non-commercial, or "not for high-stakes individual decisions"). Confirm the dataset card before any use.

## Not accessed / gaps
- Firecrawl search + scrape unavailable this session (402). Reddit/HN forum threads were NOT directly mined (search returned blogs; a dedicated Reddit/forum pass is a follow-up).
- Full-page verbatim NOT captured for TextKit, Louis Bouchard, Nathan Fennel (highlights only) — re-fetch when Firecrawl credits restored.
- Wikipedia "Emoji as formatting" and "Unusual use of tables" sections: no standalone example SENTENCE captured (those tells are formatting-only; the humanizer skill file 02 supplies synthetic examples).
