"""Family-level disjoint split (#30 Task 1).

The leak guard is keyed on source_family, not item_id or content hash: near-duplicate
passages from one family must never scatter across the calibration/held-out boundary.
"""

import pytest

from slopslap_corpus.manifest import ManifestError
from slopslap_corpus.split import (
    assert_split_disjoint,
    calibration_items,
    held_out_items,
)


def _it(family, split, item_id, lanes=("calibration",)):
    return {
        "source_family": family,
        "split": split,
        "item_id": item_id,
        "artifact_lanes": list(lanes),
    }


def _clean():
    return [
        _it("humanizer", "calibration", "h1"),
        _it("humanizer", "calibration", "h2"),
        _it("wikipedia", "held_out", "w1"),
        _it("blog", None, "b1", lanes=("inspiration",)),
    ]


def test_partitions_filter_by_split():
    man = _clean()
    assert {it["item_id"] for it in calibration_items(man)} == {"h1", "h2"}
    assert {it["item_id"] for it in held_out_items(man)} == {"w1"}


def test_null_split_items_are_in_neither_partition():
    man = _clean()
    ids = {it["item_id"] for it in calibration_items(man) + held_out_items(man)}
    assert "b1" not in ids


def test_assert_disjoint_passes_on_clean_split():
    assert_split_disjoint(_clean())  # no raise


def test_assert_disjoint_raises_when_family_spans_both():
    man = [
        _it("humanizer", "calibration", "h1"),
        _it("humanizer", "held_out", "h2"),  # same family in BOTH partitions
    ]
    with pytest.raises(ManifestError):
        assert_split_disjoint(man)
