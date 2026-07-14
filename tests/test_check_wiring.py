"""#36 (Epic #67 Wave 1): the auto-ledger checks cross_refs + defined_terms must be wired through
ALL THREE check-name-keyed surfaces, and a drift-guard pins them together so they can never re-split.

Surfaces:
  - ledger._CHECK_KIND        (check -> ledger entry kind/preservation/confidence)
  - atoms.CHECK_EXTRACTORS    (check -> region-scoped preservation extractor, used by the runner gate)
  - loader.validate_manifest  (the accepted-check allowlist)
"""

from eval.loader import _ALLOWED_CHECKS
from slopslap_verification import atoms
from slopslap_verification.editscript import Edit
from slopslap_verification.gates import GateStatus, preservation_region_scoped
from slopslap_verification.ledger import _CHECK_KIND, build_ledger

_NEW = {"cross_refs", "defined_terms"}


def test_all_three_surfaces_agree_on_the_check_set():
    # THE drift-guard: the ledger's check->kind table and the runner's check->extractor map cover
    # EXACTLY the same checks; adding a check to one and not the other fails here.
    assert set(_CHECK_KIND) == set(atoms.CHECK_EXTRACTORS)
    assert _NEW <= set(atoms.CHECK_EXTRACTORS)   # the two auto-ledger checks are wired


def test_loader_whitelist_is_derived_not_hand_kept():
    # the loader's accepted-check set is EXACTLY the extractor map's keys (no hand-kept literal that
    # drifts): the two new checks are accepted, a bogus check is not.
    assert _ALLOWED_CHECKS == set(atoms.CHECK_EXTRACTORS)
    assert _NEW <= _ALLOWED_CHECKS
    assert "telepathy" not in _ALLOWED_CHECKS


def test_region_gate_catches_a_changed_cross_ref():
    # [4] -> [9] inside a cross_refs region: caught as a CHANGE, not as a missing-extractor error
    orig = b"Refer to [4] and https://example.com/a here.\n"
    rev = b"Refer to [9] and https://example.com/a here.\n"
    fixture = {"invariant_regions": [{"id": "r0", "start_byte": 0, "end_byte": len(orig),
                                      "checks": ["cross_refs"]}]}
    r = preservation_region_scoped(orig, rev, [Edit(10, 11, b"9")], fixture)
    assert r.status is GateStatus.FAIL
    assert "unknown check" not in (r.detail or "")   # non-vacuous: the extractor exists + fired
    assert "cross_refs" in (r.detail or "")


def test_region_gate_passes_an_unchanged_cross_ref():
    orig = b"Refer to [4] and https://example.com/a here.\n"
    fixture = {"invariant_regions": [{"id": "r0", "start_byte": 0, "end_byte": len(orig),
                                      "checks": ["cross_refs"]}]}
    r = preservation_region_scoped(orig, orig, [], fixture)   # no edit, identical
    assert r.status is GateStatus.PASS


def test_region_gate_catches_a_changed_defined_term():
    orig = b"Widget means a small gadget.\n"
    rev = b"Widget means a large gadget.\n"                    # "small" -> "large"
    fixture = {"invariant_regions": [{"id": "r0", "start_byte": 0, "end_byte": len(orig),
                                      "checks": ["defined_terms"]}]}
    r = preservation_region_scoped(orig, rev, [Edit(15, 20, b"large")], fixture)
    assert r.status is GateStatus.FAIL
    assert "unknown check" not in (r.detail or "")
    assert "defined_terms" in (r.detail or "")


def test_build_ledger_builds_entries_for_new_checks():
    orig = b"See [1]. Foo means bar.\n"
    manifest = {"invariant_regions": [{"start_byte": 0, "end_byte": len(orig),
                                       "checks": ["cross_refs", "defined_terms"]}], "protected_spans": []}
    led = build_ledger(orig, manifest)
    kinds = {e.kind for e in led.entries}
    assert "cross_reference" in kinds and "defined_term" in kinds
