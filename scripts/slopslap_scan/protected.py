"""Protected-span auto-extractor for arbitrary input (#18).

Emits ``protected_spans[]`` of ``{start_byte, end_byte, sha256, kind}`` for any document,
so ``slopslap_verification.ledger.build_ledger`` can protect real docs the way the eval
fixtures / kukakuka PRD were hand-authored. It REUSES the scan tokenizer rather than adding
a second parser:

  * the vendored/pinned markdown-it CommonMark parser classifies code fences, indented code,
    blockquotes, and inline code — the same categories ``extract.extract_markdown`` drops
    from prose;
  * the ``extract`` module's URL matchers (``_SCHEME`` / ``_WWW`` / ``_BARE`` + ``_TRAIL``)
    locate bare URLs AND ``[label](dest)`` link destinations.

markdown-it block tokens carry line maps but inline tokens carry NO source position, so
inline code is located by scanning each inline block's source for CommonMark backtick runs
IN ORDER and cross-checking the count against the parser's ``code_inline`` tokens; on any
mismatch that block's inline code is skipped rather than risk a wrong offset (ponytail:
documented completeness ceiling — byte-exactness is never traded away).

Byte offsets are EXACT (UTF-8, computed by encoding the char prefix — never char offsets)
and spans are pairwise NON-OVERLAPPING as ``build_ledger``/``validate_ledger`` require. When
candidates overlap, the higher-priority kind wins: block code/blockquote > inline
code/identifier > url (a URL inside a fenced block is subsumed by the block).
"""

from __future__ import annotations

import hashlib
import re
from typing import List

from .capability import PINNED
from .extract import _BARE, _SCHEME, _TRAIL, _WWW

# CommonMark inline code: a run of N backticks, content, a matching run of N backticks not
# flanked by a backtick of the same run. DOTALL so a span may cover a soft line break.
_INLINE_CODE = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)", re.DOTALL)
# an identifier-like inline code content: a single token (no whitespace) of word chars plus
# the punctuation common to API names / paths / header names (dot, slash, hyphen).
_IDENTIFIER = re.compile(r"[\w./\-]+")

# overlap priority (lower wins): a block code/blockquote subsumes an inline/url candidate.
_PRIORITY = {"code": 0, "blockquote": 0, "inline_code": 1, "identifier": 1, "url": 2}


class ProtectedSpanError(RuntimeError):
    """The pinned CommonMark parser is unavailable, so code/blockquote spans cannot be
    classified. Failing loud beats silently emitting URL-only spans and leaving a fenced
    block unprotected (same discipline as ledger.LedgerBuildError)."""


def _markdown_it_cls():
    try:
        import markdown_it  # noqa: PLC0415
    except Exception as err:  # noqa: BLE001
        raise ProtectedSpanError(f"markdown-it-py not importable: {err}") from err
    version = getattr(markdown_it, "__version__", None)
    if version != PINNED["markdown_it"]:
        raise ProtectedSpanError(
            f"markdown-it-py version {version!r} != pinned {PINNED['markdown_it']!r}"
        )
    return markdown_it.MarkdownIt


def _line_starts(raw: bytes) -> List[int]:
    """Byte offset of the start of each source line, plus a sentinel == len(raw)."""
    starts = [0]
    for i, b in enumerate(raw):
        if b == 0x0A:  # '\n'
            starts.append(i + 1)
    starts.append(len(raw))
    return starts


def _trim_trailing_newlines(raw: bytes, start: int, end: int) -> int:
    """A block token's line map ends on the line AFTER the block; drop trailing newline bytes
    so the span ends on the block's last content byte (matches the fixtures' code spans)."""
    while end > start and raw[end - 1:end] == b"\n":
        end -= 1
    return end


def extract_protected_spans(doc: bytes) -> List[dict]:
    """Return byte-exact, non-overlapping protected spans for ``doc`` (UTF-8 bytes).

    Each span is ``{start_byte, end_byte, sha256, kind}`` where ``sha256`` is the hex SHA-256
    of ``doc[start_byte:end_byte]`` (the editscript.sha256_hex convention) and ``kind`` is one
    of ``code`` | ``blockquote`` | ``inline_code`` | ``identifier`` | ``url``. The list is
    sorted by ``start_byte`` and is safe to drop straight into a build_ledger manifest.
    """
    if not doc:
        return []
    markdown_it_cls = _markdown_it_cls()
    text = doc.decode("utf-8", errors="replace")
    line_start = _line_starts(doc)

    def line_byte(ln: int) -> int:
        return line_start[ln] if ln < len(line_start) else len(doc)

    def char_to_byte(base: int, seg_text: str, char_off: int) -> int:
        return base + len(seg_text[:char_off].encode("utf-8"))

    md = markdown_it_cls("commonmark")
    tokens = md.parse(text)

    # (start, end, kind) candidates; resolved for overlap at the end.
    cands: List[tuple] = []
    bq_depth = 0  # blockquote_close carries no map, so emit from the OUTERMOST open's span.
    for tok in tokens:
        if tok.type in ("fence", "code_block") and tok.map:
            s = line_byte(tok.map[0])
            e = _trim_trailing_newlines(doc, s, line_byte(tok.map[1]))
            if e > s:
                cands.append((s, e, "code"))
        elif tok.type == "blockquote_open":
            if bq_depth == 0 and tok.map:  # outermost open's map covers nested quotes too
                s = line_byte(tok.map[0])
                e = _trim_trailing_newlines(doc, s, line_byte(tok.map[1]))
                if e > s:
                    cands.append((s, e, "blockquote"))
            bq_depth += 1
        elif tok.type == "blockquote_close":
            bq_depth = max(0, bq_depth - 1)
        elif tok.type == "inline" and tok.map:
            base = line_byte(tok.map[0])
            seg_text = doc[base:line_byte(tok.map[1])].decode("utf-8", errors="replace")
            code_tokens = [c for c in (tok.children or []) if c.type == "code_inline"]
            matches = list(_INLINE_CODE.finditer(seg_text))
            # only trust the alignment when the count matches the parser exactly.
            if len(matches) != len(code_tokens):
                continue
            for m in matches:
                s = char_to_byte(base, seg_text, m.start())
                e = char_to_byte(base, seg_text, m.end())
                content = m.group(2).strip()
                kind = "identifier" if _IDENTIFIER.fullmatch(content) else "inline_code"
                cands.append((s, e, kind))

    # URLs (bare + link destinations). Push trailing sentence punctuation / closing brackets
    # back out of the span exactly as extract.strip_urls does, so the span is the URL only.
    for pattern in (_SCHEME, _WWW, _BARE):
        for m in pattern.finditer(text):
            frag = m.group(0)
            char_end = m.end()
            while frag and frag[-1] in _TRAIL:
                frag = frag[:-1]
                char_end -= 1
            if char_end > m.start():
                s = len(text[:m.start()].encode("utf-8"))
                e = len(text[:char_end].encode("utf-8"))
                cands.append((s, e, "url"))

    # resolve overlaps: prefer earlier start, then higher priority, then longer span; drop any
    # candidate that intersects one already accepted -> a pairwise-disjoint set.
    cands.sort(key=lambda c: (c[0], _PRIORITY[c[2]], -(c[1] - c[0])))
    accepted: List[tuple] = []
    for s, e, kind in cands:
        if any(not (e <= a_s or s >= a_e) for a_s, a_e, _ in accepted):
            continue
        accepted.append((s, e, kind))

    accepted.sort()
    return [
        {"start_byte": s, "end_byte": e,
         "sha256": hashlib.sha256(doc[s:e]).hexdigest(), "kind": kind}
        for s, e, kind in accepted
    ]
