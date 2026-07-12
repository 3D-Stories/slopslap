"""Envelope construction helpers for the eval tests."""

import base64
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "tests", "fixtures", "eval")

from slopslap_verification.editscript import apply_edits, parse_edits, sha256_hex


def fixture_dir(name):
    return os.path.join(FIXTURES, name)


def _raw_edits(edits):
    return [
        {"start_byte": s, "end_byte": e, "replacement_b64": base64.b64encode(r).decode()}
        for s, e, r in edits
    ]


def make_envelope(original: bytes, edits, baseline="slopslap"):
    """edits = [(start_byte, end_byte, replacement_bytes)]. Returns (envelope, revision)."""
    raw = _raw_edits(edits)
    revision = apply_edits(original, parse_edits(raw))
    return (
        {
            "baseline": baseline,
            "pass_index": 1,
            "edits": raw,
            "revision_sha256": sha256_hex(revision),
        },
        revision,
    )


def make_second_pass(first_pass: bytes, edits):
    return {"pass_index": 2, "base_hash": sha256_hex(first_pass), "edits": _raw_edits(edits)}
