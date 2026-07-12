# Increment 3 design brief — #scanner (scan_prose.py + vendored CommonMark)

Context: slopslap's scanner **measures, never verdicts** (spec §Scanner, §Scanner dependency). It emits
metrics that are triage aids only; it NEVER authorizes an edit (keystone rule). Increments 1–2 shipped
the acceptance contract + the plugin scaffold. Full spec:
`docs/planning/2026-07-12-slopslap-reconciled-spec.md`.

## Deliverables
- `scripts/scan_prose.py` — CLI. Plain-text path (stdlib) first; Markdown via a **vendored** CommonMark
  parser. **Mandatory `--format text|markdown`.** Reads a file arg or stdin. Emits valid JSON always.
- `scripts/slopslap_scan/` — the adapter over the vendored parser (capability gate, extraction, metrics).
- `vendor/python/markdown_it/` + `vendor/python/mdurl/` — pinned `markdown-it-py==3.0.0` + `mdurl==0.1.2`,
  plugin-private, version-gated import.
- `THIRD_PARTY_LICENSES/` — the vendored deps' licenses + provenance (upstream version / source / update
  procedure).
- `references/scanner-metrics.md` — exact parameters for every metric + CommonMark exclusion fixtures.

## Capability contract (spec §Scanner dependency; WF5 #2/#5)
- **Format explicit, never guessed:** `--format text|markdown` required. Absent/ambiguous ⇒ status
  `format_required` + a distinct exit code; never silent fallback to the plain-text path.
- **Plain-text path is stdlib-only, always available.** Markdown is EITHER parsed by the vendored
  CommonMark parser OR reported unavailable — Markdown input is NEVER routed through the plain-text path.
- **capability_unavailable:** an absent/incompatible parser ⇒ valid JSON
  `{"status":"capability_unavailable","format":"markdown","capability":"markdown_commonmark","metrics":null}`
  + stderr notice + **exit code 10** (advisory-skip). Never zero-valued/partial metrics.
- **Exit codes:** `0` ok · `1` malformed input / scanner defect · `2` format_required · `10`
  capability_unavailable. (Proposed — peer sanity-check requested.)
- **Version-gate the import** so an environment copy can't silently change tokenization.

## Markdown extraction (spec §Scanner)
Exclude fenced + indented code, HTML blocks, blockquotes (default), link destinations (keep visible
text), autolinks/**bare URLs** (post-tokenization deterministic rule — NOT a linkify extension
dependency; WF5 #8), inline code. Retain headings + list text with a structural type. Bound to explicit
extraction fixtures so counts/locations stay reproducible across parser versions.

## MVP metrics (~8, spec §MVP cut) — each emits `{eligible_units, count, rate, locations, soft_flag, threshold_profile}`
sentence-length distribution (min/p10/p25/median/p75/p90/max/mean/sd) + sentence_length_dispersion
(IQR/median, CoV, median adjacent-diff — NOT "burstiness"); repeated openers (normalize first 1/2/3
lexical tokens, lowercase, strip list punctuation, keep negation, rolling 8-sentence window, ignore
<2-token openers); transition clusters (rate per 1k eligible words); punctuation rates (em-dash /
semicolon per 1k); paragraph sentence-count runs (≥3 adjacent equal); vague-attribution clusters;
bold-label density; stock lexical clusters (named cluster + phrase, not isolated common words).
Thresholds are versioned triage aids (`purpose: candidate_selection_only`); no cross-doc percentiles in
MVP. Exact params pinned in `references/scanner-metrics.md` with fixtures BEFORE each metric ships.

## Vendoring plan
Copy `markdown-it-py 3.0.0` + `mdurl 0.1.2` (pure-Python) into `vendor/python/`; `scan_prose.py` inserts
`vendor/python` at the FRONT of `sys.path` before importing `markdown_it`, then asserts
`markdown_it.__version__ == "3.0.0"` (else capability `version_mismatch`). Licenses + a `PROVENANCE.md`
under `THIRD_PARTY_LICENSES/`.

## Questions for the peer
1. **Import isolation + how to TEST it from the packaged layout.** How do I guarantee the scanner uses
   the VENDORED `markdown_it` (not an env copy that may already be import-cached in the same process),
   and how do I prove it in a test — a subprocess with a restricted env / `PYTHONPATH` pointed only at
   `vendor/python`, `-S` to skip site-packages? What's the most robust "runs from the actual installed
   plugin layout on a machine WITHOUT markdown-it-py installed" test?
2. **Exit-code scheme** (0/1/2/10) — is `format_required=2` distinct-enough from `1` malformed; any
   collision risk with shell conventions?
3. **Metric MVP cut** — which of the ~8 are reliable enough to ship, and which should be flagged
   low-confidence? Exact params for the two trickiest: repeated-opener normalization and the stock
   lexical cluster list (named cluster + phrase, avoiding isolated common words). Keep or defer the
   cadence-similarity metric (spec routes it to scanner-metrics.md but calls it structure, not full
   parameterization)?
4. **Bare-URL exclusion** — the exact deterministic post-tokenization matcher, bound to fixtures.
5. **Vendoring source** — copy the host's installed 3.0.0 vs `pip download` the sdist at build time;
   what provenance makes this auditable and updatable?

## Folded decisions — post peer-consult (gpt-5.6-sol, `docs/reviews/peer-increment-3-scanner-design-2026-07-12.md`)

1. **Exit codes 0/1/2/10 confirmed.** Same stable JSON envelope on EVERY path (`{status, format, ...}`),
   diagnostics on stderr. `0`=ok · `1`=error (decode failure / internal defect; carry `error_kind`) ·
   `2`=format_required · `10`=capability_unavailable (carry `reason` = `not_importable|version_mismatch|origin_mismatch`).
2. **`--format` required** via explicit validation; omission / unknown / conflicting ⇒ `format_required`, exit 2.
   Markdown input is NEVER routed to the text path.
3. **Import isolation = the CLI subprocess.** `scan_prose.py` derives `vendor/python` from its own real
   `__file__`, inserts it at `sys.path[0]`, `importlib.invalidate_caches()`, imports `markdown_it` +
   `mdurl`, and verifies **each loaded module's resolved `__file__` is beneath the vendor root** AND
   `markdown_it.__version__ == 3.0.0` (+ mdurl version). Any origin/version mismatch ⇒
   `capability_unavailable` with the reason — it NEVER mutates `sys.modules`. Re-check origins again after
   parsing a fixture (lazy imports). No embeddable in-process adapter that could bind an env copy.
4. **Packaged-layout test = `python -I -S`.** Copy the plugin to a temp layout, run
   `scripts/scan_prose.py` under `python -I -S` (ignores `PYTHONPATH` + site-packages, so the env
   markdown-it-py is invisible and only the vendored copy is reachable), cwd outside the plugin, cleared
   env, scan a markdown fixture ⇒ assert `status=ok` + vendored origins. **Negative tests:** vendor tree
   renamed ⇒ exit 10; incompatible vendored version ⇒ exit 10 `reason=version_mismatch`.
5. **Extraction:** CommonMark preset, NO linkify. Walk block+inline tokens with source-LINE maps (promise
   line ranges; columns only where deterministic). Drop fenced/indented code, HTML blocks, blockquotes,
   inline code, link destinations; retain visible link labels, headings, list text, emphasis metadata,
   paragraph boundaries.
6. **Bare-URL removal within eligible text spans only** (never across token boundaries), case-insensitive:
   `https?://` + non-space run · `www.` + DNS host · or DNS host + ≥1 dot + a **pinned ASCII TLD
   allowlist** + optional port/path/query/fragment. Left boundary ∉ {letter,digit,_,@}; exclude emails;
   strip trailing `.,:;!?` and unmatched closing `)]}`; keep balanced delimiters. Frozen TLD list + regex +
   fixtures in the extraction profile.
7. **Metric confidence tiers** (recorded in each result's `threshold_profile.confidence`):
   - normal: sentence-length distribution + dispersion, punctuation rates, paragraph sentence-count runs,
     bold-label density.
   - medium: repeated openers, transition clusters.
   - low: vague-attribution, stock-lexical clusters (`soft_flag` may be `null` until corpus evidence).
   Every result names `metric_version, extraction_profile, threshold_profile, confidence,
   purpose=candidate_selection_only`. **cadence-similarity is DEFERRED** (no stable parameterization; no
   placeholder metric).
8. **repeated openers:** eligible sentences in doc order; Unicode-aware lexical tokens preserving internal
   apostrophes; leading negator (no/not/never/neither/nor) is lexical; strip list markers; casefold;
   normalize apostrophes; 1/2/3-token prefixes only when ≥2 lexical tokens; rolling 8-sentence window;
   count a prefix once when it occurs in ≥3 distinct sentences in the window; canonicalize by
   prefix+maximal contiguous range (no overlap double-count).
9. **stock lexical clusters:** phrase-only, table-driven, named clusters (conclusion / significance /
   broad-change / essence / duality / generic-navigation) with exact normalized phrase sequences (except
   the two bounded duality templates); never match isolated words (important/landscape/crucial/delve);
   report cluster + matched phrase; table versioned separately.
10. **transition clusters:** explicit multi-token phrase table, occurrences per 1k eligible prose words;
    isolated however/moreover/therefore only via a narrow sentence-initial fixture-established pattern.
11. **bold-label density:** a "label" = strong text at the START of a paragraph/list item followed by
    punctuation (e.g. a colon) — NOT every bold span.
12. **sentence segmentation:** stdlib heuristic with a fixture-pinned abbreviation table + Unicode rules,
    exposed as part of the metric version.
13. **Vendoring source = immutable PyPI sdist**, downloaded in a controlled BUILD-TIME update step (not
    copied from a dev env, not fetched during the product build). `THIRD_PARTY_LICENSES/PROVENANCE.md`
    records package/version/canonical artifact URL/artifact SHA-256/upstream URL/license id/license
    hash/included+excluded paths/patch status/exact repeatable update+verify commands. **If PyPI is
    unreachable in this run, fall back to vendoring the host's installed 3.0.0/0.1.2, record that source
    honestly in PROVENANCE, and flag a follow-up to re-vendor from the sdist (does not block — the
    version-gate + origin check still hold).**

## Post-review resolutions — WF5 on the scanner design (`docs/reviews/increment-3-scanner-design-md-2026-07-12.md`, 0 Crit / 1 High / 7 Med, all confirmed)

- **R1 (H1) — no separate installer.** A Claude Code plugin has no wheel/build step: the git tree IS the
  artifact, copied wholesale into the plugin cache. The `python -I -S` copied-layout test faithfully
  models that cache copy (whole plugin dir → temp → run with site-packages invisible). Add a test that
  `vendor/python/markdown_it/__init__.py` + `vendor/python/mdurl/__init__.py` are git-tracked, so
  "packaging excludes vendor/" can't happen. Runtime subprocess/sandbox permission is the host's and is
  flagged separately, not defeated by this test.
- **R2 (M2) — deterministic repeated-opener events.** For each prefix length L∈{1,2,3} and normalized
  prefix p, take the eligible-sentence indices containing p; group them into maximal **clusters** where
  successive members differ by ≤7 (the 8-sentence reach); a cluster with ≥3 sentences is ONE event.
  count = number of events; locations = the cluster's sentence line ranges; eligible_units = eligible
  sentences. No rolling-window overlap double-count. Overlapping + separated fixtures pinned.
- **R3 (M3) — error-envelope table.** Every CLI/IO failure maps to the stable JSON envelope on stdout +
  a stderr message: `format_required` (exit 2); else `error` (exit 1) with `error_kind ∈
  {bad_arguments, file_not_found, file_unreadable, stdin_error, decode_error, serialize_error,
  internal}`. argparse errors are caught and translated (never a raw non-JSON exit 2). One fixture per path.
- **R4 (M4) — origin diagnostic in the ok envelope.** The markdown ok JSON carries
  `capabilities.markdown_commonmark = {available:true, modules:{markdown_it:{version,origin}, mdurl:{version,origin}}}`
  with resolved origins; the packaged-layout test asserts every origin is under the vendor root.
- **R5 (M5) — one flat metric schema.** Each metric result =
  `{eligible_units, count, rate, locations, soft_flag, metric_version, extraction_profile, confidence, purpose}`;
  `confidence`/`purpose` are TOP-LEVEL (no nested threshold_profile); optional `thresholds` holds the
  actual values. Pinned as the normative schema in `references/scanner-metrics.md`.
- **R6 (M6) — content-pinned vendoring.** Prefer the immutable PyPI **sdist** (record artifact SHA-256).
  A host-copy fallback is allowed ONLY if every copied file's SHA-256 is recorded in PROVENANCE (the
  runtime version/origin checks prove name+location+version, NOT content equivalence). PROVENANCE carries
  per-file hashes either way; a host-sourced copy is flagged for sdist re-vendor.
- **R7 (M7) — extraction spike first.** Before implementing extraction, run a spike against the vendored
  `markdown-it-py==3.0.0` capturing, per construct, the exact token `type/tag/nesting/map/children/content`;
  pin the observed token contract + fixtures in `references/scanner-metrics.md`. Extraction promises LINE
  ranges (token `map` is line-oriented); columns only where deterministic.
- **R8 (M8) — sys.modules wording.** The scanner never **manually deletes, replaces, or aliases** an
  existing `sys.modules` entry; normal imports populate the fresh CLI process's cache, and a failed
  capability check leaves those entries untouched until process exit.

## Out of scope
The ledger/verify (#ledger-verify), apply/backup (#apply-backup), wiring the scanner INTO the suggest
command flow (later), cross-doc percentile baselines (post-MVP). The scanner measures; it never verdicts
and never authorizes an edit.
