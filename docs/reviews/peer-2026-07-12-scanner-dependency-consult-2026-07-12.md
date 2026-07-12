# Peer Consult — 2026-07-12-scanner-dependency-consult.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Ranked recommendation: (1) MVP ships the stdlib-only plain-text scanner and treats Markdown scanning as an explicitly unavailable capability; Markdown input must never be passed through the plain-text measurement path. Emit a conspicuous, machine-readable capability result and let the advisory pipeline skip those metrics. (2) When Markdown support is enabled for general users, vendor pinned, tested copies of markdown-it-py and its transitive runtime dependencies inside a private plugin directory, including licenses and provenance. This best satisfies zero-config, deterministic behavior, offline operation, and correct region selection. (3) Permit an explicitly configured system installation only as an advanced/development option with a tested version range; do not make it the normal install path. Do not auto-install packages at runtime. Do not implement a home-grown stdlib CommonMark subset: the exclusion requirements cross block and inline parsing boundaries, so a supposed subset would become an approximate parser under another name.

## Key decisions

- Use capability gating by input format: plain text remains available with stdlib only; Markdown is either parsed by a conforming parser or reported unavailable.
- Represent Markdown unavailability as a distinct result such as status=capability_unavailable, capability=markdown_commonmark, metrics=null. Also print a concise stderr notice. Never emit zero-valued or partial metrics that could look authoritative.
- Give capability absence a dedicated exit code or result state that the caller explicitly converts into an advisory skip; reserve ordinary failure states for malformed input or scanner defects.
- Vendor exact parser versions for the production Markdown capability, load them from a plugin-private path, and test that environment-installed packages cannot silently change behavior.
- Record upstream version, source, hashes, licenses, and update procedure. Add CommonMark fixture tests focused on fenced and indented code, HTML blocks, blockquotes, links, autolinks, bare URLs, inline code, headings, and lists.
- Keep manual pip installation optional and explicit. If supported, validate the imported package version before scanning and report incompatibility rather than attempting best-effort operation.
- Reject runtime pip installation because execution must not depend on network access, writable environments, package-index availability, or mutation of the user's Python installation.
- Reject a custom minimal parser for production correctness. Its maintenance and conformance burden is disproportionate to an advisory scanner and would recreate the silent-wrong-region risk.
- MVP scope: ship plain-text measurement plus the Markdown capability contract and loud skip behavior. Vendoring and Markdown enablement can follow as a separately tested release if Markdown support is not required for the first release.

## Risks

- Vendored dependencies increase plugin size and create license, provenance, vulnerability-monitoring, and update obligations.
- Vendored packages may assume normal package layout or include transitive dependencies; packaging tests must run from the actual installed plugin layout on Linux, macOS, and Windows.
- A caller could accidentally ignore the capability state. The output schema and integration tests must make unavailable metrics impossible to confuse with successful measurements.
- Using an optional system package can produce version-dependent tokenization unless imports are version-gated and clearly identified in diagnostic output.
- Deferring Markdown support may disappoint users, but it is safer than shipping misleading metrics and does not block the deterministic editing pipeline.
- Parser correctness alone is insufficient: converting tokens into visible prose regions can still introduce mistakes, so extraction fixtures and regression tests remain necessary.
- Bare URLs are not uniformly defined by core CommonMark behavior; the implementation must state whether a tested parser extension or a post-tokenization URL exclusion rule supplies that requirement.

## Sketch

scan_prose.py --format text|markdown\n\ntext:\n  run stdlib scanner\n  emit {status:"ok", format:"text", metrics:{...}}\n\nmarkdown:\n  load plugin-private, pinned CommonMark adapter\n  if unavailable or incompatible:\n    stderr: "Markdown metrics unavailable: CommonMark parser capability is not installed."\n    emit {status:"capability_unavailable", format:"markdown", capability:"markdown_commonmark", metrics:null}\n    exit with a documented advisory-skip code\n  else:\n    parse CommonMark tokens\n    extract only eligible visible prose while preserving heading/list tags\n    run the same measurement core\n    emit {status:"ok", format:"markdown", parser:{name:"markdown-it-py", version:"<pinned>"}, metrics:{...}}\n\nPackage layout:\n  scripts/scan_prose.py\n  scripts/slopslap_scan/markdown_adapter.py\n  vendor/python/markdown_it/...\n  vendor/python/mdurl/...\n  THIRD_PARTY_LICENSES/...\n  tests/fixtures/commonmark/...

---
_Peer proposal (report-only). Synthesize at your discretion._
