"""Edit-script primitives: apply, reconstruct, derive, and map original->revision offsets.

The candidate envelope carries an ordered, non-overlapping edit script in ORIGINAL byte
coordinates. Reconstructing the revision from (original + edits) and checking its sha256
makes edit-authorization, protected-span mapping, and provenance deterministic — no
ambiguous substring matching (peer-consult 2026-07-12).
"""

from __future__ import annotations

import base64
import difflib
import hashlib
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence


class EditError(ValueError):
    """Malformed edit script: out of bounds, inverted, or overlapping."""


class MapError(ValueError):
    """An original offset falls inside a replaced span and cannot be mapped."""


@dataclass(frozen=True)
class Edit:
    """A replacement of original[start_byte:end_byte) with ``replacement`` bytes.

    Half-open interval in ORIGINAL coordinates. start_byte == end_byte is a pure
    insertion at that offset.
    """

    start_byte: int
    end_byte: int
    replacement: bytes
    # #43: OPTIONAL self-check — the expected sha256 (hex) of original[start_byte:end_byte). When set,
    # apply_edits rejects the script if the doc's bytes at that range don't match (a stale/drifted
    # script whose offsets stayed in bounds). None (the default) = no check → byte-identical to pre-#43.
    preimage_sha256: Optional[str] = None

    @property
    def is_insertion(self) -> bool:
        return self.start_byte == self.end_byte

    @property
    def orig_len(self) -> int:
        return self.end_byte - self.start_byte


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_edits(raw_edits: Sequence[dict]) -> List[Edit]:
    """Parse envelope ``edits`` (replacement carried base64 as ``replacement_b64``)."""
    out: List[Edit] = []
    for e in raw_edits:
        if "replacement_b64" in e:
            repl = base64.b64decode(e["replacement_b64"])
        elif "replacement" in e:
            r = e["replacement"]
            repl = r if isinstance(r, bytes) else str(r).encode("utf-8")
        else:
            repl = b""
        # #43: optional expected preimage — accept either the raw bytes (preimage_b64) or a bare
        # sha256 hex (preimage_sha256); both normalize to a hex digest checked in _validated_sorted.
        pre: Optional[str] = None
        if "preimage_b64" in e:
            pre = sha256_hex(base64.b64decode(e["preimage_b64"]))
        elif "preimage_sha256" in e:
            pre = str(e["preimage_sha256"]).strip().lower()
        out.append(Edit(int(e["start_byte"]), int(e["end_byte"]), repl, pre))
    return out


def _validated_sorted(original: bytes, edits: Sequence[Edit]) -> List[Edit]:
    original_len = len(original)
    for e in edits:
        if not (0 <= e.start_byte <= e.end_byte <= original_len):
            raise EditError(
                f"edit out of bounds or inverted: [{e.start_byte},{e.end_byte}) "
                f"against original length {original_len}"
            )
        # #43: self-checking edit-script — reject a range whose doc bytes don't match its declared
        # preimage (bounds/overlap can pass while the script is stale against a drifted doc).
        if e.preimage_sha256 is not None:
            actual = sha256_hex(original[e.start_byte:e.end_byte])
            if actual != e.preimage_sha256:
                raise EditError(
                    f"preimage mismatch at [{e.start_byte},{e.end_byte}): expected "
                    f"{e.preimage_sha256[:12]}…, doc has {actual[:12]}… (stale/drifted edit-script)"
                )
    ordered = sorted(edits, key=lambda e: (e.start_byte, e.end_byte))
    for a, b in zip(ordered, ordered[1:]):
        if a.end_byte > b.start_byte:
            raise EditError(
                f"overlapping edits: [{a.start_byte},{a.end_byte}) and "
                f"[{b.start_byte},{b.end_byte})"
            )
        if (
            a.end_byte == b.start_byte
            and a.is_insertion
            and b.is_insertion
            and a.start_byte == b.start_byte
        ):
            raise EditError(
                f"two insertions at the same offset {a.start_byte} (ambiguous order)"
            )
    return ordered


def apply_edits(original: bytes, edits: Sequence[Edit]) -> bytes:
    """Reconstruct the revision by splicing edits into ``original``."""
    ordered = _validated_sorted(original, edits)
    out = bytearray()
    cursor = 0
    for e in ordered:
        out += original[cursor : e.start_byte]
        out += e.replacement
        cursor = e.end_byte
    out += original[cursor:]
    return bytes(out)


def derive_edits(original: bytes, revision: bytes) -> List[Edit]:
    """Derive a minimal edit script from byte-only output (provenance: inferred).

    Used to adapt external baselines (humanizer, original-unchanged) that emit revised
    bytes without an explicit script. difflib operates on the byte sequences directly.
    """
    matcher = difflib.SequenceMatcher(a=original, b=revision, autojunk=False)
    edits: List[Edit] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits.append(Edit(i1, i2, revision[j1:j2]))
    return edits


def map_offset(edits: Sequence[Edit], off: int) -> int:
    """Map an ORIGINAL byte offset to the corresponding REVISION offset.

    Raises MapError if ``off`` lies strictly inside a replaced span (ambiguous).
    Offsets at an edit boundary (== start_byte or == end_byte) map cleanly.
    """
    ordered = sorted(edits, key=lambda e: (e.start_byte, e.end_byte))
    delta = 0
    for e in ordered:
        if e.end_byte <= off:
            delta += len(e.replacement) - e.orig_len
        elif e.start_byte >= off:
            break
        else:  # e.start_byte < off < e.end_byte
            raise MapError(
                f"offset {off} is inside replaced span [{e.start_byte},{e.end_byte})"
            )
    return off + delta


def map_region(edits: Sequence[Edit], start: int, end: int) -> tuple[int, int]:
    """Map an original [start, end) region to revision coordinates (fail-closed)."""
    return map_offset(edits, start), map_offset(edits, end)


def edit_map_fn(edits: Sequence[Edit]) -> Callable[[int], int]:
    ordered = sorted(edits, key=lambda e: (e.start_byte, e.end_byte))
    return lambda off: map_offset(ordered, off)


def map_region_status(edits: Sequence[Edit], start: int, end: int):
    """Map an original [start, end) region AND report its status (ledger-verify design R6).

    Returns ``(interval_or_None, status)`` where status is one of:
      - ``unchanged``: no edit intersects the region.
      - ``modified``: an edit intersects, but both boundaries map cleanly.
      - ``deleted``: an edit fully covers the region -> a tombstone at the mapped insertion
        point (a zero-width interval), NOT an empty successful mapping.
      - ``ambiguous``: a boundary falls strictly inside an edit (cannot map cleanly).

    Backward-compatible NEW function; ``map_region`` is unchanged. Under a non-overlapping
    ordered splice a source interval maps to ONE contiguous revision interval.
    """
    ordered = sorted(edits, key=lambda e: (e.start_byte, e.end_byte))
    for e in ordered:
        if e.orig_len > 0 and e.start_byte <= start and e.end_byte >= end:
            point = map_offset(ordered, e.start_byte)
            return ((point, point), "deleted")
    try:
        rs = map_offset(ordered, start)
        re = map_offset(ordered, end)
    except MapError:
        return (None, "ambiguous")
    intersects = any(not (e.end_byte <= start or e.start_byte >= end) for e in ordered)
    return ((rs, re), "modified" if intersects else "unchanged")
