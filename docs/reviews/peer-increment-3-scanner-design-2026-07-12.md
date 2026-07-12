# Peer Consult — increment-3-scanner-design.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Build the scanner as two strictly separated pipelines behind one JSON-emitting CLI: a stdlib-only text pipeline and a capability-gated Markdown pipeline. Resolve all paths relative to the installed script, start Markdown scans in a fresh process, prepend the plugin-private vendor directory, and accept the parser only when both its version and resolved module origins match the vendored tree. Convert either input into a common sequence of source-mapped structural units, then compute deterministic metrics without producing edit recommendations or verdicts. Freeze extraction behavior, sentence segmentation, lexical tables, thresholds, and schemas as independently versioned profiles backed by fixtures.

## Key decisions

- Keep exit codes 0/1/2/10. Code 2 is conventionally associated with command-line usage errors and cleanly represents a missing or invalid --format; code 10 is sufficiently distinct for an advisory capability skip. Emit the same stable JSON envelope on every path, including unexpected scanner failures, while putting diagnostics on stderr.
- Make --format required through explicit argument validation. Unknown values, omission, or conflicting occurrences return status=format_required and exit 2. File decoding failures, invalid invocation details other than format, broken input streams, and internal defects return status=error and exit 1.
- Treat the CLI subprocess as the isolation boundary. scan_prose.py derives vendor/python from its own real path, inserts it at sys.path[0], invalidates import caches, imports markdown_it and mdurl, and verifies every relevant module's resolved __file__ is beneath that exact vendor root. It also verifies markdown_it.__version__ == 3.0.0 and the expected mdurl version metadata. Any origin or version mismatch produces capability_unavailable rather than attempting to delete or replace entries in sys.modules.
- If an embeddable adapter is exposed, it must fail closed when markdown_it or mdurl is already cached from another origin. Mutating sys.modules is unsafe because parser modules use absolute imports and other application code may hold references. Document the CLI as the supported isolation mechanism.
- Test the packaged artifact, not the source checkout: copy/install the complete plugin into a temporary layout, run the installed scripts/scan_prose.py with an absolute interpreter under python -I -S, set the working directory outside the plugin, clear Python-related environment variables, and scan a Markdown fixture. -I intentionally ignores PYTHONPATH; -S excludes site initialization. Assert status=ok plus an optional diagnostic capability record containing resolved vendor-relative origins and versions.
- Add two isolation-negative tests in fresh subprocesses: remove/rename the packaged vendor tree and expect exit 10; replace the vendored version or module with an incompatible fixture and expect exit 10 with reason=version_mismatch or origin_mismatch. A disposable container or clean virtual environment provides the strongest release test that no global markdown-it-py is installed, but -I -S is the deterministic test used in the normal suite.
- Parse Markdown with the CommonMark preset and no linkify extension. Walk block and inline tokens while maintaining source-line mappings. Drop fenced code, indented code, HTML blocks, blockquotes by default, inline code, and link destinations; retain visible link labels, headings, list text, emphasis metadata, and paragraph boundaries.
- Perform bare-URL removal only within eligible text-token spans, never across token boundaries. Match ASCII case-insensitively: schemes https?:// followed by a non-space run; www. followed by a DNS-like host; or a DNS-like host with at least one dot and a pinned ASCII TLD allowlist, followed by an optional port/path/query/fragment. Require a left boundary that is neither a letter, digit, underscore, nor @; exclude email-domain matches. Strip trailing . , : ; ! ? and unmatched closing ) ] } while preserving balanced delimiters inside the URL. Freeze the TLD allowlist, regex, trimming algorithm, Unicode policy, and fixtures as part of the extraction profile.
- Source locations survive URL removal by representing extracted text as source-mapped spans rather than concatenated strings. Fixtures cover schemes, www, bare domains, ports, query strings, fragments, balanced parentheses, terminal punctuation, Markdown links, autolinks, emails, Unicode domains, code, HTML, and adjacent prose.
- Ship sentence-length distribution/dispersion, punctuation rates, paragraph sentence-count runs, and bold-label density as normal-confidence deterministic metrics. Ship repeated openers and transition clusters as medium-confidence candidate selectors. Ship vague-attribution and stock-lexical clusters as low-confidence lexical indicators with that confidence recorded in threshold_profile; their soft flags remain advisory and independently suppressible.
- Define repeated openers over eligible sentences in document order. Tokenize lexical words with a pinned Unicode-aware rule that preserves internal apostrophes and treats a leading negator—no, not, never, neither, nor—as lexical. Remove structural list markers before tokenization, casefold, normalize apostrophe variants, and form 1-, 2-, and 3-token prefixes only when the sentence has at least two lexical tokens and contains enough tokens for that prefix length. Within each rolling window of eight sentences, count a normalized prefix once when it occurs in at least three distinct sentences; report the contributing sentences and prefix length without double-counting the same sentence/prefix/window combination.
- Make stock lexical matching phrase-only and table-driven. Initial named clusters: conclusion framing {in conclusion, to sum up, all things considered}; significance framing {it is important to note, it is worth noting, serves as a reminder, stands as a testament}; broad-change framing {in today's rapidly changing, in an ever-evolving, rapidly evolving landscape}; essence framing {at its core, at the heart of}; duality framing {not only ... but also, not just ... but}; and generic navigation {delve into, sheds light on, paves the way for}. Require exact normalized token sequences, except the two explicitly bounded duality templates; do not match isolated words such as important, landscape, crucial, testament, or delve. Version the table separately from metric code and report both cluster and matched phrase.
- Pin transition clusters as an explicit multi-token phrase table and calculate occurrences per 1,000 eligible prose words. Avoid treating isolated conjunctions such as however, moreover, or therefore as inherently meaningful unless fixtures establish a narrowly defined sentence-initial pattern.
- Defer cadence-similarity from MVP. It lacks a stable parameterization and overlaps sentence-length dispersion and paragraph-run measurements. Add it only after defining its representation, distance function, comparison window, minimum sample size, and fixtures; do not publish a placeholder metric.
- Acquire vendored dependencies from immutable upstream release artifacts, preferably PyPI sdists downloaded in a controlled update step—not copied from a developer's installed environment and not fetched dynamically during the product build. Record package name, version, canonical artifact URL, artifact SHA-256, upstream project URL, license identifier, extracted license hash, included/excluded paths, patch status, and the exact repeatable update/verification commands in PROVENANCE.md.
- Keep threshold profiles separate from raw measurements. Every metric result names metric_version, extraction_profile, threshold_profile, confidence, and purpose=candidate_selection_only. A profile may set soft_flag=null for low-confidence metrics until thresholds have fixture and corpus evidence.

## Risks

- Checking only __version__ is insufficient: an environment package can report the pinned version while differing in files or import origin. Origin checks and release-time artifact hashes are both required.
- python -I -S proves independence from ordinary site-packages but does not by itself prove a machine has no global installation. The clean-container release test closes that evidentiary gap.
- Vendored parser internals may import modules lazily after the initial capability check. Validate origins after parsing a representative fixture as well as immediately after import, or enumerate the expected markdown_it and mdurl module origins.
- CommonMark token maps are generally line-oriented, so exact columns may not always be recoverable. The public location contract should explicitly promise line ranges and only promise columns where the adapter can derive them deterministically.
- Bare-domain detection can remove prose containing dotted identifiers or version-like strings. A pinned TLD allowlist and strict host-label rules reduce false positives but require deliberate versioned updates.
- Sentence segmentation implemented with stdlib heuristics will mishandle some abbreviations, initials, decimals, and multilingual punctuation. Its abbreviation table and Unicode rules must be fixture-pinned and exposed as part of the metric version.
- Rolling-window repeated-opener counts can inflate when overlapping windows report the same pattern. Canonicalize findings by prefix plus maximal contiguous sentence/window range before producing count and locations.
- Bold-label density depends on a precise definition of label, such as strong text at the start of a paragraph or list item followed by punctuation. Counting all bold spans would measure emphasis rather than labels.
- Vague-attribution and stock phrase metrics are highly genre-sensitive. Even deterministic matching can invite verdict-like interpretation, so confidence and candidate-selection-only purpose must be prominent in every result.
- Collapsing malformed input and scanner defects into exit 1 is acceptable for automation but less diagnostic. Preserve machine-readable reason and error_kind fields so callers need not infer meaning from the code.

## Sketch

CLI
  parse arguments
  if --format missing/invalid -> JSON(status=format_required), exit 2
  open UTF-8 input or stdin
  if format=text:
    stdlib extraction -> source-mapped structural units
  else:
    locate <installed-plugin>/vendor/python
    capability_gate(vendor_root):
      prepend exact root; invalidate caches
      reject conflicting cached modules
      import markdown_it + mdurl
      verify versions and resolved origins
    unavailable -> JSON(status=capability_unavailable, metrics=null), stderr, exit 10
    CommonMark parse -> token filter -> visible-span extraction -> bare-URL removal
    recheck all loaded parser-module origins
  units -> pinned sentence/word segmentation -> metric functions
  emit JSON(status=ok, format, profiles, metrics), exit 0

Metric result
  {
    eligible_units: <integer or typed unit map>,
    count: <integer or null>,
    rate: <number or null>,
    locations: [...],
    soft_flag: <boolean or null>,
    threshold_profile: {
      id: "scanner-mvp-v1",
      metric_version: "...",
      extraction_profile: "commonmark-3.0.0-v1" | "text-v1",
      confidence: "normal" | "medium" | "low",
      purpose: "candidate_selection_only"
    }
  }

Release verification
  installed temporary plugin layout
    -> interpreter -I -S /absolute/plugin/scripts/scan_prose.py --format markdown fixture.md
    -> assert ok, expected fixture metrics, vendored origins
    -> vendor absent test: exit 10
    -> vendor incompatible test: exit 10
    -> clean container with no installed dependency: same golden result

---
_Peer proposal (report-only). Synthesize at your discretion._
