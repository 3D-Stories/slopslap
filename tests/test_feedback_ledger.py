"""P5 (#63) feedback-ledger WRITER: append every review decision as a schema-valid, span-hashed,
local, purgeable JSONL line. The schema was frozen in #58 (schema.validate_feedback_line); this
tests the writer's storage properties (hashed spans, purge) that the schema deliberately left to P5.
"""

import json

from slopslap_assemble.assemble import audit_document
from slopslap_review.feedback import append_feedback, feedback_path, read_feedback, reset_feedback
from slopslap_review.findings import build_findings
from slopslap_review.review import build_review_payload, decisions_from_actions
from slopslap_review.schema import validate_feedback_line

_TEXT = ("Intro line here.\n\n"
         "However it works well. Furthermore it scales up. Moreover it helps a lot. "
         "However it stays fast. Furthermore it feels clean.\n")


def _findings(tmp_path, genre="general"):
    p = tmp_path / "doc.md"
    p.write_text(_TEXT, encoding="utf-8")
    audit = audit_document(str(p), declared_genre=genre).data
    findings = build_findings(audit, p.read_bytes())
    payload = build_review_payload(audit, p.read_bytes(), findings)
    return audit, findings, payload


def _ledger(tmp_path):
    return str(tmp_path / "feedback.jsonl")


def test_append_writes_one_schema_valid_line_per_decision(tmp_path):
    audit, findings, payload = _findings(tmp_path)
    actions = {f["id"]: {"action": "discard", "reason": "keep_voice"} for f in payload["findings"]}
    decisions = decisions_from_actions(payload, actions)
    path = _ledger(tmp_path)
    n = append_feedback(decisions, findings, audit.genre, path=path, now="2026-07-14T16:00:00Z")
    assert n == len(decisions["decisions"]) and n > 0
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    assert len(lines) == n
    for ln in lines:
        assert validate_feedback_line(ln) == [], ln
        assert ln["doc_sha"] == audit.source_sha256
        assert ln["user_action"] == "discard" and ln["reason"] == "keep_voice"


def test_span_is_hashed_not_raw_offsets(tmp_path):
    audit, findings, payload = _findings(tmp_path)
    # a finding id in the review layer is "metric:start:end" (raw offsets); the LEDGER must hash the span
    raw_ids = {f["id"] for f in payload["findings"]}
    actions = {f["id"]: {"action": "discard"} for f in payload["findings"]}
    path = _ledger(tmp_path)
    append_feedback(decisions_from_actions(payload, actions), findings, audit.genre, path=path,
                    now="2026-07-14T16:00:00Z")
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    for ln in lines:
        # ledger finding_id is "metric:<hex16>" — carries no reconstructable byte offsets
        assert ln["finding_id"] not in raw_ids
        metric, _, tail = ln["finding_id"].rpartition(":")
        assert metric == ln["metric"] and len(tail) == 16 and all(c in "0123456789abcdef" for c in tail)


def test_edit_keeps_b64_replacement(tmp_path):
    import base64
    audit, findings, payload = _findings(tmp_path)
    b64 = base64.b64encode(b"It works.").decode("ascii")
    strip = next(f for f in payload["findings"] if f["recommendation"] == "strip")
    actions = {strip["id"]: {"action": "edit", "replacement_b64": b64}}
    path = _ledger(tmp_path)
    append_feedback(decisions_from_actions(payload, actions), findings, audit.genre, path=path,
                    now="2026-07-14T16:00:00Z")
    ln = json.loads(open(path, encoding="utf-8").readline())
    assert ln["user_action"] == "edit" and ln["replacement"] == b64
    assert validate_feedback_line(ln) == []


def test_apply_with_log_feedback_writes_the_ledger(tmp_path):
    # end-to-end WIRED path (the Step-8a HIGH): apply_from_decisions(log_feedback=True) actually appends
    # the user's decisions to the ledger. Library-hermetic via feedback_ledger_path (no real HOME write).
    from slopslap_apply.backup import BackupConfig
    from slopslap_assemble.assemble import apply_from_decisions
    audit, findings, payload = _findings(tmp_path)
    strip = next(f for f in payload["findings"] if f["recommendation"] == "strip")
    actions = {strip["id"]: {"action": "discard", "reason": "false_positive"}}
    dj = tmp_path / "d.json"
    dj.write_text(json.dumps(decisions_from_actions(payload, actions)), encoding="utf-8")
    ledger = _ledger(tmp_path)
    apply_from_decisions(str(tmp_path / "doc.md"), str(dj), declared_genre="general",
                         semantic_fn=lambda o, r, l: {"verdict": "clean", "concerns": []}, write=True,
                         apply_config=BackupConfig(root=str(tmp_path / "b")),
                         log_feedback=True, feedback_ledger_path=ledger)
    lines = list(read_feedback(ledger))
    assert len(lines) == 1 and lines[0]["user_action"] == "discard" and lines[0]["reason"] == "false_positive"


def test_reset_purges_the_ledger(tmp_path):
    audit, findings, payload = _findings(tmp_path)
    actions = {f["id"]: {"action": "discard"} for f in payload["findings"]}
    path = _ledger(tmp_path)
    append_feedback(decisions_from_actions(payload, actions), findings, audit.genre, path=path,
                    now="2026-07-14T16:00:00Z")
    assert list(read_feedback(path)) != []
    reset_feedback(path)
    assert list(read_feedback(path)) == []      # gone / empty


def test_reader_skips_malformed_lines(tmp_path):
    path = _ledger(tmp_path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"ts":"2026-07-14T16:00:00Z","finding_id":"m:abc","category":"filler","metric":"m",'
                 '"genre":"general","recommendation":"strip","user_action":"discard",'
                 '"doc_sha":"' + "0" * 64 + '"}\n')
        fh.write("not json at all\n")
        fh.write('{"missing":"fields"}\n')
    good = list(read_feedback(path))
    assert len(good) == 1 and good[0]["metric"] == "m"


def test_feedback_path_uses_xdg_state(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    p = feedback_path()
    assert p.endswith("slopslap/feedback.jsonl") and str(tmp_path / "state") in p


def test_cli_path_show_reset(tmp_path, monkeypatch, capsys):
    import json as _json

    from slopslap_review.feedback import main
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    audit, findings, payload = _findings(tmp_path)
    actions = {f["id"]: {"action": "discard"} for f in payload["findings"]}
    append_feedback(decisions_from_actions(payload, actions), findings, audit.genre,
                    now="2026-07-14T16:00:00Z")  # writes to the XDG path

    assert main(["path"]) == 0
    assert feedback_path() in capsys.readouterr().out
    assert main(["show"]) == 0
    shown = _json.loads(capsys.readouterr().out)
    assert shown["lines"] > 0 and "learned_keep_classes" in shown
    assert main(["reset"]) == 0
    capsys.readouterr()
    assert list(read_feedback()) == []      # purged
