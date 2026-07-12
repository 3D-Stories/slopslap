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


# --- regression: the SHIPPED manifest's common-origin families never span partitions ---
def test_shipped_manifest_common_origin_does_not_leak():
    """Step-11 Critical regression: the humanizer skill is a Wikipedia-Signs-of-AI-writing
    DERIVATIVE (identical before-passages in both fetch files), so drawing the split boundary
    at the fetch-file level (wikipedia vs humanizer) leaked identical content across the
    calibration/held-out line while the family-string check passed. They are now ONE family
    (`wikipedia-signs-guide`) in a single partition. Anchor that so the leak can't silently
    return: no wiki-*/hum-* item may land in a different partition from its siblings, and the
    real shipped manifest stays family-disjoint."""
    import json, os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    man = [json.loads(l) for l in open(os.path.join(repo, "research/ai-slop-corpus/corpus_manifest.jsonl")) if l.strip()]
    assert_split_disjoint(man)  # no source_family spans both partitions
    # every Wikipedia-guide-derived item (wiki-* and hum-*) shares ONE family + ONE split
    origin_items = [it for it in man if it["item_id"].startswith(("wiki-", "hum-"))]
    assert origin_items, "expected wiki-/hum- items in the shipped manifest"
    fams = {it["source_family"] for it in origin_items}
    splits = {it.get("split") for it in origin_items}
    assert fams == {"wikipedia-signs-guide"}, f"common-origin items scattered across families: {fams}"
    assert splits == {"calibration"}, f"common-origin items scattered across splits: {splits}"
