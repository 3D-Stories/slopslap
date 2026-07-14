"""apply-from-decisions (#62, pivot P4): approved hunks only, verifier + backup engine unchanged.

The user's decision authorizes (keystone v2); the byte-exact verifier still hard-gates. decisions.json
is untrusted (schema-validated, finding-ids matched, source_sha256-bound). E2E golden: approved-safe
applies; approved-but-invariant-breaking blocks + leaves the file untouched; discarded untouched; a
replay against the now-drifted file is rejected (idempotence)."""

import json

from slopslap_apply.backup import BackupConfig
from slopslap_assemble.assemble import apply_from_decisions, audit_document
from slopslap_review.findings import build_findings
from slopslap_review.review import build_review_payload, decisions_from_actions


def _stub(original, revision, ledger_canonical):
    return {"verdict": "clean", "concerns": []}  # offline clean Layer-3 stub


def _bconf(tmp_path):
    return BackupConfig(root=str(tmp_path / "backups"))


def _stage(run, name):
    return next(s for s in run.stages if s.stage == name)


# a transition-cluster passage: a strip finding whose whole-unit delete is verifier-clean (no invariant).
_CLEAN_STRIP = ("Intro line here.\n\n"
                "However it works well. Furthermore it scales up. Moreover it helps a lot. "
                "However it stays fast. Furthermore it feels clean.\n")
# a cadence "X, not Y" passage: negative_parallelism whose delete would DROP the "not" negation invariant.
_INVARIANT = ("Intro line here.\n\n"
              + ". ".join(f"choose {w} thing, not other thing" for w in "abcdef") + ".\n")


def _setup(tmp_path, text, actions_for, genre="general"):
    p = tmp_path / "doc.md"
    p.write_text(text, encoding="utf-8")
    audit = audit_document(str(p), declared_genre=genre).data
    findings = build_findings(audit, p.read_bytes())
    payload = build_review_payload(audit, p.read_bytes(), findings)
    dj = tmp_path / "decisions.json"
    dj.write_text(json.dumps(decisions_from_actions(payload, actions_for(payload))), encoding="utf-8")
    return str(p), str(dj), payload, p


def _apply(tmp_path, path, dj):
    return apply_from_decisions(path, dj, declared_genre="general", semantic_fn=_stub, write=True,
                                apply_config=_bconf(tmp_path))


def test_approved_safe_hunk_applies_and_changes_file(tmp_path):
    path, dj, _, p = _setup(tmp_path, _CLEAN_STRIP,
        lambda pl: {f["id"]: {"action": "apply"} for f in pl["findings"] if f["category"] == "transition_clusters"})
    before = p.read_bytes()
    run = _apply(tmp_path, path, dj)
    assert run.status == "ok", run
    assert _stage(run, "apply").status == "ok"
    assert p.read_bytes() != before and b"However it works well" not in p.read_bytes()


def test_approved_invariant_breaking_blocks_and_leaves_file_untouched(tmp_path):
    path, dj, _, p = _setup(tmp_path, _INVARIANT,
        lambda pl: {f["id"]: {"action": "apply"} for f in pl["findings"] if f["category"] == "negative_parallelism"})
    before = p.read_bytes()
    run = _apply(tmp_path, path, dj)
    assert _stage(run, "verify").status == "blocked"   # verifier rejected the user-approved hunk
    assert _stage(run, "apply").status == "aborted"
    assert p.read_bytes() == before                     # never silently applied


def test_all_discard_is_noop_and_untouched(tmp_path):
    path, dj, _, p = _setup(tmp_path, _CLEAN_STRIP,
        lambda pl: {f["id"]: {"action": "discard", "reason": "keep_voice"} for f in pl["findings"]})
    before = p.read_bytes()
    run = _apply(tmp_path, path, dj)
    assert run.status == "ok" and _stage(run, "candidate").status == "ok"
    assert p.read_bytes() == before                     # discarded/undecided → untouched


def test_replay_against_drifted_file_is_rejected(tmp_path):
    path, dj, _, p = _setup(tmp_path, _CLEAN_STRIP,
        lambda pl: {f["id"]: {"action": "apply"} for f in pl["findings"] if f["category"] == "transition_clusters"})
    r1 = _apply(tmp_path, path, dj)
    assert r1.status == "ok"
    after = p.read_bytes()
    r2 = _apply(tmp_path, path, dj)                      # same decisions, but the file's sha changed
    cand = _stage(r2, "candidate")
    assert cand.status == "failed" and cand.code == "invalid_decisions"
    assert p.read_bytes() == after                      # no double-apply


def test_unknown_finding_id_rejected(tmp_path):
    path, _, payload, p = _setup(tmp_path, _CLEAN_STRIP, lambda pl: {})
    audit = audit_document(path, declared_genre="general").data
    bad = {"schema_version": 1, "doc": payload["doc"], "source_sha256": audit.source_sha256,
           "decisions": [{"finding_id": "bogus:0:0", "user_action": "apply"}]}
    bj = tmp_path / "bad.json"
    bj.write_text(json.dumps(bad), encoding="utf-8")
    before = p.read_bytes()
    run = apply_from_decisions(path, str(bj), declared_genre="general", semantic_fn=_stub, write=True,
                               apply_config=_bconf(tmp_path))
    assert _stage(run, "candidate").code == "invalid_decisions"
    assert p.read_bytes() == before
