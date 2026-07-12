"""Fail-closed loader for the provenance manifest (#30 Task 1).

Every mislabeled or unlabeled line is a ManifestError, never a silent accept into a lane.
Tests build small tmp manifests so they exercise the loader, not the committed file.
"""

import json

import pytest

from slopslap_corpus.manifest import ManifestError, load_manifest


def _item(**over):
    base = {
        "source_id": "01",
        "item_id": "01-a",
        "source_family": "wikipedia",
        "citation": "Wikipedia: Signs of AI writing",
        "revision": "2026-07-12",
        "license": "CC-BY-SA-4.0",
        "allowed_uses": ["fixture", "calibration"],
        "redistribution": "share-alike",
        "attribution": "Wikipedia contributors, CC BY-SA 4.0",
        "direction": "ai_to_human",
        "tells": ["copula_avoidance"],
        "genre": "encyclopedic",
        "control": False,
        "after_validity": "faithful",
        "artifact_lanes": ["fixture", "calibration"],
        "content_hashes": {"before": None, "after": None},
        "lineage": "derived from the CC BY-SA guide",
        "notes": "",
        "split": "held_out",
    }
    base.update(over)
    return base


def _write(tmp_path, items):
    p = tmp_path / "m.jsonl"
    p.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")
    return str(p)


def test_valid_manifest_loads(tmp_path):
    path = _write(tmp_path, [_item(), _item(item_id="01-b")])
    got = load_manifest(path)
    assert len(got) == 2
    assert got[0]["source_family"] == "wikipedia"
    assert got[0]["artifact_lanes"] == ["fixture", "calibration"]


def test_blank_lines_are_skipped(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text(json.dumps(_item()) + "\n\n" + json.dumps(_item(item_id="b")) + "\n",
                 encoding="utf-8")
    assert len(load_manifest(str(p))) == 2


def test_malformed_line_raises(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text(json.dumps(_item()) + "\n{not valid json}\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(str(p))


def test_non_object_line_raises(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(str(p))


def test_missing_required_field_raises(tmp_path):
    it = _item()
    del it["citation"]
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [it]))


def test_unknown_lane_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(artifact_lanes=["fixture", "bogus_lane"])]))


def test_artifact_lanes_must_be_nonempty_list(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(artifact_lanes=[])]))
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(artifact_lanes="fixture")]))


def test_unknown_after_validity_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(after_validity="maybe")]))


def test_unknown_direction_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(direction="sideways")]))


def test_content_hashes_must_be_before_after_object(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(content_hashes=["x"])]))
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(content_hashes={"before": None})]))


def test_bad_split_value_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [_item(split="train")]))


def test_split_on_lane_without_calibration_or_judge_raises(tmp_path):
    # a fixture-only item may not carry a non-null split (design §1 self-review H6)
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path,
                             [_item(artifact_lanes=["fixture"], split="calibration")]))
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path,
                             [_item(artifact_lanes=["inspiration"], split="held_out")]))


def test_null_split_on_fixture_only_item_ok(tmp_path):
    got = load_manifest(_write(tmp_path, [_item(artifact_lanes=["fixture"], split=None)]))
    assert got[0].get("split") is None


def test_judge_reference_lane_may_carry_split(tmp_path):
    got = load_manifest(_write(tmp_path,
                               [_item(artifact_lanes=["judge_reference"], split="held_out")]))
    assert got[0]["split"] == "held_out"


def test_conflicting_family_split_raises(tmp_path):
    a = _item(item_id="a", split="calibration")
    b = _item(item_id="b", split="held_out")  # same family "wikipedia"
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, [a, b]))
