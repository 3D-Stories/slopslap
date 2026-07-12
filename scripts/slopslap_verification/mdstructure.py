"""Markdown structural invariants — NOT a vacuous "does it parse" check.

A CommonMark parser silently coerces malformed input (an unclosed fence auto-closes at
EOF; a broken link becomes literal text), so parse-success proves nothing (WF5 H3).
This module checks explicit structural invariants across the supported failure classes:

  * fenced-code fence PARITY (an even number of fence markers; an odd count means a
    closing ``` was deleted and prose was swallowed into a code block);
  * fenced code-BLOCK count preserved between original and revision;
  * link/image destination TERMINATION (every ``[...](`` opener forms a real link token).

markdown-it-py is version-gated: an environment copy whose version != the pinned one is
reported as ``version_mismatch`` (a FIXTURE_ERROR for the runner), so tokenization can't
silently drift. The #scanner increment vendors the pinned parser for the packaged plugin;
until then it is pinned in tests/requirements.txt.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

PINNED_VERSION = "3.0.0"

_FENCE_LINE_RE = re.compile(r"(?m)^\s{0,3}(?:`{3,}|~{3,})")
_LINK_OPENER_RE = re.compile(r"!?\[[^\]\n]*\]\(")


def parser_capability() -> Tuple[str, Optional[str]]:
    """Return ("ok"|"version_mismatch"|"unavailable", version_or_None)."""
    try:
        import markdown_it  # noqa: F401
    except Exception:
        return ("unavailable", None)
    version = getattr(markdown_it, "__version__", None)
    if version != PINNED_VERSION:
        return ("version_mismatch", version)
    return ("ok", version)


def _tokens(text: str):
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark")
    flat = []
    for tok in md.parse(text):
        flat.append(tok)
        if tok.children:
            flat.extend(tok.children)
    return flat


def structural_features(text: str) -> dict:
    """Structural counts used to detect Markdown damage. Requires a usable parser."""
    fence_lines = len(_FENCE_LINE_RE.findall(text))
    toks = _tokens(text)
    code_blocks = sum(1 for t in toks if t.type in ("fence", "code_block"))
    code_inline = sum(1 for t in toks if t.type == "code_inline")
    parsed_links = sum(1 for t in toks if t.type in ("link_open", "image"))
    raw_openers = len(_LINK_OPENER_RE.findall(text))
    broken_links = max(0, raw_openers - parsed_links)
    return {
        "fence_lines": fence_lines,
        "code_blocks": code_blocks,
        "code_inline": code_inline,
        "parsed_links": parsed_links,
        "raw_link_openers": raw_openers,
        "broken_links": broken_links,
    }


def compare(original: str, revision: str) -> List[str]:
    """Return a list of structural violations introduced by the revision (empty = clean)."""
    o = structural_features(original)
    r = structural_features(revision)
    violations: List[str] = []
    if r["fence_lines"] % 2 != 0:
        violations.append(
            f"unbalanced code fences in revision ({r['fence_lines']} fence markers)"
        )
    if r["code_blocks"] != o["code_blocks"]:
        violations.append(
            f"fenced code-block count changed {o['code_blocks']} -> {r['code_blocks']}"
        )
    if r["broken_links"] > o["broken_links"]:
        violations.append(
            f"introduced {r['broken_links'] - o['broken_links']} unterminated "
            f"link/image destination(s)"
        )
    if r["code_inline"] < o["code_inline"]:
        # a deleted closing backtick turns a code span into literal text (fewer code_inline
        # tokens) — an inline-code delimiter was broken (WF5-diff F2).
        violations.append(
            f"inline code-span count dropped {o['code_inline']} -> {r['code_inline']} "
            f"(broken backtick delimiter)"
        )
    return violations
