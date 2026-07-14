"""apply-from-decisions (#62, pivot P4): approved hunks only, verifier + backup engine unchanged.

The user's decision authorizes (keystone v2); the byte-exact verifier still hard-gates. decisions.json
is untrusted (schema-validated, finding-ids matched, source_sha256-bound). E2E golden: approved-safe
applies; approved-but-invariant-breaking blocks + leaves the file untouched; discarded untouched; a
replay against the now-drifted file is rejected (idempotence)."""

import base64
import json

from slopslap_apply.backup import BackupConfig
from slopslap_assemble.assemble import apply_from_decisions, audit_document, exit_code, main
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


def test_cli_rejected_decisions_returns_exit_3_not_crash(tmp_path):
    # the untrusted-input rejection MUST surface as the documented exit 3 via main()/exit_code,
    # not a KeyError/traceback+exit-1 (invalid_decisions/conflicting_decisions in _EXIT_CLASS).
    path, _, payload, p = _setup(tmp_path, _CLEAN_STRIP, lambda pl: {})
    bad = {"schema_version": 1, "doc": payload["doc"], "source_sha256": "0" * 64,  # drifted sha
           "decisions": [{"finding_id": "bogus:0:0", "user_action": "apply"}]}
    bj = tmp_path / "bad.json"
    bj.write_text(json.dumps(bad), encoding="utf-8")
    rc = main(["apply", "--path", path, "--decisions", str(bj), "--declared-genre", "general"])
    assert rc == 3, f"rejected decisions.json must be exit 3 (invalid input), got {rc}"


def _edit_actions(category, replacement):
    b64 = base64.b64encode(replacement.encode("utf-8")).decode("ascii")
    return lambda pl: {f["id"]: {"action": "edit", "replacement_b64": b64}
                       for f in pl["findings"] if f["category"] == category}


def test_edit_with_clean_replacement_applies(tmp_path):
    path, dj, _, p = _setup(tmp_path, _CLEAN_STRIP, _edit_actions("transition_clusters", "It works."))
    run = _apply(tmp_path, path, dj)
    assert run.status == "ok" and _stage(run, "apply").status == "ok"
    assert b"It works." in p.read_bytes() and b"However it works well" not in p.read_bytes()


def test_edit_replacement_breaking_an_invariant_blocks(tmp_path):
    # editing the cadence span to text that DROPS the "not" negations → verifier REJECT, file untouched
    path, dj, _, p = _setup(tmp_path, _INVARIANT, _edit_actions("negative_parallelism", "We make choices here."))
    before = p.read_bytes()
    run = _apply(tmp_path, path, dj)
    assert _stage(run, "verify").status == "blocked"
    assert p.read_bytes() == before


def test_mixed_apply_and_discard(tmp_path):
    # one finding applied, the rest discarded, in a single decisions.json
    def actions(pl):
        out = {}
        for i, f in enumerate(pl["findings"]):
            out[f["id"]] = {"action": "apply"} if (f["category"] == "transition_clusters" and "apply" not in [v.get("action") for v in out.values()]) else {"action": "discard", "reason": "keep_voice"}
        return out
    path, dj, _, p = _setup(tmp_path, _CLEAN_STRIP, actions)
    run = _apply(tmp_path, path, dj)
    assert run.status == "ok"  # applied subset ok; discards skipped


def test_conflicting_same_span_decisions_rejected(tmp_path):
    # two DIFFERENT metrics on the same unit → same span; apply (delete) on one + edit (replace) on the
    # other → conflicting_decisions (never a silent overlap / last-writer-wins).
    doc = "Intro.\n\nWe choose robust, not weak. We choose scalable, not slow. We choose seamless, not clunky.\n"
    p = tmp_path / "doc.md"
    p.write_text(doc, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    payload = build_review_payload(audit, p.read_bytes(), build_findings(audit, p.read_bytes()))
    by_cat = {}
    for f in payload["findings"]:
        by_cat.setdefault(f["category"], f)
    # need two metrics sharing the exact same span
    same_span = {}
    for f in payload["findings"]:
        same_span.setdefault((f["span"]["start"], f["span"]["end"]), []).append(f)
    shared = next((fs for fs in same_span.values() if len(fs) >= 2), None)
    # fail loud (not skip): the conflict path must stay exercised even if the scanner's overlap shifts.
    assert shared, "fixture must produce two metrics on one shared span to exercise conflicting_decisions"
    actions = {shared[0]["id"]: {"action": "apply"},
               shared[1]["id"]: {"action": "edit", "replacement_b64": base64.b64encode(b"x").decode()}}
    dj = tmp_path / "decisions.json"
    dj.write_text(json.dumps(decisions_from_actions(payload, actions)), encoding="utf-8")
    run = apply_from_decisions(str(p), str(dj), declared_genre="general", semantic_fn=_stub, write=True,
                               apply_config=_bconf(tmp_path))
    assert _stage(run, "candidate").code == "conflicting_decisions"
    assert p.read_bytes() == doc.encode("utf-8")


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
