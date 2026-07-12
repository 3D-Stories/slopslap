"""Authored thin-tell fixtures + the negative preservation anchor (#30 Task 3).

Each fixture is ORIGINAL prose (no license risk) matching the eval loader schema. The candidate
edit-script is built INLINE as ``editscript.Edit`` objects (as in test_invoke_verify_roundtrip),
and ``verify()`` is driven directly with ``authorized_ranges = fixture['editable_ranges']`` so
edit-locality is confirmed rather than downgraded to ASK.

Positive fixtures: a faithful, in-range, seam-local / laundering edit must NOT hard-REJECT
(``verify`` returns SURFACE without a Layer-3 semantic pass — design R1). The negative anchor:
a fabricated number the source never contained MUST drive ``verify`` to REJECT via the
Layer-1 ``no_new_claim_atoms`` gate, proving it can never become a golden.

Idempotence is exercised separately through the two-pass runner (``verify`` itself carries no
idempotence gate): a no-op second pass makes the gate FIRE (PASS) instead of NOT_EVALUATED.
"""

import os

import pytest

import helpers
from eval import runner
from eval.loader import load_fixture, validate_manifest
from slopslap_verification.editscript import Edit
from slopslap_verification.ledger import build_ledger, verify

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(REPO, "tests", "fixtures", "eval")


def _load(name):
    fixture_dir = os.path.join(FIX, name)
    original, manifest = load_fixture(fixture_dir)
    problems = validate_manifest(original, manifest)
    assert problems == [], f"{name} manifest invalid: {problems}"
    return fixture_dir, original, manifest


def _verify(name, edits):
    _, original, manifest = _load(name)
    ledger = build_ledger(original, manifest)
    return verify(original, edits, ledger, authorized_ranges=manifest["editable_ranges"])


# ---- positive fixtures: faithful in-range edit must not hard-REJECT ----

# name -> [(start_byte, end_byte, replacement_bytes)] candidate edit, in ORIGINAL coordinates.
POSITIVE_EDITS = {
    # remove the stylistic semicolon (";  the" -> ".  The"); the structural list is protected.
    "authored-semicolon": [(52, 57, b". The")],
    # drop the unbounded "from X to Y" rhetoric; the genuine 4-24h range is protected.
    "authored-false-range": [(21, 130, b"covers what a new lead needs, start to finish")],
    # harmonize the promotional seam back to the incident-report register; facts are protected.
    "authored-voice-seam": [
        (127, 234, b"The team scheduled a postmortem and will publish the findings to the incident log.")
    ],
    # convert the laundered adjective into a question (do NOT delete); genuine req is protected.
    "authored-laundering-question": [(48, 81, b" (intuitive by what measure, and verified how?)")],
}


@pytest.mark.parametrize("name", sorted(POSITIVE_EDITS))
def test_positive_fixture_not_hard_rejected(name):
    edits = [Edit(s, e, r) for s, e, r in POSITIVE_EDITS[name]]
    result = _verify(name, edits)
    assert result["decision"] in ("ACCEPT", "SURFACE"), (name, result["findings"])


@pytest.mark.parametrize("name", sorted(POSITIVE_EDITS))
def test_positive_fixture_idempotence_gate_is_evaluated(name):
    # NOTE (Step-11 review): the second pass is a NO-OP (empty edits), so this asserts only
    # that the idempotence gate is EVALUATED (status `pass` vs NOT_EVALUATED) — it does NOT
    # prove the deslop edit is idempotent under a real re-application. Genuine idempotence
    # needs a live deslop pass (out of scope for this additive corpus PR; exercised by the
    # eval-run loop). Named accordingly so no maintainer over-credits it as real coverage.
    fixture_dir = os.path.join(FIX, name)
    original, _ = load_fixture(fixture_dir)
    envelope, first_pass = helpers.make_envelope(original, POSITIVE_EDITS[name])
    second = helpers.make_second_pass(first_pass, [])  # no-op second pass: gate FIRES, not real idempotence
    result = runner.run(fixture_dir, envelope, second_pass=second)
    idem = next(g for g in result.gates if g["name"] == "idempotence")
    assert idem["status"] == "pass", (name, result.gates)


# ---- negative anchor: a fabricated number must REJECT ----

def test_negative_fabricated_number_is_rejected():
    # "every account" -> "all 4,200 accounts": 4200 appears NOWHERE in original.md.
    result = _verify("authored-negative-fabricated", [Edit(32, 45, b"all 4,200 accounts")])
    assert result["decision"] == "REJECT", result["findings"]
    codes = {f["code"] for f in result["findings"]}
    assert "no_new_claim_atoms" in codes, result["findings"]


def test_negative_source_has_no_number_token():
    # guards the anchor's premise: the fabricated token must be genuinely absent (self-review H7)
    _, original, _ = _load("authored-negative-fabricated")
    assert b"4200" not in original.replace(b",", b"") and b"4,200" not in original
