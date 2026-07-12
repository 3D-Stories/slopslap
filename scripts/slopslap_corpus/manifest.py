"""Provenance manifest: one JSON object per LINE, per corpus ITEM (design #30 §1).

Fail-closed loader: a malformed line, a missing required field, an unknown lane/enum, or a
misplaced ``split`` is a ``ManifestError`` — never a silent accept of an unlabeled item into
a lane. Two orthogonal axes: ``artifact_lanes`` (a LIST: the PURPOSE an item may serve) and
``split`` (the PARTITION, present only on empirically-tuned lanes). The partition is keyed on
``source_family`` so near-duplicate passages cannot leak across the calibration/held-out line.
"""

from __future__ import annotations

import json
from typing import List

# design §1: 18 required per-item fields.
REQUIRED_FIELDS = (
    "source_id",
    "item_id",
    "source_family",
    "citation",
    "revision",
    "license",
    "allowed_uses",
    "redistribution",
    "attribution",
    "direction",
    "tells",
    "genre",
    "control",
    "after_validity",
    "artifact_lanes",
    "content_hashes",
    "lineage",
    "notes",
)

VALID_LANES = {"fixture", "judge_reference", "calibration", "inspiration"}
VALID_AFTER_VALIDITY = {"faithful", "fabricated", "indeterminate", "none"}
VALID_DIRECTION = {"ai_to_human", "human_to_ai", "before_only"}
VALID_SPLIT = {"calibration", "held_out"}
# split is meaningful only on the empirically-tuned lanes (design §1).
SPLIT_ELIGIBLE_LANES = {"calibration", "judge_reference"}


class ManifestError(Exception):
    """A malformed / mislabeled manifest line — fail closed, never a silent accept."""


def load_manifest(path) -> List[dict]:
    """Parse the manifest (one JSON object per line). Raise ManifestError on any defect."""
    items: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue  # blank lines are allowed
            try:
                item = json.loads(line)
            except json.JSONDecodeError as err:
                raise ManifestError(f"line {lineno}: malformed JSON: {err}") from err
            if not isinstance(item, dict):
                raise ManifestError(f"line {lineno}: not a JSON object")
            _validate_item(item, lineno)
            items.append(item)
    _validate_family_splits(items)
    return items


def _validate_item(item: dict, lineno: int) -> None:
    for field in REQUIRED_FIELDS:
        if field not in item:
            raise ManifestError(f"line {lineno}: missing required field '{field}'")

    lanes = item["artifact_lanes"]
    if not isinstance(lanes, list) or not lanes:
        raise ManifestError(f"line {lineno}: artifact_lanes must be a non-empty list")
    for lane in lanes:
        if lane not in VALID_LANES:
            raise ManifestError(f"line {lineno}: unknown artifact_lane '{lane}'")

    if item["after_validity"] not in VALID_AFTER_VALIDITY:
        raise ManifestError(
            f"line {lineno}: unknown after_validity '{item['after_validity']}'"
        )
    if item["direction"] not in VALID_DIRECTION:
        raise ManifestError(f"line {lineno}: unknown direction '{item['direction']}'")

    ch = item["content_hashes"]
    if not isinstance(ch, dict) or "before" not in ch or "after" not in ch:
        raise ManifestError(
            f"line {lineno}: content_hashes must be an object with 'before' and 'after'"
        )

    split = item.get("split")
    if split is not None:
        if split not in VALID_SPLIT:
            raise ManifestError(
                f"line {lineno}: split '{split}' not in {sorted(VALID_SPLIT)}"
            )
        if not set(lanes) & SPLIT_ELIGIBLE_LANES:
            raise ManifestError(
                f"line {lineno}: split present but lanes {lanes} include neither "
                "'calibration' nor 'judge_reference'"
            )


def _validate_family_splits(items: List[dict]) -> None:
    """A source_family must not carry conflicting split values across items (the leak guard,
    enforced at load-time; ``split.assert_split_disjoint`` re-proves it at partition time)."""
    by_family: dict = {}
    for item in items:
        split = item.get("split")
        if split is None:
            continue
        by_family.setdefault(item["source_family"], set()).add(split)
    for family, splits in by_family.items():
        if len(splits) > 1:
            raise ManifestError(
                f"source_family '{family}' has conflicting split values {sorted(splits)}"
            )
