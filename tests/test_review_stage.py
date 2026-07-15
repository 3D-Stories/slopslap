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
