"""Extraction: source text/markdown -> eligible prose units with source-LINE maps.

Markdown extraction excludes fenced/indented code, HTML blocks, blockquotes, inline code,
and link destinations (keeps visible link labels + headings + list text). Bare URLs are
removed by a deterministic post-tokenization matcher (NOT a linkify extension). Locations
are LINE ranges (markdown-it token maps are line-oriented); columns are not promised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .tables import ABBREVIATIONS, TLD_ALLOWLIST


@dataclass
class Unit:
    text: str
    line_start: int  # 1-indexed inclusive
    line_end: int
    structural_type: str  # paragraph | heading | list_item
    is_label: bool = False  # markdown: a **bold label**: opener (detected from tokens)


# ---- bare-URL removal ----------------------------------------------------
_SCHEME = re.compile(r"(?i)\bhttps?://[^\s<>()\[\]]+")
_WWW = re.compile(r"(?i)\bwww\.[^\s<>()\[\]]+")
_TLD_ALT = "|".join(sorted((re.escape(t) for t in TLD_ALLOWLIST), key=len, reverse=True))
# left boundary not a word char, '@' or '.' (so emails and sub-parts don't match).
# a suffix (path/query/fragment/port) may start with : / ? or # (design R5/M5).
_BARE = re.compile(
    r"(?i)(?<![\w@.])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + _TLD_ALT + r")"
    r"(?:[:/?#][^\s<>()\[\]]*)?"
)
# trailing sentence punctuation AND unmatched closing brackets are pushed back out of a match.
_TRAIL = ".,:;!?)]}"


def _sub_keep_trailing(pattern: re.Pattern, text: str) -> str:
    """Replace each match with a space, but push trailing sentence punctuation / unmatched
    closing brackets back into the text so punctuation-rate metrics aren't distorted by a URL
    swallowing them (a URL rarely ends in these; ponytail: balanced parens inside a URL are a
    documented ceiling, not handled)."""
    out, last = [], 0
    for m in pattern.finditer(text):
        frag = m.group(0)
        keep = ""
        while frag and frag[-1] in _TRAIL:
            keep = frag[-1] + keep
            frag = frag[:-1]
        out.append(text[last : m.start()])
        out.append(" ")
        out.append(keep)
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def strip_urls(text: str) -> str:
    text = _sub_keep_trailing(_SCHEME, text)
    text = _sub_keep_trailing(_WWW, text)
    text = _sub_keep_trailing(_BARE, text)
    return text


# ---- markdown extraction -------------------------------------------------
# inline tokens that carry content but are EXCLUDED: emit a space so opposite-side text can't
# fuse into a synthetic domain / word across the boundary (WF5-diff M4).
_CONTENT_SKIP = {"code_inline", "image", "html_inline"}


def _visible(children) -> str:
    parts = []
    for c in children:
        if c.type == "text":
            parts.append(c.content)
        elif c.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif c.type in _CONTENT_SKIP:
            parts.append(" ")  # break the token boundary; content itself is dropped
        # link_open/close and emphasis wrappers carry no content and wrap contiguous label text.
    return "".join(parts)


def _is_bold_label(children) -> bool:
    """A leading **bold**: opener at the start of a block (design R5/M4/H1).

    markdown-it can emit a leading empty text token before strong_open, so skip
    empty/whitespace-only leading text.
    """
    i = 0
    while i < len(children) and children[i].type == "text" and not children[i].content.strip():
        i += 1
    if i >= len(children) or children[i].type != "strong_open":
        return False
    depth = 0
    for j in range(i, len(children)):
        c = children[j]
        if c.type == "strong_open":
            depth += 1
        elif c.type == "strong_close":
            depth -= 1
            if depth == 0:
                nxt = children[j + 1] if j + 1 < len(children) else None
                return bool(nxt and nxt.type == "text" and nxt.content.lstrip().startswith(":"))
    return False


def extract_markdown(source: str, markdown_it_cls) -> List[Unit]:
    md = markdown_it_cls("commonmark")
    tokens = md.parse(source)
    units: List[Unit] = []
    bq_depth = 0
    struct_stack: List[str] = []  # nesting-aware structural context (WF5-diff M6)
    for t in tokens:
        if t.type == "blockquote_open":
            bq_depth += 1
        elif t.type == "blockquote_close":
            bq_depth = max(0, bq_depth - 1)
        elif t.type == "heading_open":
            struct_stack.append("heading")
        elif t.type == "list_item_open":
            struct_stack.append("list_item")
        elif t.type in ("heading_close", "list_item_close"):
            if struct_stack:
                struct_stack.pop()
        elif t.type == "inline" and bq_depth == 0:
            children = t.children or []
            text = strip_urls(_visible(children))
            if text.strip():
                struct = struct_stack[-1] if struct_stack else "paragraph"
                ls, le = (t.map[0] + 1, t.map[1]) if t.map else (0, 0)
                label = struct in ("paragraph", "list_item") and _is_bold_label(children)
                units.append(Unit(text.strip(), ls, le, struct, is_label=label))
    return units


# ---- plain-text extraction (stdlib) --------------------------------------
def extract_text(source: str) -> List[Unit]:
    units: List[Unit] = []
    lines = source.split("\n")
    buf: List[str] = []
    start = None
    for idx, line in enumerate(lines, 1):
        if line.strip() == "":
            if buf:
                units.append(Unit(strip_urls(" ".join(buf)).strip(), start, idx - 1, "paragraph"))
                buf, start = [], None
        else:
            if start is None:
                start = idx
            buf.append(line.strip())
    if buf:
        units.append(Unit(strip_urls(" ".join(buf)).strip(), start, len(lines), "paragraph"))
    return [u for u in units if u.text]


# ---- sentence + word segmentation ---------------------------------------
# Unicode-aware lexical word: letters (any script) with internal apostrophes; not digits/underscore.
_LEX = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_END = re.compile(r"[.!?]+(?=\s|$)")


def words(text: str) -> List[str]:
    return _LEX.findall(text)


def split_sentences(text: str) -> List[str]:
    """Heuristic sentence split respecting the pinned abbreviation table."""
    sents, start = [], 0
    for m in _END.finditer(text):
        pre = text[start : m.start()]
        # the trailing token may carry internal dots (e.g., "e.g", "i.e", "u.s")
        tail = re.search(r"([A-Za-z][A-Za-z.]*)$", pre.rstrip())
        tok = tail.group(1).rstrip(".").lower() if tail else ""
        if tok in ABBREVIATIONS:
            continue
        chunk = text[start : m.end()].strip()
        if chunk:
            sents.append(chunk)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sents.append(tail)
    return sents


def unit_sentences(units: List[Unit]):
    """Yield (sentence, unit) for prose-bearing units (headings/list-items count as one)."""
    out = []
    for u in units:
        if u.structural_type in ("heading", "list_item"):
            out.append((u.text, u))
        else:
            for s in split_sentences(u.text):
                out.append((s, u))
    return out
