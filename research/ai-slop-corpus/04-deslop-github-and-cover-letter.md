# 04 — deslop (Stephen Turner) — MIT, scientific-writing focus + one gold long-form pair

- **Source URLs:**
  - Repo: https://github.com/stephenturner/skill-deslop
  - Before/after file: https://raw.githubusercontent.com/stephenturner/skill-deslop/main/references/examples.md
  - Blog write-up (long-form pair): https://blog.stephenturner.us/p/deslop
- **Date:** repo created 2026-03-18; blog post 2026-03-22
- **License:** MIT (repo). Blog post text: Substack, no explicit reuse license — quote for reference with attribution. The repo's examples.md is MIT and REUSABLE. Repo itself credits/synthesizes tropes.fyi + stop-slop.
- **Scoring rubric:** same 5 dims as stop-slop; "Authenticity" refined to "Sounds like a *specific* human wrote it?".

> Best-in-class for SCIENTIFIC / TECHNICAL register (methods passive-voice conventions respected). 15 sentence/paragraph pairs + 1 full long-form pair.

## Long-form pair (GOLD — real published paper, PLANES / Nagraj et al. 2025 PLOS ONE)

A cover letter written "with every AI trope cranked up" (scored 8/50) vs. the deslopped rewrite (scored 43/50). Excellent long-form eval fixture; scientific register; preserves the same factual claims while replacing vague claims with specific numbers.

**BEFORE (8/50):**
> "It's worth noting that methods for reviewing epidemiological signals serve as a critical component of the ever-evolving landscape of public health surveillance. Here's the thing: implausible forecasts and faulty surveillance data don't just bias ensemble models — they erode trust in the very systems designed to protect public health. We are pleased to submit our manuscript, "PLANES: Plausibility Analysis of Epidemiological Signals," for consideration in PLOS ONE. In this paper, we delve into a novel, robust approach for assessing forecast plausibility and surveillance data integrity — one that is multi-dimensional, flexible, and open-source. The result? A scoring system that fundamentally reshapes how modelers and public health stakeholders navigate the challenges of data quality review. Our analysis of 2022-23 FluSight forecasts highlights that forecasts flagged by multiple PLANES components were remarkably less accurate on average, underscoring the approach's practical utility... Despite these challenges in the current state of plausibility assessment, we believe PLANES fills an important gap. Not a replacement for human judgment. Not a fully automated system. A decision-support tool that quietly reduces the burden of manual review while leveraging historical data to codify nuanced expectations about signal behavior. ... In summary, we believe this work represents a meaningful contribution to the growing body of literature on epidemiological data integrity... Let's dive in."

Tells packed in: "it's worth noting," "serve as," "ever-evolving landscape," "Here's the thing," "don't just X — they Y" (negative parallelism + em dash), "delve into," rule-of-three ("multi-dimensional, flexible, open-source"), "The result?" (rhetorical), "fundamentally reshapes," "navigate the challenges," "Despite these challenges," "Not a X. Not a Y. A Z." (negative listing), "leveraging," "nuanced," "In summary," "growing body of literature," "Let's dive in."

**AFTER (43/50):**
> "We submit "PLANES: Plausibility Analysis of Epidemiological Signals" for consideration in PLOS ONE. The manuscript describes a multi-dimensional scoring method for assessing the plausibility of infectious disease forecasts and surveillance data, delivered through an open-source R package (rplanes, available on CRAN). PLANES uses historical observed data to seed location-specific baseline characteristics, then evaluates signals across seven components, each producing a binary flag that rolls up into an ordinal score. In a retrospective analysis of over 29,000 FluSight forecasts from the 2022-23 season, we found that forecasts with two or more components flagged had significantly higher weighted interval scores (r = 0.267, p < 0.0001), indicating worse predictive accuracy. No codified plausibility heuristics currently exist for epidemiological signals; review, where it happens at all, is ad hoc and undocumented. PLANES addresses this gap with a method that works for both forecasted and observed signals at daily, weekly, or monthly resolution. We piloted rplanes operationally during the 2023-24 FluSight season... The package is designed for human-in-the-loop use: it flags signals for review rather than censoring them automatically..."

Direction: vague inflation → concrete numbers (29,000 forecasts; r = 0.267, p < 0.0001; seven components), meaning preserved.

## Sentence/paragraph pairs (verbatim, scientific/blog/grant register)

**1. Throat-clearing + binary contrast → emptiness + synthetic cadence**
- Before: "Here's the thing: forecasting infectious disease is hard. Not because the models are complex. Because the data is complex. Let that sink in."
- After: "Forecasting infectious disease is hard. The models are tractable. The data, collected under shifting surveillance definitions and reporting lags, is not."

**2. Filler + "Despite these challenges" → emptiness**
- Before: "It's worth noting that these findings have important implications for how we navigate the challenges of forecast ensembling moving forward. Despite these challenges, this work contributes meaningfully to the growing body of literature, highlighting the need for continued evaluation and underscoring the importance of robust benchmarking."
- After: "If individual model rankings are unstable across geography and time, ensemble methods that weight models by past performance may not improve on equal-weight approaches."

**3. Grandiose stakes + "landscape" → emptiness/inflated symbolism**
- Before: "In today's rapidly evolving genomic landscape, single-cell RNA sequencing has fundamentally reshaped how we think about cellular heterogeneity. This paradigm shift has far-reaching implications for our understanding of disease."
- After: "Single-cell RNA sequencing reveals cell-type-specific expression patterns that bulk methods average out. In tumor samples, this distinction matters: rare resistant subpopulations visible in single-cell data disappear in bulk profiles."

**4. Passive voice + false agency → obscured responsibility / anthropomorphic**
- Before: "It was observed that model performance degraded at longer forecast horizons. The uncertainty naturally increased as the prediction window expanded. These results emerged from our analysis of 54 state-level forecasts."
- After: "We observed that model performance degraded at longer forecast horizons. Each additional week of lead time added roughly 15% to the mean WIS. We saw this pattern across all 54 state-level forecasts."

**5. Self-posed rhetorical questions → emptiness (signposting)**
- Before: "What if I told you that most bioinformatics pipelines break in production? The result? Wasted compute and silent errors. The worst part? Nobody checks the intermediate outputs. Here's why that matters:"
- After: "Most bioinformatics pipelines break in production, and the failures are quiet. The FASTQ passes QC. The alignment runs. But the reference genome version changed between runs, and the variant calls shift without warning."

**6. "Serves as" + superficial participles → copula avoidance / emptiness**
- Before: "The FluSight initiative serves as a foundational framework for influenza forecasting in the United States, contributing to public health preparedness and underscoring the importance of collaborative forecasting efforts."
- After: "The FluSight initiative coordinates influenza forecasting across dozens of modeling groups in the United States. Since 2013, it has standardized targets, submission formats, and evaluation metrics."

**7. Narrator distance + vague declarative → emptiness**
- Before: "Nobody designed the current state of genomic data sharing. The reasons are structural. This is genuinely hard, and the implications are significant."
- After: "You inherit a genomic data sharing system that grew by accretion: dbGaP for controlled access, GEO for expression, SRA for raw reads, ClinVar for variants. Each solves one problem. None talks to the others without custom glue code."

**8. Listicle in a trench coat → lexical_structural**
- Before: "The first limitation of our study is the relatively short evaluation window. The second limitation is the lack of a standardized baseline across all forecasters. The third limitation is the potential for overfitting..."
- After: "Our evaluation covers only two seasons, and both followed the unusual post-COVID influenza dynamics that may not generalize. We also lacked a standardized baseline: each forecaster chose their own training data and feature set..."

**9. One-point dilution → emptiness (density)**
- Before: "Reproducibility matters. In fact, reproducibility is the most underrated quality in computational biology. When you make your analysis reproducible, you reduce errors. Fewer errors mean more trust. More trust means faster adoption. The lesson? Make it reproducible. Irreproducible analyses are the enemy of science. The best papers are the reproducible ones."
- After: "Reproducible analyses catch errors earlier. When Beaulieu-Jones and Greene re-ran 68 papers from the PharmacoGenomics Knowledge Base, only 40% reproduced. The ones that failed had no shared code or pinned dependency versions."

**10. Historical-analogy stacking → simulation/emptiness**
- Before: "Apple didn't build Uber. Facebook didn't build Spotify. Stripe didn't build Shopify. AWS didn't build Airbnb. Every major technological shift follows the same pattern."
- After: "AWS sold infrastructure. Airbnb built a business on top of it. That split between platform and product repeats across the industry."

**11. Anaphora abuse → synthetic cadence (grant register)**
- Before: "We will develop novel computational methods. We will apply these methods to large-scale genomic datasets. We will validate our findings using independent cohorts. We will disseminate our tools through open-source repositories. We will train the next generation of computational biologists."
- After: "We will develop and validate statistical methods for multi-ancestry fine-mapping using UK Biobank and TOPMed cohorts, then release them as an R package with documentation and tutorials suitable for graduate training."

**12. Dramatic fragmentation → synthetic cadence**
- Before: "Speed. Quality. Cost. You can only pick two. That's it. That's the tradeoff."
- After: "Speed, quality, cost: pick two."

**13. False vulnerability + meta-commentary → emptiness/epistemic**
- Before: "And yes, since we're being honest: I've run plenty of analyses where the p-value was borderline and I squinted at it until it cooperated. I want to explore why that impulse is so common. In this post, I'll walk you through what I've learned."
- After: "I've nudged a borderline p-value along by trying one more covariate. You probably have too. The question is what makes that feel acceptable in the moment, and the answer is usually that the rest of the analysis already 'looks right.'"

**14. "It's worth noting" + invented concept label → epistemic_distortion**
- Before: "It's worth noting that this creates what might be called the 'calibration paradox': models that are well-calibrated at the national level may be poorly calibrated at the state level, reflecting broader trends in the tension between aggregation and granularity."
- After: "National-level calibration does not guarantee state-level calibration. A model can produce well-calibrated 90% intervals for the US overall while consistently undercovering in states with smaller populations and noisier surveillance data."

**15. "Imagine a world" + patronizing analogy → emptiness/inflated metaphor**
- Before: "Imagine a world where every meeting had a clear agenda. Think of it like a recipe: you wouldn't start cooking without knowing the ingredients. That's the promise of async-first communication. Let's unpack why this matters."
- After: "Meetings without agendas waste time. A 15-person sync with no written agenda averages 47 minutes and produces no decisions (Atlassian, 2019). Writing the agenda forces the organizer to decide whether the meeting is necessary at all."
