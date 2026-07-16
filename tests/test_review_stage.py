"""Interactive review stage (#61, pivot P3): payload, decisions capture, page, loopback server."""

import http.client
import json
import socket
import threading

import pytest

from slopslap_assemble.assemble import audit_document
from slopslap_review.findings import build_findings
from slopslap_review.review import (
    build_review_payload,
    decisions_from_actions,
    render_review_page,
    serve_review,
)
from slopslap_review.schema import validate_decisions

_DOC = ("Clean intro paragraph here.\n\n"
        + ". ".join(f"choose {w} thing, not other thing" for w in "abcdef") + ".\n"
        + "\nOur robust, scalable, best-in-class platform will empower teams.\n")


def _payload(tmp_path, genre="general"):
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = audit_document(str(p), declared_genre=genre).data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    return build_review_payload(audit, doc, findings), audit, {f.id for f in findings}


def test_payload_shape_and_binding(tmp_path):
    payload, audit, ids = _payload(tmp_path)
    assert payload["source_sha256"] == audit.source_sha256
    assert payload["findings"], "a flagged doc yields findings"
    for f in payload["findings"]:
        assert {"id", "category", "span", "span_text", "recommendation", "verifier_precheck"} <= set(f)
        # span_text is the actual source bytes of the span (so the review UI can show/pre-fill it)
        assert isinstance(f["span_text"], str)


def test_decisions_from_actions_is_schema_valid(tmp_path):
    payload, audit, ids = _payload(tmp_path)
    fid = payload["findings"][0]["id"]
    dec = decisions_from_actions(payload, {fid: {"action": "discard", "reason": "keep_voice"}})
    problems = validate_decisions(dec, audit_finding_ids=ids, expected_source_sha256=audit.source_sha256)
    assert problems == [], problems
    assert dec["source_sha256"] == audit.source_sha256


def test_decisions_drops_unknown_finding_id(tmp_path):
    payload, audit, ids = _payload(tmp_path)
    dec = decisions_from_actions(payload, {"bogus:0:0": {"action": "apply"}})
    assert dec["decisions"] == []  # an id not in the payload is never emitted


def test_page_embeds_payload_inertly_and_avoids_innerhtml(tmp_path):
    payload, _, _ = _payload(tmp_path)
    page = render_review_page(payload, post_url="http://127.0.0.1:9/finish?token=x")
    assert 'type="application/json"' in page          # payload is an inert JSON blob
    assert ".innerHTML" not in page                    # rendered via textContent only (XSS-safe)
    assert "textContent" in page
    # static mode: no post_url -> Finish is inert (POST_URL null)
    static = render_review_page(payload, post_url=None)
    assert "null" in static and "Export" in static


def test_page_json_blob_is_script_safe_and_roundtrips(tmp_path):
    # a finding whose evidence contains "</script>" must not break out of the inert blob, AND payloads
    # with <, >, & must round-trip: <script type=application/json> content is NOT entity-decoded, so
    # html.escape would corrupt JSON.parse — the \uXXXX embedding decodes back to the real chars.
    payload, _, _ = _payload(tmp_path)
    payload["findings"][0]["evidence"] = "danger </script><script>alert(1)</script> a<b & c>d"
    page = render_review_page(payload, post_url="http://127.0.0.1:9/finish?token=x")
    assert "</script><script>alert(1)" not in page          # no breakout
    assert "&lt;" not in page and "&amp;" not in page        # NOT html-escaped (would corrupt JSON.parse)
    import re
    m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', page, re.S)
    assert m, "payload blob present"
    assert json.loads(m.group(1)) == payload                # \uXXXX decodes back to the real chars


def _serve(tmp_path):
    payload, audit, ids = _payload(tmp_path)
    out = tmp_path / "decisions.json"
    srv = serve_review(payload, str(out), idle_timeout=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, payload, out


def test_server_binds_loopback_only(tmp_path):
    srv, _, _ = _serve(tmp_path)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.shutdown()


def test_server_rejects_bad_token(tmp_path):
    srv, _, _ = _serve(tmp_path)
    try:
        host, port = srv.server_address
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("GET", "/?token=wrong")
        assert c.getresponse().status == 403
        # a random other path is also refused
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("GET", "/../../etc/passwd?token=" + srv.review_token)
        assert c.getresponse().status == 404
    finally:
        srv.shutdown()


def test_server_serves_page_and_writes_decisions_on_finish(tmp_path):
    srv, payload, out = _serve(tmp_path)
    try:
        host, port = srv.server_address
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("GET", "/?token=" + srv.review_token)
        r = c.getresponse()
        assert r.status == 200 and b"slopslap review" in r.read()
        fid = payload["findings"][0]["id"]
        dec = decisions_from_actions(payload, {fid: {"action": "discard", "reason": "false_positive"}})
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("POST", "/finish?token=" + srv.review_token, json.dumps(dec),
                  {"Content-Type": "application/json"})
        assert c.getresponse().status == 200
    finally:
        srv.shutdown()
    assert out.exists() and srv.finished
    written = json.loads(out.read_text())
    assert written["source_sha256"] == payload["source_sha256"]


def _raw(host, port, request_bytes):
    s = socket.create_connection((host, port), timeout=5)
    try:
        s.sendall(request_bytes)
        return s.recv(4096)
    finally:
        s.close()


def test_server_non_ascii_token_is_clean_403(tmp_path):
    # a non-ASCII token must yield a clean 403, NOT an uncaught secrets.compare_digest TypeError
    # (which would reset the connection with no HTTP response).
    srv, _, _ = _serve(tmp_path)
    try:
        host, port = srv.server_address
        resp = _raw(host, port, b"GET /?token=%E6%97%A5%E6%9C%AC HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        assert resp.split(b"\r\n")[0].split()[1] == b"403", resp[:80]
    finally:
        srv.shutdown()


def test_server_malformed_content_length_is_400(tmp_path):
    srv, _, _ = _serve(tmp_path)
    try:
        host, port = srv.server_address
        req = (f"POST /finish?token={srv.review_token} HTTP/1.1\r\nHost: x\r\n"
               "Content-Length: notanint\r\nConnection: close\r\n\r\n").encode()
        resp = _raw(host, port, req)
        assert resp.split(b"\r\n")[0].split()[1] == b"400", resp[:80]
    finally:
        srv.shutdown()


def test_server_oversized_body_is_413(tmp_path):
    # the server rejects on the Content-Length HEADER (>1 MiB) before reading the body — the DoS
    # protection. Declare 2 MiB, send no body, and confirm a clean 413 (never a blocking read).
    srv, _, _ = _serve(tmp_path)
    try:
        host, port = srv.server_address
        req = (f"POST /finish?token={srv.review_token} HTTP/1.1\r\nHost: x\r\n"
               f"Content-Length: {1 << 21}\r\nConnection: close\r\n\r\n").encode()
        resp = _raw(host, port, req)
        assert resp.split(b"\r\n")[0].split()[1] == b"413", resp[:80]
    finally:
        srv.shutdown()


def test_page_shows_span_text_so_edits_are_not_blind(tmp_path):
    payload, _, _ = _payload(tmp_path)
    page = render_review_page(payload, post_url="http://127.0.0.1:9/finish?token=x")
    assert "span_text" in page                    # span source rendered in the passage block
    assert "ta.value = f.span_text" in page       # edit textarea pre-filled with the visible span text
    # Bug1 fix: an empty edit replacement never emits — Finish/Export refuse and report instead
    assert "t===''" in page or "t === ''" in page
    # Bug2 fix: blocked findings hide only apply/edit — the false-positive feedback button stays visible
    assert ".f.blocked .btn.apply" in page and "mark false positive" in page


def test_cli_main_static_writes_page_and_findings(tmp_path):
    from slopslap_review.review import main
    doc = tmp_path / "in.md"
    doc.write_text(_DOC, encoding="utf-8")
    page = tmp_path / "review.html"
    fj = tmp_path / "findings.json"
    rc = main([str(doc), "--genre", "general", "--static", str(page), "--findings-out", str(fj)])
    assert rc == 0
    assert page.exists() and "slopslap review" in page.read_text()
    assert json.loads(fj.read_text())["source_sha256"]


def test_cli_main_missing_target_returns_1(tmp_path):
    from slopslap_review.review import main
    rc = main([str(tmp_path / "nope.md"), "--static", str(tmp_path / "o.html")])
    assert rc == 1


def test_server_rejects_finish_with_wrong_sha(tmp_path):
    srv, payload, out = _serve(tmp_path)
    try:
        host, port = srv.server_address
        bad = decisions_from_actions(payload, {payload["findings"][0]["id"]: {"action": "discard", "reason": "other"}})
        bad["source_sha256"] = "0" * 64  # replay against a drifted audit
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("POST", "/finish?token=" + srv.review_token, json.dumps(bad),
                  {"Content-Type": "application/json"})
        assert c.getresponse().status == 422  # validation rejected -> not written
    finally:
        srv.shutdown()
    assert not out.exists()


def test_payload_emits_alternatives_only_when_present(tmp_path):
    # #81 T2: absent alternatives -> payload byte-identical to today; present -> emitted verbatim.
    import json as _json
    from dataclasses import replace
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    base = build_review_payload(audit, doc, findings)
    for f in base["findings"]:
        assert "alternatives" not in f, "absent alternatives must not appear in the payload"
    alts = [{"id": "subjectivize", "text": "we stand behind it", "claim_status": "none"}]
    enriched = [replace(findings[0], alternatives=alts)] + list(findings[1:])
    p2 = build_review_payload(audit, doc, enriched)
    emitted = p2["findings"][0]["alternatives"]
    # emitted with id/text intact; claim_status is SERVER-DERIVED (#84) so it may differ
    assert [a["id"] for a in emitted] == ["subjectivize"]
    assert emitted[0]["text"] == "we stand behind it"
    for f in p2["findings"][1:]:
        assert "alternatives" not in f
    _json.dumps(p2)  # payload stays JSON-serializable


def test_payload_rejects_malformed_alternatives(tmp_path):
    # Adversarial F1 (#81): the payload boundary enforces the shape guard itself.
    from dataclasses import replace
    import pytest
    from slopslap_review.findings import FindingsError
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    bad = [replace(findings[0], alternatives=[{"id": "x", "text": "y", "claim_status": "amazing"}])]
    with pytest.raises(FindingsError, match="claim_status"):
        build_review_payload(audit, doc, bad + list(findings[1:]))


def test_actions_empty_alternative_fails_closed(tmp_path):
    # Adversarial F3 (#81): a present-but-empty alternative must reach the validator and be
    # rejected there — never silently dropped by a truthiness check.
    import base64
    from slopslap_review.review import decisions_from_actions
    from slopslap_review.schema import validate_decisions
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    payload = build_review_payload(audit, doc, findings)
    fid = payload["findings"][0]["id"]
    b64 = base64.b64encode(b"x").decode("ascii")
    dec = decisions_from_actions(payload, {fid: {"action": "edit", "replacement_b64": b64, "alternative": ""}})
    assert dec["decisions"][0].get("alternative") == "", "empty value must be carried, not dropped"
    assert any("alternative" in p2 for p2 in validate_decisions(dec))


def _payload_with_alternatives(tmp_path):
    from dataclasses import replace
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    alts = [
        {"id": "subjectivize", "text": "we stand behind it", "claim_status": "none",
         "label": "no external claim"},
        {"id": "lateral", "text": "industry-leading results", "claim_status": "banned",
         "label": "BLOCKED - lateral swap"},
    ]
    enriched = [replace(findings[0], alternatives=alts)] + list(findings[1:])
    return build_review_payload(audit, doc, enriched)


def test_page_renders_alternatives_machinery(tmp_path):
    # #83: the page script carries the alts rendering + selection flow.
    payload = _payload_with_alternatives(tmp_path)
    page = render_review_page(payload, post_url="http://127.0.0.1:9/finish?token=x")
    assert "f.alternatives" in page                    # rendering keyed on the payload field
    assert "claim_status" in page                      # chip per status
    assert "banned" in page and "disabled" in page     # banned alternatives never selectable
    assert ".alts" in page and ".altlbl" in page       # mockup block styles present
    assert "alternative:" in page or "alternative =" in page or "alternative}" in page or "a.id" in page


def test_page_decodes_proposed_rewrite_dict(tmp_path):
    # #83 (defect from #81 run): proposed_rewrite is {start,end,replacement_b64}; the page
    # must decode the b64 (empty = delete) instead of type-testing for a string.
    payload = _payload_with_alternatives(tmp_path)
    page = render_review_page(payload, post_url="http://127.0.0.1:9/finish?token=x")
    assert "replacement_b64" in page                   # reads the real field
    assert "typeof f.proposed_rewrite === 'string'" not in page


def test_page_alternatives_state_machine_guards(tmp_path):
    # #83 review findings: F1 sel-tracking, F2 delete-shaped pick -> apply, F3 no alts on blocked.
    payload = _payload_with_alternatives(tmp_path)
    page = render_review_page(payload, post_url=None)
    assert "!blocked && Array.isArray(f.alternatives)" in page          # F3
    assert "a.text === ''" in page and "action:'apply', picked:" in page  # F2
    assert "a.alternative || a.picked" in page                           # F1


def test_finish_handler_rejects_forged_alternative_id(tmp_path):
    # #83 adv F1: end-to-end — the REAL finish handler rejects an alternative id the finding
    # never offered (binding enforced via #81's alternative_ids map), and accepts an offered one.
    import base64
    from dataclasses import replace
    from slopslap_review.review import serve_review
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    alts = [{"id": "subjectivize", "text": "we stand behind it", "claim_status": "none"}]
    enriched = [replace(findings[0], alternatives=alts)] + list(findings[1:])
    payload = build_review_payload(audit, doc, enriched)
    out = tmp_path / "decisions.json"
    srv = serve_review(payload, str(out), idle_timeout=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        host, port = srv.server_address
        fid = payload["findings"][0]["id"]
        b64 = base64.b64encode(b"we stand behind it").decode("ascii")

        def post(dec):
            c = http.client.HTTPConnection(host, port, timeout=5)
            c.request("POST", "/finish?token=" + srv.review_token, json.dumps(dec),
                      {"Content-Type": "application/json"})
            return c.getresponse().status

        forged = decisions_from_actions(
            payload, {fid: {"action": "edit", "replacement_b64": b64, "alternative": "fabricated"}})
        assert post(forged) != 200, "forged alternative id must be rejected"
        assert not out.exists()
        ok = decisions_from_actions(
            payload, {fid: {"action": "edit", "replacement_b64": b64, "alternative": "subjectivize"}})
        assert post(ok) == 200
        assert out.exists()
    finally:
        srv.shutdown()


def test_precheck_replacement_banned_and_pass(tmp_path):
    # #84 (AC4 from #82): the authoring lane's precheck — a claim-adding replacement comes back
    # blocked with the lexeme named; a claim-free one passes deterministically.
    from slopslap_review.findings import precheck_replacement
    from slopslap_assemble.assemble import audit_document as _ad
    p = tmp_path / "d.md"
    p.write_text(_DOC, encoding="utf-8")
    audit = _ad(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    f = findings[0]
    s, e = f.span["start"], f.span["end"]
    led = audit.ledger  # same ledger build_findings prechecks with
    # introduce a buzzword ABSENT from the whole doc ("world-class"; the doc already carries
    # "best-in-class", whose reuse is allowed by design)
    banned = precheck_replacement(doc, s, e, doc[s:e] + b" A world-class rewrite.", led)
    assert banned["status"] == "blocked"
    assert "no_new_claim_atoms" in banned["reason"]
    # an invariant-free span (the intro paragraph carries no ledger entries) with a
    # claim-free rewrite clears Layers 1+2
    intro_end = doc.index(b"\n\n")
    ok = precheck_replacement(doc, 0, intro_end, b"A tidy intro paragraph here.", led)
    assert ok["status"] == "deterministic_pass", ok["reason"]


def test_alternatives_authoring_contract_doc_anchor():
    # #84 drift guard — anchored to ONE canonical sentence (workspace lesson: never corpus-regex).
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    skill = (root / "skills" / "slopslap" / "SKILL.md").read_text(encoding="utf-8")
    assert "<!-- anchor:alternatives-authoring -->" in skill
    assert "Author alternatives only for `simulation`-class findings" in skill
    assert "precheck_replacement" in skill
    review_cmd = (root / "commands" / "review.md").read_text(encoding="utf-8")
    assert "anchor:alternatives-authoring" in review_cmd


def test_payload_derives_claim_status_server_side(tmp_path):
    # #84 adv F1/F2: the payload builder runs the precheck itself and OVERRIDES a model-authored
    # claim_status with `banned` on ANY blocked verdict — an unprechecked claim-adding
    # alternative can never be served as selectable.
    from dataclasses import replace
    p = tmp_path / "d.md"
    # a buzzword-pile span with NO ledger invariants (no negation/modal/number/condition),
    # so the precheck outcome is decided purely by the no-new-claims dimension
    p.write_text("Intro sentence here.\n\nOur robust, scalable, best-in-class platform "
                 "empowers teams across projects.\n", encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    findings = build_findings(audit, doc)
    alts = [
        # claim-adding (buzzword absent from the whole doc) but AUTHORED as 'none' — must flip to banned
        {"id": "sneaky", "text": "A world-class platform.", "claim_status": "none"},
        # claim-free (composed from lexemes the doc already carries) — authored status survives
        {"id": "honest", "text": "Our robust platform helps teams.", "claim_status": "scoped"},
    ]
    enriched = [replace(findings[0], alternatives=alts)] + list(findings[1:])
    payload = build_review_payload(audit, doc, enriched)
    out = {a["id"]: a for a in payload["findings"][0]["alternatives"]}
    assert out["sneaky"]["claim_status"] == "banned", out["sneaky"]
    assert "no_new_claim_atoms" in out["sneaky"].get("label", ""), out["sneaky"]
    assert out["honest"]["claim_status"] == "scoped"


def test_editbox_autoresizes_instead_of_scrolling(tmp_path):
    # UAT feedback 2026-07-15: the edit textarea grows with its content — no inner scrollbar.
    payload, _, _ = _payload(tmp_path)
    page = render_review_page(payload, post_url=None)
    assert "field-sizing:content" in page.replace(" ", "")   # native auto-size where supported
    assert "autosize" in page and "scrollHeight" in page     # JS fallback + programmatic seeding
    assert "overflow:hidden" in page.replace(" ", "")        # no scrollbar on the grown box


def test_distribution_finding_has_no_delete_candidate(tmp_path):
    # #92: a uniform-cadence run (numberless) must NOT yield a green whole-span delete candidate.
    # After the fix: recommendation 'keep', proposed_rewrite None (no auto-delete footgun).
    p = tmp_path / "cadence.md"
    p.write_text("Intro line here.\n\n"
                 "The system stays fast under load.\n\n"
                 "The system stays simple to reason about.\n\n"
                 "The system stays pleasant to maintain.\n", encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    doc = p.read_bytes()
    runs = [f for f in build_findings(audit, doc) if f.category == "paragraph_sentence_count_runs"]
    assert runs, "the uniform run should still be DETECTED"
    for f in runs:
        assert f.recommendation == "keep", f
        assert f.proposed_rewrite is None, f.proposed_rewrite   # no whole-span delete candidate


def test_category_chips_carry_explanatory_tooltips(tmp_path):
    # UAT feedback: each category chip gets a hover tooltip explaining the metric.
    payload, _, _ = _payload(tmp_path)
    page = render_review_page(payload, post_url="http://127.0.0.1:9/finish?token=x")
    assert "CATEGORY_HELP" in page
    # the four the owner named, plus the map is keyed by metric name
    for metric in ("rule_of_three", "paragraph_sentence_count_runs",
                   "repeated_openers", "transition_clusters"):
        assert metric in page, metric
    # tooltip is set as the native title attribute on the .cat chip, with a hover affordance
    assert ".title =" in page and "CATEGORY_HELP[" in page
    assert "cursor:help" in page
