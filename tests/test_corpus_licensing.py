"""Two-sided licensing + hash-drift invariants over the committed manifest (#30 Task 2).

Licensing is the real risk: only fixture/calibration-lane items may carry redistributed
verbatim bytes, and only under a redistribution-permitting license. These tests FAIL (never
skip) so provenance metadata can never silently detach from the bytes it describes.
"""

import os

import pytest

from slopslap_corpus.manifest import load_manifest
from slopslap_corpus.split import assert_split_disjoint
from slopslap_verification.editscript import sha256_hex

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO, "research", "ai-slop-corpus", "corpus_manifest.jsonl")

REDISTRIBUTABLE = {"permitted", "share-alike"}


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(MANIFEST_PATH)


def test_manifest_loads_and_split_is_family_disjoint(manifest):
    assert len(manifest) > 0
    assert_split_disjoint(manifest)  # no source_family spans both partitions


# (a) NEGATIVE: no inspiration-lane item ships a committed verbatim fixture file.
def test_no_inspiration_item_ships_verbatim(manifest):
    for it in manifest:
        if "inspiration" in it["artifact_lanes"]:
            vp = it.get("verbatim_path")
            assert vp is None, f"{it['item_id']}: inspiration lane must not name verbatim file {vp}"
            assert it["content_hashes"]["before"] is None
            assert it["content_hashes"]["after"] is None


# (b) POSITIVE: any item that ACTUALLY commits verbatim bytes is licensed AND attributed.
# Gate on committed bytes (a real verbatim_path), NOT on lane label (Step-11 diff-review H2):
# a judge_reference-only item could name a verbatim_path under a prohibited license and slip a
# lane-keyed check. The invariant is "committed bytes ⇒ redistributable license + attribution",
# independent of which lane the item claims.
def test_committed_verbatim_items_are_licensed_and_attributed(manifest):
    checked = 0
    for it in manifest:
        lanes = set(it["artifact_lanes"])
        commits_bytes = it.get("verbatim_path") is not None or lanes & {"fixture", "calibration"}
        if commits_bytes:
            assert it["redistribution"] in REDISTRIBUTABLE, (
                f"{it['item_id']}: commits verbatim bytes but redistribution "
                f"{it['redistribution']!r} not in {sorted(REDISTRIBUTABLE)}"
            )
            assert (it["attribution"] or "").strip(), f"{it['item_id']}: empty attribution"
            checked += 1
    assert checked >= 5, f"expected redistributed items to be checked, got {checked}"


# (b2) CONSISTENCY: a CC-BY-SA license carries share-alike obligations, so it must be recorded
# as redistribution 'share-alike', never merely 'permitted' (Step-11 diff-review H3 — enforce
# the license↔redistribution binding so a future mislabel can't erase the share-alike duty).
def test_cc_by_sa_items_are_marked_share_alike(manifest):
    for it in manifest:
        if "BY-SA" in it["license"].upper():
            assert it["redistribution"] == "share-alike", (
                f"{it['item_id']}: {it['license']} implies share-alike, "
                f"got redistribution {it['redistribution']!r}"
            )


# (c) HASH DRIFT: a committed verbatim file must match its recorded before-hash; a committed
#     fixture-lane item with a null hash FAILS.
def test_committed_verbatim_hash_matches_bytes(manifest):
    checked = 0
    for it in manifest:
        vp = it.get("verbatim_path")
        if vp is None:
            continue  # catalog-only item (no separate committed fixture file)
        path = os.path.join(REPO, vp)
        assert os.path.exists(path), f"{it['item_id']}: names missing verbatim file {vp}"
        before = it["content_hashes"]["before"]
        assert before is not None, f"{it['item_id']}: commits {vp} but has a null before-hash"
        with open(path, "rb") as fh:
            actual = sha256_hex(fh.read())
        assert actual == before, f"{it['item_id']}: hash drift for {vp}: {actual} != {before}"
        checked += 1
    assert checked >= 5, f"expected the 5 authored fixtures to be hash-checked, got {checked}"


def test_authored_fixtures_are_all_cataloged(manifest):
    families = {it["source_family"] for it in manifest}
    for name in (
        "authored-semicolon", "authored-false-range", "authored-voice-seam",
        "authored-laundering-question", "authored-negative-fabricated",
    ):
        assert name in families, f"authored fixture {name} missing from manifest"


def test_negative_anchor_is_labeled_fabricated(manifest):
    neg = next(it for it in manifest if it["item_id"] == "authored-negative-fabricated")
    assert neg["after_validity"] == "fabricated"
    assert "fixture" in neg["artifact_lanes"]
