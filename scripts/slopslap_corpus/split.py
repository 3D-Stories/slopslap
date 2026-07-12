"""Family-level disjoint split over the provenance manifest (design #30 §5).

The leak guard is keyed on ``source_family``, NOT item_id or content hash: every item from
one family lands in the SAME partition, so near-duplicate passages (e.g. 29 pairs from one
Wikipedia guide) cannot scatter across the calibration/held-out boundary and leak.
"""

from __future__ import annotations

from typing import List

from .manifest import ManifestError


def calibration_items(manifest: List[dict]) -> List[dict]:
    return [it for it in manifest if it.get("split") == "calibration"]


def held_out_items(manifest: List[dict]) -> List[dict]:
    return [it for it in manifest if it.get("split") == "held_out"]


def assert_split_disjoint(manifest: List[dict]) -> None:
    """Raise if any source_family appears in BOTH partitions (the real leak-proofness guard)."""
    cal = {it["source_family"] for it in calibration_items(manifest)}
    held = {it["source_family"] for it in held_out_items(manifest)}
    overlap = cal & held
    if overlap:
        raise ManifestError(
            f"source_family spans both partitions (family-level leak): {sorted(overlap)}"
        )
