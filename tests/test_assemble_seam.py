"""End-to-end live-orchestration seam tests (#27).

The seam (``scripts/slopslap_assemble/assemble.py``) chains audit -> candidate -> verify ->
apply for an ARBITRARY document, with an explicit stage-boundary data contract
(``AuditResult``), a uniform stage-result envelope (``StageResult``/``RunResult``), and a
dry-run acceptance golden. These tests are hermetic and offline: the semantic layer is an
injected clean stub, never a real model call (``SLOPSLAP_LIVE`` is never set).

Design: docs/planning/2026-07-12-27-live-orchestration-seam.md (§4 contracts, §10 cases).
"""

import os

from slopslap_assemble.assemble import (
    AuditResult,
    audit_document,
    build_manifest,
)
from slopslap_verification.ledger import build_ledger, validate_ledger, verify
from slopslap_verification.editscript import Edit

# a doc flagged by rule_of_three (two tricolons) with NO invariant regions / protected spans
FLAGGED_DOC = (
    b"The platform is fast, reliable, and scalable.\n\n"
    b"Our approach is simple, elegant, and powerful.\n"
)
# a genuinely clean doc: no metric location, no soft_flag
CLEAN_DOC = b"The cat sat on the mat. It was a warm day outside.\n"
# a doc exercising the #36-adjacent checks: defined_terms + cross_refs (+ number/modal)
XREF_DOC = (
    b'The term "widget" means a small tool. See https://example.com for the spec. '
    b"It must respond within 200 ms.\n"
)


def _write(tmp_path, name, data: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# ---- case 1: build_manifest on an arbitrary doc, incl. cross_refs/defined_terms (not #36-gapped) ----
def test_build_manifest_regions_have_non_empty_checks_and_build_ledger_accepts():
    manifest = build_manifest(XREF_DOC)
    assert manifest["invariant_regions"], "expected at least one invariant region"
    for region in manifest["invariant_regions"]:
        assert region["checks"], "autoledger must never emit an empty-checks region"
    assert manifest["protected_spans"], "expected the URL protected span"
    # the manifest carries the #36-adjacent checks and build_ledger accepts them (not gapped)
    all_checks = {c for r in manifest["invariant_regions"] for c in r["checks"]}
    assert "defined_terms" in all_checks and "cross_refs" in all_checks
    ledger = build_ledger(XREF_DOC, manifest)  # must NOT raise LedgerBuildError
    assert validate_ledger(XREF_DOC, ledger) == []


# ---- case 2: audit_document returns a well-formed AuditResult ----
def test_audit_document_flagged(tmp_path):
    path = _write(tmp_path, "flagged.md", FLAGGED_DOC)
    # declare "general": the ONLY genre that suppresses nothing (a content-only doc with just a
    # cadence tell classifies as the preservation-heavy "spec" fallback, which suppresses tricolons
    # by design — so general is the lever that exercises a flagged->authorized path).
    result = audit_document(path, declared_genre="general")
    assert result.stage == "audit" and result.status == "ok" and result.code == "ok"
    audit = result.data
    assert isinstance(audit, AuditResult)
    assert audit.genre == "general" and audit.genre_confidence == "high"
    assert audit.audit_status == "flagged"  # the tricolons emit metric locations
    # flagged tricolons are localizable -> authorized ranges derived
    assert audit.authorization["state"] == "authorized"
    assert audit.authorization["ranges"]  # non-empty
    assert validate_ledger(FLAGGED_DOC, audit.ledger) == []
    assert audit.source_path == os.path.realpath(path)
    assert audit.source_sha256 and audit.byte_length == len(FLAGGED_DOC)
    assert audit.run_id  # deterministic id present


def test_audit_document_clean_is_reject_all(tmp_path):
    path = _write(tmp_path, "clean.md", CLEAN_DOC)
    audit = audit_document(path).data
    assert audit.audit_status == "clean"
    # a clean doc has no localizable passage -> reject_all ([] editable set), NOT locality_unverified
    assert audit.authorization["state"] == "reject_all"
    assert audit.authorization["ranges"] == []


def test_audit_run_id_is_deterministic(tmp_path):
    p1 = _write(tmp_path, "a.md", FLAGGED_DOC)
    p2 = _write(tmp_path, "b.md", FLAGGED_DOC)  # identical bytes, different path
    a1 = audit_document(p1).data
    a2 = audit_document(p2).data
    assert a1.run_id == a2.run_id  # keyed on content, not path/clock/uuid


# ---- case 10: empty doc / no invariants -> empty-but-valid ledger, verify handles it ----
def test_empty_doc_yields_empty_but_valid_ledger(tmp_path):
    path = _write(tmp_path, "empty.md", b"")
    result = audit_document(path)
    assert result.status == "ok"
    audit = result.data
    assert audit.ledger.entries == []
    assert audit.ledger.protected_spans == []
    assert validate_ledger(b"", audit.ledger) == []
    # verify tolerates the empty-but-valid ledger (no LedgerBuildError, no crash)
    res = verify(b"", [], audit.ledger, authorized_ranges=[], semantic_fn=lambda o, r, l: {"verdict": "clean", "concerns": []})
    assert res["decision"] in ("ACCEPT", "REJECT", "ASK", "SURFACE")


def test_no_invariant_doc_builds_valid_ledger(tmp_path):
    path = _write(tmp_path, "flagged.md", FLAGGED_DOC)
    audit = audit_document(path).data
    # the tricolon doc has no numbers/modals/etc -> no invariant entries, still a valid ledger
    assert audit.ledger.entries == []
    assert validate_ledger(FLAGGED_DOC, audit.ledger) == []
