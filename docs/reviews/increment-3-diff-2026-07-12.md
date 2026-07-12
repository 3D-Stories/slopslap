# Adversarial Review — increment-3.diff

- Date: 2026-07-12
- Artifact type: diff
- Reviewer: Codex (model config-default, reasoning effort high)
- Findings: 7 (Critical 0, High 2, Medium 5, Low 0)

## Summary

The change implements a measure-only text/Markdown scanner with vendored-parser gating and multiple prose metrics. Several paths silently produce incorrect metrics, particularly excluded Markdown content, Unicode prose, nested structures, and URL handling; the diff also does not demonstrate that its required vendored dependencies are included.

## Findings

### 1. [High] correctness · high confidence — scripts/slopslap_scan/metrics.py — bold_label_density

> +def bold_label_density(units, sw, source="") -> Dict:
> +    labels = list(_BOLD_LABEL.finditer(source))

The bold-label metric scans the original source instead of the eligible extracted units. Labels inside fenced or indented code, HTML blocks, blockquotes, and other content the Markdown extraction contract excludes are therefore counted as prose labels, silently corrupting the metric and its density denominator.

**Recommendation:** Change `bold_label_density` in `scripts/slopslap_scan/metrics.py` to inspect source-mapped eligible paragraph/list-item units and their retained strong-token metadata. Add fixtures proving bold labels in every excluded Markdown construct produce no hit.

### 2. [High] correctness · high confidence — scripts/slopslap_scan/extract.py — sentence and word segmentation

> +8. **repeated openers:** eligible sentences in doc order; Unicode-aware lexical tokens preserving internal
> +   apostrophes; leading negator (no/not/never/neither/nor) is lexical; strip list markers; casefold;
> +_LEX = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")

The implementation contradicts the promised Unicode-aware tokenization: `[A-Za-z]` recognizes only ASCII letters. Accented words and non-Latin prose are partially or completely omitted from sentence lengths, word denominators, opener normalization, transition rates, and dispersion metrics, yielding silently wrong results.

**Recommendation:** Replace `_LEX` in `scripts/slopslap_scan/extract.py` with the pinned Unicode lexical-token algorithm promised by the design, and add fixtures for accented Latin text and at least one non-Latin script across word counts and repeated openers.

### 3. [Medium] completeness · high confidence — docs/planning/increment-3-scanner-design.md — Deliverables

> +- `vendor/python/markdown_it/` + `vendor/python/mdurl/` — pinned `markdown-it-py==3.0.0` + `mdurl==0.1.2`,
> +  plugin-private, version-gated import.
> +- `THIRD_PARTY_LICENSES/` — the vendored deps' licenses + provenance (upstream version / source / update
> +  procedure).

The provided diff declares the vendored parser trees, licenses, hashes, and provenance as deliverables but contains no additions under either `vendor/python/` or `THIRD_PARTY_LICENSES/`. Their presence and content are therefore unverifiable from the provided text; if they are not already present in the base tree, every Markdown scan returns `capability_unavailable` and the new Markdown success tests fail.

**Recommendation:** Add the complete pinned vendor trees and `THIRD_PARTY_LICENSES/PROVENANCE.md` to this change, including the required per-file hashes and licenses. If they already exist in the base tree, include a manifest or diff evidence tying those exact tracked contents and hashes to this increment.
**Ambiguity:** The artifact does not show whether these required paths already exist unchanged in the base revision.

### 4. [Medium] correctness · high confidence — scripts/slopslap_scan/extract.py — _visible and extract_markdown

> +6. **Bare-URL removal within eligible text spans only** (never across token boundaries), case-insensitive:
> +def _visible(children) -> str:
> +    parts = []
> +    for c in children:
> +        if c.type == "text":
> +            parts.append(c.content)
> +        elif c.type in ("softbreak", "hardbreak"):
> +            parts.append(" ")
> +    return "".join(parts)
> +            text = strip_urls(_visible(t.children or []))

All eligible text children are concatenated before URL matching, while skipped inline tokens contribute no separator. Text fragments on opposite sides of inline code or another skipped token can consequently form a synthetic domain such as `foo.com` and be removed, directly violating the rule that URL matching never crosses token boundaries. Ordinary words can likewise be fused and distort lexical metrics.

**Recommendation:** Change Markdown extraction to preserve separate source-mapped text spans and invoke `strip_urls` on each eligible text child independently. Insert an explicit word boundary or space when excluded inline tokens separate retained prose, and add a fixture such as `foo.` followed by inline code followed by `com`.

### 5. [Medium] correctness · high confidence — scripts/slopslap_scan/extract.py — bare-URL removal

> +6. **Bare-URL removal within eligible text spans only** (never across token boundaries), case-insensitive:
> +   `https?://` + non-space run · `www.` + DNS host · or DNS host + ≥1 dot + a **pinned ASCII TLD
> +   allowlist** + optional port/path/query/fragment. Left boundary ∉ {letter,digit,_,@}; exclude emails;
> +   strip trailing `.,:;!?` and unmatched closing `)]}`; keep balanced delimiters.
> +_SCHEME = re.compile(r"(?i)\bhttps?://[^\s<>()\[\]]+")
> +_WWW = re.compile(r"(?i)\bwww\.[^\s<>()\[\]]+")
> +    r"(?:[:/][^\s<>()\[\]]*)?"
> +_TRAIL = ".,:;!?"

The URL implementation does not implement the pinned contract. Scheme and `www` matches stop at every parenthesis rather than preserving balanced delimiters; `_BARE` accepts a suffix only when it begins with `:` or `/`, so a direct query or fragment such as `example.com?q=1` leaves `?q=1` as prose; and `_TRAIL` never handles unmatched `)]}`. These remnants contaminate sentence and punctuation metrics.

**Recommendation:** Replace the three independent substitutions in `strip_urls` with the specified candidate matcher plus deterministic balanced-delimiter/trailing-closer trimming. Support bare-domain suffixes beginning with `?` and `#`, and add fixtures for balanced parentheses, unmatched closers, direct queries, and fragments.

### 6. [Medium] correctness · high confidence — scripts/slopslap_scan/extract.py — extract_markdown structural state

> +        elif t.type == "heading_open":
> +            struct = "heading"
> +        elif t.type == "heading_close":
> +            struct = "paragraph"
> +        elif t.type == "list_item_open":
> +            struct = "list_item"
> +        elif t.type == "list_item_close":
> +            struct = "paragraph"

Structural context is stored in one scalar and reset to `paragraph` on every close token. After a nested list item or heading closes inside an outer list item, subsequent outer-item prose is misclassified as a paragraph, changing eligible-block counts and paragraph-run/bold-label metrics.

**Recommendation:** Replace `struct` with nesting-aware state in `extract_markdown`, restoring the enclosing structural type on close tokens. Add nested-list and heading-within-list fixtures that assert every continuation retains its outer `list_item` classification.

### 7. [Medium] correctness · high confidence — tests/test_scanner_capability.py — test_vendor_is_git_tracked_in_source

> +def test_vendor_is_git_tracked_in_source():
> +    for rel in ("vendor/python/markdown_it/__init__.py", "vendor/python/mdurl/__init__.py"):
> +        assert os.path.exists(os.path.join(REPO, rel)), f"{rel} missing (packaging must include vendor/)"

Despite its name and stated purpose, this test checks only that files exist in the working tree. Untracked or ignored vendor files satisfy it locally but disappear from a committed checkout or packaged artifact, so the safeguard can pass while the Markdown capability ships unavailable.

**Recommendation:** Change `test_vendor_is_git_tracked_in_source` to query the repository index, for example with `git ls-files --error-unmatch` for each required vendor path, or validate the exact manifest/archive produced from tracked files. Retain the existence check as a separate assertion.

---
_Report-only: this review does not edit the artifact. Findings are advisory; incorporate them at your discretion._