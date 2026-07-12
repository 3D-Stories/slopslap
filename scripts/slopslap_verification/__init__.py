"""slopslap deterministic verification checkers.

Pure, dependency-light gate functions shared by the eval runner (#eval-fixtures) and,
later, the layer-1 deterministic verifier (#ledger-verify). Single source of truth for
the hard gates in the spec's Evaluation decision rule.

Coordinates are ORIGINAL-byte offsets throughout (half-open [start, end)). A revision is
always described by an explicit edit script in original coordinates; positions in the
revision are obtained by transforming original offsets through that edit map, never by
substring search (repeated text makes location inference ambiguous).
"""

from .editscript import (
    Edit,
    EditError,
    MapError,
    apply_edits,
    derive_edits,
    map_offset,
    map_region,
    map_region_status,
    parse_edits,
    sha256_hex,
)

__all__ = [
    "Edit",
    "EditError",
    "MapError",
    "apply_edits",
    "derive_edits",
    "map_offset",
    "map_region",
    "map_region_status",
    "parse_edits",
    "sha256_hex",
]
