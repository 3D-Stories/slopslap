# Scanner metrics — pinned parameters + extraction contract

The scanner **measures, never verdicts** (spec §Scanner). Every metric is a
candidate-selection aid (`purpose: candidate_selection_only`); a soft flag is a triage
signal, never proof, and NEVER authorizes an edit (keystone rule). Changing any table or
parameter here is a `metric_version` bump. Design + review trail:
`docs/planning/increment-3-scanner-design.md`.

## CLI + envelope (`scripts/scan_prose.py`)
- **`--format text|markdown` is mandatory** (no content sniffing). A stable JSON envelope is
  emitted on stdout for EVERY path; diagnostics go to stderr.
- **Exit codes:** `0` ok · `1` error · `2` format_required · `10` capability_unavailable.
- **Error envelope table** (`status:"error"`, `metrics:null`, exit 1 unless noted):

  | error_kind | trigger |
  |---|---|
  | bad_arguments | unknown option, missing `--format` value, >1 FILE |
  | file_not_found | FILE path does not exist |
  | file_unreadable | OS error opening FILE |
  | stdin_error | stdin read failure |
  | decode_error | input is not valid UTF-8 |
  | internal | any uncaught defect (still emits JSON) |
  | *(format_required)* | `--format` absent / unknown / given twice → exit **2** |

## Capability contract (Markdown only)
The Markdown path uses the plugin-private VENDORED `markdown-it-py==3.0.0` + `mdurl==0.1.2`
under `vendor/python/`. `scan_prose.py` prepends the vendor root (derived from its own real
path), imports the parser, and verifies **each module's resolved `__file__` is beneath the
vendor root AND the version is pinned**. On any mismatch it emits
`{"status":"capability_unavailable","format":"markdown","capability":"markdown_commonmark","metrics":null,"reason":<not_importable|version_mismatch|origin_mismatch>}`
+ a stderr notice + exit 10 — never zero/partial metrics, never a plain-text fallback for
Markdown input. The scanner never manually deletes/replaces/aliases a `sys.modules` entry.
On success the ok envelope carries `capabilities.markdown_commonmark.modules` with resolved
origins + versions.

## Extraction (verified against markdown-it-py 3.0.0 tokens — `extraction_profile: commonmark-3.0.0-v1`)
Parse with the `commonmark` preset (NO linkify). Observed token contract used:
- Block tokens carry `.map = [start_line, end_line)` (0-indexed, half-open); `inline` tokens
  carry `.map` and `.children`. Locations are reported as **1-indexed inclusive line ranges**
  (`line_start`, `line_end`); columns are not promised (token maps are line-oriented).
- **Excluded** (not eligible prose): `fence`, `code_block` (indented), `html_block`,
  `code_inline`, link destinations, and everything inside `blockquote_open`/`blockquote_close`.
- **Retained**: visible link labels (sibling `text` children between `link_open`/`link_close`),
  heading text (`structural_type: heading`), list text (`list_item`), paragraph text.
- **Bare-URL removal** is a deterministic post-tokenization rule (NOT a linkify extension),
  applied within eligible text only: `https?://…`, `www.…`, or a DNS host + `.` + a pinned
  ASCII TLD (`tables.TLD_ALLOWLIST`) + optional `:port`/path/query/fragment. Left boundary
  ∉ {word char, `@`, `.`} so emails and sub-parts don't match; trailing `.,:;!?` is pushed
  back into the prose. Bound to extraction fixtures in `tests/test_scanner_extract.py`.

## Metrics (flat schema, design R5)
Each result: `{eligible_units, count, rate, locations, soft_flag, metric_version,
extraction_profile, confidence, purpose}` (distribution/dispersion metrics add a
`distribution`/`dispersion` object; punctuation adds `rates`). `confidence ∈
{normal, medium, low}`; a `low` metric may keep `soft_flag: null` until corpus evidence.

| metric | confidence | parameterization |
|---|---|---|
| sentence_length_distribution | normal | word-count per sentence; min/p10/p25/median/p75/p90/max/mean/sd (population sd) |
| sentence_length_dispersion | normal | IQR/median, CoV = sd/mean, median adjacent-diff (NOT "burstiness") |
| punctuation_rates | normal | em-dash (`—` and standalone `--`) + `;` per 1k eligible words |
| paragraph_sentence_count_runs | normal | ≥3 adjacent paragraphs with equal sentence count → one run |
| bold_label_density | normal | `**label**:` at the start of a paragraph/list item ÷ eligible blocks (not every bold span) |
| repeated_openers | medium | normalized 1/2/3-token openers; **gap≤7 cluster events** (see below) |
| transition_clusters | medium | SENTENCE-INITIAL transition openers (`tables.TRANSITION_OPENERS`) per 1k words |
| vague_attribution | low | phrase table `tables.VAGUE_ATTRIBUTION`; `soft_flag:null` |
| stock_lexical_clusters | low | named phrase table `tables.STOCK_CLUSTERS` + 2 bounded duality templates; `soft_flag:null` |

**cadence-similarity is DEFERRED** (no stable parameterization; overlaps dispersion +
paragraph-runs) — not shipped as a placeholder.

### repeated_openers event algorithm (deterministic; design R2)
For each opener length L∈{1,2,3} and normalized prefix p (lowercase lexical tokens, internal
apostrophes kept, leading negators lexical, only when the sentence has ≥2 lexical tokens):
collect the eligible-sentence indices containing p; sort; split into maximal **clusters**
where each successive index is within 7 of the previous (the 8-sentence reach). A cluster of
≥3 sentences is ONE event. `count` = number of events; each location gives the prefix,
prefix length, sentence count, and the cluster's line range. Overlapping windows cannot
double-count because clustering is a single left-to-right pass over sorted indices.
