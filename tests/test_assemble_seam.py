"""End-to-end live-orchestration seam tests (#27).

The seam (``scripts/slopslap_assemble/assemble.py``) chains audit -> candidate -> verify ->
apply for an ARBITRARY document, with an explicit stage-boundary data contract
(``AuditResult``), a uniform stage-result envelope (``StageResult``/``RunResult``), and a
dry-run acceptance golden. These tests are hermetic and offline: the semantic layer is an
injected clean stub, never a real model call (``SLOPSLAP_LIVE`` is never set).

Design: docs/planning/2026-07-12-27-live-orchestration-seam.md (§4 contracts, §10 cases).
"""

import dataclasses
import os

from slopslap_assemble.assemble import (
    AuditResult,
    RunResult,
    assemble,
    audit_document,
    build_manifest,
    exit_code,
    live_semantic_fn,
    run_candidate,
)
from slopslap_apply.backup import BackupConfig
from slopslap_verification.ledger import build_ledger, validate_ledger, verify
from slopslap_verification.editscript import Edit, apply_edits, sha256_hex

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


# =====================================================================================
# Task 3 — candidate/verify/apply stages, run_candidate/assemble, exit contract
# =====================================================================================

# a heading + two tricolons: heading is NOT flagged (an out-of-range target), tricolons ARE
GOLDEN_DOC = (
    b"# Overview\n\n"
    b"The platform is fast, reliable, and scalable.\n\n"
    b"Our approach is simple, elegant, and powerful.\n"
)
# a tricolon-flagged sentence that ALSO carries a number invariant (weakening it -> REJECT)
NUM_DOC = b"The platform is fast, reliable, and scalable, serving 100 users daily.\n"


def CLEAN_STUB(original, revision, ledger_canonical):
    """Offline clean Layer-3 stub with NO status_sink attribute -> sink reads 'ok'."""
    return {"verdict": "clean", "concerns": []}


def _bconf(tmp_path):
    return BackupConfig(root=str(tmp_path / "backups"))


def _stage(run, name):
    return [s for s in run.stages if s.stage == name][0]


# ---- case 3: end-to-end dry-run ACCEPT golden (F1: backup reality) ----
def test_e2e_dry_run_accept_golden(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    bconf = _bconf(tmp_path)
    edit = Edit(28, 32, b"quick")  # "fast" -> "quick", inside authorized range [12,58]
    run = assemble(src, [edit], declared_genre="general", semantic_fn=CLEAN_STUB,
                   write=False, apply_config=bconf)
    assert isinstance(run, RunResult)
    assert [s.stage for s in run.stages] == ["audit", "candidate", "verify", "apply"]
    assert all(s.status == "ok" for s in run.stages), [(s.stage, s.status, s.code) for s in run.stages]
    assert run.status == "ok" and exit_code(run) == 0
    # verify shippable
    assert run.verification["decision"] == "ACCEPT" and run.verification["proposal_status"] == "ACCEPT"
    assert run.verification["semantic_status"] == "clean"
    # apply report: dry-run applied (mutated False), expected final_digest
    report = run.apply
    assert report["status"] == "applied" and report["mutated"] is False
    expected = sha256_hex(apply_edits(GOLDEN_DOC, [edit]))
    assert report["final_digest"] == expected
    # THE safety assertion: the SOURCE file on disk is byte-identical
    with open(src, "rb") as fh:
        assert fh.read() == GOLDEN_DOC
    # AND a verified backup EXISTS in the test-owned tmp dir (apply creates it before write=False)
    bdir = str(tmp_path / "backups")
    assert os.path.isdir(bdir) and any(f.endswith(".bak") for f in os.listdir(bdir))


# ---- case 4: end-to-end dry-run REJECT golden x2 (out-of-range + invariant weakening) ----
def test_e2e_dry_run_reject_out_of_range(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    bconf = _bconf(tmp_path)
    edit = Edit(2, 10, b"Summary!")  # edits the heading — OUTSIDE every authorized range
    run = assemble(src, [edit], declared_genre="general", semantic_fn=CLEAN_STUB,
                   write=False, apply_config=bconf)
    verify_stage = _stage(run, "verify")
    assert verify_stage.status == "blocked" and verify_stage.code == "verify_not_shippable"
    assert verify_stage.data["decision"] == "REJECT"  # full verify_result preserved
    assert exit_code(run) == 2
    apply_stage = _stage(run, "apply")
    assert apply_stage.status == "aborted" and apply_stage.code == "upstream_not_ok"
    assert apply_stage.data is None  # an aborted stage has NO apply report
    # source byte-identical, and NO backup created (verify blocks before apply is invoked)
    with open(src, "rb") as fh:
        assert fh.read() == GOLDEN_DOC
    assert not os.path.exists(str(tmp_path / "backups"))


def test_e2e_dry_run_reject_invariant_weakening(tmp_path):
    src = _write(tmp_path, "num.md", NUM_DOC)
    bconf = _bconf(tmp_path)
    i = NUM_DOC.index(b"100")
    edit = Edit(i, i + 3, b"999")  # in an authorized range, but weakens the number invariant
    run = assemble(src, [edit], declared_genre="general", semantic_fn=CLEAN_STUB,
                   write=False, apply_config=bconf)
    verify_stage = _stage(run, "verify")
    assert verify_stage.status == "blocked" and verify_stage.code == "verify_not_shippable"
    assert verify_stage.data["decision"] == "REJECT"
    assert any(f["code"] == "entry_weakened" for f in verify_stage.data["findings"])
    assert exit_code(run) == 2
    assert _stage(run, "apply").status == "aborted"
    with open(src, "rb") as fh:
        assert fh.read() == NUM_DOC
    assert not os.path.exists(str(tmp_path / "backups"))


# ---- case 5: stage propagation + exit codes ----
def test_non_utf8_doc_audit_failed_downstream_aborted(tmp_path):
    src = _write(tmp_path, "bad.md", b"\xff\xfe not utf-8 bytes")
    run = assemble(src, [Edit(0, 1, b"x")], semantic_fn=CLEAN_STUB, write=False)
    assert _stage(run, "audit").status == "failed"
    assert _stage(run, "audit").code == "genre_error"  # genre owns bad-bytes
    for name in ("candidate", "verify", "apply"):
        st = _stage(run, name)
        assert st.status == "aborted" and st.code == "upstream_not_ok"
    assert run.status == "failed" and exit_code(run) == 3


def test_malformed_edit_script_candidate_failed_before_verify(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    # out-of-bounds edit: end_byte far past the document length
    bad = Edit(0, len(GOLDEN_DOC) + 500, b"x")
    run = run_candidate(audit_document(src, declared_genre="general").data, [bad],
                        semantic_fn=CLEAN_STUB, write=False)
    cand = _stage(run, "candidate")
    assert cand.status == "failed" and cand.code == "invalid_edits"
    # verify NEVER sees a malformed edit-script — it is aborted, not run
    assert _stage(run, "verify").status == "aborted"
    assert exit_code(run) == 3


def test_overlapping_edits_candidate_failed(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    overlap = [Edit(12, 30, b"a"), Edit(20, 40, b"b")]  # overlapping spans
    run = run_candidate(audit_document(src, declared_genre="general").data, overlap,
                        semantic_fn=CLEAN_STUB, write=False)
    assert _stage(run, "candidate").code == "invalid_edits"
    assert exit_code(run) == 3


# ---- case 6: locality_unverified (ranges None) -> ASK -> blocked ----
def test_locality_unverified_blocks(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    audit = audit_document(src, declared_genre="general").data
    audit = dataclasses.replace(audit, authorization={"state": "locality_unverified", "ranges": None})
    run = run_candidate(audit, [Edit(28, 32, b"quick")], semantic_fn=CLEAN_STUB, write=False,
                        apply_config=_bconf(tmp_path))
    verify_stage = _stage(run, "verify")
    assert verify_stage.status == "blocked" and verify_stage.code == "verify_not_shippable"
    assert verify_stage.data["decision"] == "ASK"
    assert any(f["code"] == "locality_unverified" for f in verify_stage.data["findings"])
    assert exit_code(run) == 2


# ---- case 7: reject_all (clean doc, ranges []) + nonempty candidate -> blocked ----
def test_reject_all_blocks_every_edit(tmp_path):
    src = _write(tmp_path, "clean.md", CLEAN_DOC)
    audit = audit_document(src).data
    assert audit.authorization["state"] == "reject_all"
    run = run_candidate(audit, [Edit(4, 7, b"dog")], semantic_fn=CLEAN_STUB, write=False,
                        apply_config=_bconf(tmp_path))
    verify_stage = _stage(run, "verify")
    assert verify_stage.status == "blocked" and verify_stage.data["decision"] == "REJECT"
    assert exit_code(run) == 2


# ---- case 8: empty-candidate policy keyed on audit_status (adv A1) ----
def test_empty_candidate_clean_is_ok_noop(tmp_path):
    src = _write(tmp_path, "clean.md", CLEAN_DOC)
    audit = audit_document(src).data
    assert audit.audit_status == "clean"
    run = run_candidate(audit, [], semantic_fn=CLEAN_STUB, write=False)
    assert run.status == "ok" and exit_code(run) == 0
    assert _stage(run, "candidate").status == "ok"
    assert run.apply is None  # nothing applied; no backup, no mutation


def test_empty_candidate_flagged_blocks_even_when_reject_all(tmp_path):
    src = _write(tmp_path, "clean.md", CLEAN_DOC)
    audit = audit_document(src).data
    assert audit.authorization["state"] == "reject_all"
    # force the A1 edge: flagged audit_status while authorization stays reject_all (doc-level-only)
    audit = dataclasses.replace(audit, audit_status="flagged")
    run = run_candidate(audit, [], semantic_fn=CLEAN_STUB, write=False)
    cand = _stage(run, "candidate")
    assert cand.status == "blocked" and cand.code == "candidate_empty"
    assert exit_code(run) == 2
    assert _stage(run, "verify").status == "aborted"


# ---- case 9: digest / path-mismatch guards (peer + adv A6) ----
def test_digest_mismatch_aborts_before_apply(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    audit = audit_document(src, declared_genre="general").data
    with open(src, "wb") as fh:  # modify the file AFTER the audit snapshot
        fh.write(GOLDEN_DOC + b"drift\n")
    run = run_candidate(audit, [Edit(28, 32, b"quick")], semantic_fn=CLEAN_STUB, write=False,
                        apply_config=_bconf(tmp_path))
    cand = _stage(run, "candidate")
    assert cand.status == "failed" and cand.code == "digest_mismatch"
    assert _stage(run, "verify").status == "aborted" and _stage(run, "apply").status == "aborted"
    assert exit_code(run) == 3
    assert not os.path.exists(str(tmp_path / "backups"))  # apply never invoked


def test_path_mismatch_same_bytes_different_file(tmp_path):
    a = tmp_path / "a.md"
    a.write_bytes(GOLDEN_DOC)
    b = tmp_path / "b.md"
    b.write_bytes(GOLDEN_DOC)  # identical bytes, different file
    audit = audit_document(str(a), declared_genre="general").data
    a.unlink()
    os.symlink(str(b), str(a))  # audit.source_path now resolves to b, not the audited file
    run = run_candidate(audit, [Edit(28, 32, b"quick")], semantic_fn=CLEAN_STUB, write=False,
                        apply_config=_bconf(tmp_path))
    cand = _stage(run, "candidate")
    assert cand.status == "failed" and cand.code == "path_mismatch"
    assert exit_code(run) == 3


# ---- case 11: semantic INVOCATION failure -> failed (exit 4), distinct from policy blocked ----
def test_semantic_invocation_failure_is_failed_not_blocked(tmp_path):
    src = _write(tmp_path, "doc.md", GOLDEN_DOC)
    audit = audit_document(src, declared_genre="general").data

    def failing_sem(original, revision, ledger_canonical):
        return {"verdict": "ambiguous", "concerns": []}
    failing_sem.status_sink = {"invocation_status": "timeout"}  # simulate a transport failure

    edit = Edit(28, 32, b"quick")  # otherwise-shippable edit
    run = run_candidate(audit, [edit], semantic_fn=failing_sem, write=False,
                        apply_config=_bconf(tmp_path))
    verify_stage = _stage(run, "verify")
    assert verify_stage.status == "failed" and verify_stage.code == "semantic_invocation_failed"
    assert exit_code(run) == 4  # ops failure, NOT the exit-2 policy block of case 6
    assert _stage(run, "apply").status == "aborted"


# ---- live_semantic_fn factory: offline default is the clean stub, no model call ----
def test_live_semantic_fn_offline_is_clean_stub():
    fn = live_semantic_fn()  # SLOPSLAP_LIVE unset -> offline clean stub
    assert fn(b"orig", b"rev", {}) == {"verdict": "clean", "concerns": []}
    assert hasattr(fn, "status_sink")  # exposes the sink the seam reads
    assert fn.status_sink.get("invocation_status", "ok") == "ok"
