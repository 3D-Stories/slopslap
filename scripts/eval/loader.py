"""Load and validate eval fixtures.

A fixture directory holds immutable ``original.md`` bytes and a ``fixture.json`` manifest
whose coordinates are ORIGINAL-byte offsets. Manifest validation is fail-closed: an invalid
manifest is a FIXTURE_ERROR, never a silently-skipped fixture.
"""

from __future__ import annotations

import json
import os
from typing import List, Tuple

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from slopslap_verification.editscript import sha256_hex  # noqa: E402

SCHEMA_VERSION = 1

VALID_GENRES = {"personal", "spec", "prd", "marketing", "technical", "general"}
INVARIANT_KINDS = {
    "literal",
    "number_or_quantity",
    "normative_statement",
    "condition",
    "exception",
    "causal_claim",
    "attribution",
    "defined_term",
    "cross_reference",
    "unsupported_intent",
    "missing_support",
    "intentional_repetition",
    "protected_span",
}
PRESERVATION_KINDS = {
    "byte_exact",
    "lexically_exact",
    "semantic_exact",
    "relationship_exact",
    "surface_only",
}


class FixtureError(ValueError):
    """Invalid fixture manifest (schema/bounds/overlap/hash)."""


def load_fixture(fixture_dir: str) -> Tuple[bytes, dict]:
    with open(os.path.join(fixture_dir, "original.md"), "rb") as fh:
        original = fh.read()
    with open(os.path.join(fixture_dir, "fixture.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    return original, manifest


def _overlaps(a, b) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def validate_manifest(original: bytes, manifest: dict) -> List[str]:
    """Return a list of problems (empty = valid)."""
    problems: List[str] = []
    n = len(original)

    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"schema_version {manifest.get('schema_version')} != {SCHEMA_VERSION}"
        )
    genre = manifest.get("genre")
    if genre not in VALID_GENRES:
        problems.append(f"genre '{genre}' not in {sorted(VALID_GENRES)}")

    editable = [(r["start_byte"], r["end_byte"]) for r in manifest.get("editable_ranges", [])]
    protected = [
        (r["start_byte"], r["end_byte"]) for r in manifest.get("protected_spans", [])
    ]

    for label, ranges in (("editable_ranges", editable), ("protected_spans", protected)):
        for s, e in ranges:
            if not (0 <= s <= e <= n):
                problems.append(f"{label} [{s},{e}) out of bounds (len {n})")

    # non-overlap within editable_ranges
    se = sorted(editable)
    for a, b in zip(se, se[1:]):
        if _overlaps(a, b):
            problems.append(f"editable_ranges overlap: {a} & {b}")

    # editable / protected disjoint
    for er in editable:
        for pr in protected:
            if _overlaps(er, pr):
                problems.append(f"editable range {er} overlaps protected span {pr}")

    # protected span hashes match the immutable original bytes
    for sp in manifest.get("protected_spans", []):
        s, e = sp["start_byte"], sp["end_byte"]
        if 0 <= s <= e <= n:
            got = sha256_hex(original[s:e])
            if sp.get("sha256") != got:
                problems.append(
                    f"protected_span [{s},{e}) sha256 {str(sp.get('sha256'))[:10]} "
                    f"!= actual {got[:10]}"
                )

    # invariant regions in bounds; checks known
    for region in manifest.get("invariant_regions", []):
        s, e = region.get("start_byte"), region.get("end_byte")
        if not (isinstance(s, int) and isinstance(e, int) and 0 <= s <= e <= n):
            problems.append(f"invariant_region {region.get('id','?')} out of bounds")
        for check in region.get("checks", []):
            if check not in {"numbers", "units", "modality", "negation", "conditions"}:
                problems.append(
                    f"invariant_region {region.get('id','?')} unknown check '{check}'"
                )

    for inv in manifest.get("expected_invariants", []):
        if inv.get("kind") not in INVARIANT_KINDS:
            problems.append(f"expected_invariant kind '{inv.get('kind')}' invalid")
        if inv.get("preservation") not in PRESERVATION_KINDS:
            problems.append(
                f"expected_invariant preservation '{inv.get('preservation')}' invalid"
            )

    # control invariants
    if manifest.get("control"):
        if editable:
            problems.append("control fixture must have empty editable_ranges")

    return problems
