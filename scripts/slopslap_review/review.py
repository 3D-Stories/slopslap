"""Interactive review stage (issue #61, de-slop pivot P3).

Turns a findings envelope (P1 `findings.build_findings`) into the user's per-finding review, whose
sole output is a `decisions.json` (the frozen #58 schema, bound to the audit's `source_sha256`) that
`apply` (#62/P4) consumes. Two delivery mechanisms, one schema:

- **A. Local review server** (`serve_review`) — stdlib `http.server` bound to 127.0.0.1 on a random
  port, gated by a per-run URL token, with an idle-timeout and shutdown-after-finish. It serves
  ONE self-contained page and accepts ONE `POST /finish?token=…`; every other path/method/bad-token
  is 404/403. No filesystem serving (no path-traversal surface), no new dependencies.
- **B. Static-export fallback** (`render_review_page` written to a file) — the same page; where a
  CSP blocks POST (a claude.ai artifact / offline), "Export decisions" hands back `decisions.json`
  for the user to feed to `apply --decisions`.

Keystone v2: this stage only CAPTURES the user's decision — it authorizes nothing itself, proposes
no rewrite the verifier didn't precheck, and every applied edit is still hard-gated downstream. The
page is XSS-safe by construction: the findings payload is embedded as an inert
`<script type="application/json">` blob and rendered into the DOM with `textContent` only — never
HTML-string concatenation.
"""

from __future__ import annotations

import html
import http.server
import json
import os
import secrets
import sys
import threading
from typing import Optional

# self-locate so `python3 scripts/slopslap_review/review.py` works as a script (its own dir, not the
# `scripts/` parent, is on sys.path[0] when run directly). Harmless/idempotent when imported.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_review.schema import validate_decisions  # noqa: E402

REVIEW_SCHEMA_VERSION = 1
DECISIONS_SCHEMA_VERSION = 1


def build_review_payload(audit, doc: bytes, findings) -> dict:
    """The `findings.json` payload: the audit binding + the serializable findings. `findings` is the
    `list[Finding]` from `build_findings(audit, doc)` (passed in so this module never re-audits)."""
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "doc": audit.source_path,
        "source_sha256": audit.source_sha256,
        "genre": audit.genre,
        "genre_confidence": audit.genre_confidence,
        "findings": [
            {
                "id": f.id, "category": f.category, "span": f.span, "evidence": f.evidence,
                # the SOURCE TEXT of the span (the whole containing unit an edit/strip acts on) so the
                # review UI can SHOW it and pre-fill the Edit box — an edit is a hand-tune of visible
                # text, never a blind overwrite of a span the user can't see.
                "span_text": doc[f.span["start"]:f.span["end"]].decode("utf-8", "replace"),
                "recommendation": f.recommendation, "rationale": f.rationale,
                "confidence": f.confidence, "proposed_rewrite": f.proposed_rewrite,
                "verifier_precheck": f.verifier_precheck,
            }
            for f in findings
        ],
    }


def decisions_from_actions(payload: dict, actions: dict) -> dict:
    """Build a `decisions.json` dict from `payload` + a `{finding_id: {"action":..., "replacement_b64"?:...,
    "reason"?:...}}` action map. Only findings present in the payload are emitted (an unknown id is
    dropped — the review UI cannot invent one). The result is bound to the audit `source_sha256`; the
    caller validates it with `validate_decisions(audit_finding_ids=…)` before writing/applying."""
    ids = {f["id"] for f in payload["findings"]}
    decisions = []
    for fid, act in actions.items():
        if fid not in ids:
            continue
        action = act.get("action")
        entry = {"finding_id": fid, "user_action": action}
        if action == "edit" and act.get("replacement_b64"):
            entry["replacement"] = act["replacement_b64"]
        if act.get("reason"):
            entry["reason"] = act["reason"]
        decisions.append(entry)
    return {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "doc": payload["doc"],
        "source_sha256": payload["source_sha256"],
        "decisions": decisions,
    }


# --------------------------------------------------------------------------- page rendering
_PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>slopslap review</title>
<style>
:root{{color-scheme:light dark}}
body{{font:15px/1.5 system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem}}
.f{{border:1px solid #8884;border-radius:8px;padding:.75rem 1rem;margin:.75rem 0}}
.f[data-state="apply"]{{border-color:#c0392b}}
.f[data-state="edit"]{{border-color:#d68910}}
.f[data-state="discard"]{{border-color:#2874a6}}
.cat{{font-weight:600}} .rec{{font-size:.8em;border:1px solid;border-radius:6px;padding:0 .35em;margin-left:.4em}}
.ev{{background:#8881;border-radius:4px;padding:.15em .35em;font-family:ui-monospace,monospace;font-size:.9em}}
.src{{font-size:.9em;margin:.35em 0}} .srctext{{background:#8881;border-radius:4px;padding:.1em .3em;white-space:pre-wrap}}
.blocked{{opacity:.7}} .blocked .apply,.blocked .edit{{display:none}}
.act button{{margin-right:.35em}} button{{cursor:pointer;border-radius:6px;border:1px solid #8886;padding:.2em .6em}}
.recbtn{{border-color:currentColor;font-weight:600;box-shadow:0 0 0 1px currentColor}}
.done{{margin:1.5rem 0;font-weight:600}}
</style></head><body>
<h1>slopslap review <small>{count} findings · genre {genre}</small></h1>
<p id="status">Choose an action per finding, then Finish.</p>
<div id="findings"></div>
<div class="done">
  <button id="finish">{finish_label}</button>
  <button id="export">Export decisions.json</button>
</div>
<script id="payload" type="application/json">{payload_json}</script>
<script>{script}</script>
</body></html>"""

# The page script: renders findings with textContent (no HTML injection), tracks per-finding
# actions, and Finish POSTs / Export downloads decisions.json. Kept in a Python string (doubled
# braces are for str.format); it embeds no user data — all user text flows through the JSON blob.
_PAGE_SCRIPT = r"""
const PAYLOAD = JSON.parse(document.getElementById('payload').textContent);
const POST_URL = %POST_URL%;
const actions = {};
function mk(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls; if(text!=null)e.textContent=text; return e; }
function b64utf8(s){ return btoa(unescape(encodeURIComponent(s))); }  // UTF-8-safe base64 for edits
const root = document.getElementById('findings');
PAYLOAD.findings.forEach(f => {
  const box = mk('div','f'); box.dataset.state='';
  const h = mk('div');
  h.appendChild(mk('span','cat', f.category));
  h.appendChild(mk('span','rec', 'rec: '+f.recommendation));
  const blocked = f.verifier_precheck && f.verifier_precheck.status === 'blocked';
  if(blocked){ box.classList.add('blocked'); h.appendChild(mk('span','rec','blocked')); }
  box.appendChild(h);
  if(f.evidence){ const ev=mk('div'); ev.appendChild(mk('span','ev', f.evidence)); box.appendChild(ev); }
  box.appendChild(mk('div', null, f.rationale));
  // show the SPAN's source text (what an apply/edit acts on) so the user is never editing blind.
  if(f.span_text){ const s=mk('div','src'); s.appendChild(mk('span',null,'this passage: ')); s.appendChild(mk('span','srctext', f.span_text)); box.appendChild(s); }
  if(blocked && f.verifier_precheck.reason){ box.appendChild(mk('div', null, 'Blocked: '+f.verifier_precheck.reason)); }
  const act = mk('div','act');
  function choose(action, extra){ actions[f.id]=Object.assign({action}, extra||{}); box.dataset.state=action; }
  // one labeled button per outcome; the one matching the recommendation carries the rec marker.
  function outcomeBtn(cls, label, action, extra){
    const rec = (f.recommendation==='strip' && action==='apply') || (f.recommendation==='keep' && action==='discard');
    const b = mk('button','btn '+cls, (rec?'★ ':'')+label);
    if(rec) b.classList.add('recbtn');
    b.onclick=()=>choose(action, extra);
    return b;
  }
  if(!blocked){
    act.appendChild(outcomeBtn('apply','Apply strip','apply'));
    const ed = mk('button','btn edit','Edit…');
    // pre-fill with the FULL span text (what gets replaced) so an edit is a hand-tune of visible text.
    ed.onclick=()=>{ const t=window.prompt('Edit this passage — your text replaces the whole shown span (to delete it, use Apply strip):', f.span_text||''); if(t!==null && t!==''){ choose('edit',{replacement_b64:b64utf8(t)}); } };
    act.appendChild(ed);
  }
  // agreeing with a keep recommendation is not a voice-override; only tag keep_voice when overriding a strip.
  act.appendChild(outcomeBtn('discard','Keep original','discard', f.recommendation==='keep' ? {} : {reason:'keep_voice'}));
  if(blocked){ const fb=mk('button','btn','Mark false positive'); fb.onclick=()=>choose('discard',{reason:'false_positive'}); act.appendChild(fb); }
  box.appendChild(act);
  root.appendChild(box);
});
function decisions(){
  const out=[];
  PAYLOAD.findings.forEach(f=>{ const a=actions[f.id]; if(a){ const d={finding_id:f.id, user_action:a.action}; if(a.action==='edit'&&a.replacement_b64)d.replacement=a.replacement_b64; if(a.reason)d.reason=a.reason; out.push(d); } });
  return {schema_version:1, doc:PAYLOAD.doc, source_sha256:PAYLOAD.source_sha256, decisions:out};
}
document.getElementById('export').onclick=()=>{
  const blob=new Blob([JSON.stringify(decisions(),null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='decisions.json'; a.click();
};
document.getElementById('finish').onclick=()=>{
  if(!POST_URL){ document.getElementById('status').textContent='No server — use Export decisions.json.'; return; }
  fetch(POST_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(decisions())})
    .then(r=>{ document.getElementById('status').textContent = r.ok ? 'Decisions saved. You can close this tab.' : 'Save failed (invalid decisions).'; })
    .catch(()=>{ document.getElementById('status').textContent='Save failed (server closed?).'; });
};
"""


def render_review_page(payload: dict, *, post_url: Optional[str] = None) -> str:
    """Render the self-contained review page. `post_url` set → the Finish button POSTs there (server
    mode); None → static-export mode (Finish is inert, Export downloads decisions.json). The payload
    is embedded as an inert JSON blob and rendered client-side with textContent only (XSS-safe)."""
    # Safe JSON-in-<script> embedding: escape <, >, & as JSON \uXXXX. `<script type="application/json">`
    # content is raw text the browser does NOT entity-decode, so html.escape would be WRONG — its
    # &lt;/&amp; would reach JSON.parse verbatim and corrupt any payload containing <, > or &. The \u
    # escapes both (a) parse back to the real chars via JSON.parse and (b) can never form `</script>`.
    payload_json = (json.dumps(payload)
                    .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    script = _PAGE_SCRIPT.replace("%POST_URL%", json.dumps(post_url) if post_url else "null")
    return _PAGE_TEMPLATE.format(
        count=len(payload["findings"]),
        genre=html.escape(str(payload.get("genre", ""))),
        finish_label="Finish review" if post_url else "Finish (static — use Export)",
        payload_json=payload_json,
        script=script,
    )


# --------------------------------------------------------------------------- local review server
_MAX_BODY = 1 << 20  # 1 MiB cap on the /finish POST body (a decisions.json is tiny; reject the rest)


class _ReviewHandler(http.server.BaseHTTPRequestHandler):
    """Serves EXACTLY one page (GET /) and one decision POST (POST /finish), both gated by the
    server's per-run token. No filesystem access — there is no path-traversal surface. Every
    other path/method, or a bad/missing token, is 403/404."""

    timeout = 30  # bound a slow/stalled socket read so one client can't hang the single-threaded server

    def _token_ok(self) -> bool:
        from urllib.parse import parse_qs, urlparse
        token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        # constant-time compare on BYTES — secrets.compare_digest raises TypeError on a non-ASCII str,
        # so an attacker-supplied non-ASCII token would otherwise escape the 403 path (encode both sides).
        return bool(self.server.review_token) and secrets.compare_digest(
            token.encode("utf-8"), self.server.review_token.encode("utf-8"))

    def _path(self) -> str:
        from urllib.parse import urlparse
        return urlparse(self.path).path

    def do_GET(self):  # noqa: N802
        if self._path() == "/favicon.ico":
            self.send_response(204)  # no-content: silence the browser's unauthenticated favicon probe
            self.end_headers()
            return
        if self._path() == "/" and self._token_ok():
            body = self.server.review_page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.server.touch()
        else:
            self.send_error(403 if not self._token_ok() else 404)

    def do_POST(self):  # noqa: N802
        if self._path() != "/finish" or not self._token_ok():
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (ValueError, TypeError):
            self.send_error(400)  # a malformed Content-Length must not escape as an uncaught traceback
            return
        if length < 0 or length > _MAX_BODY:
            self.send_error(413)  # negative (read-to-EOF) or oversized body — refuse, don't block/DoS
            return
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self.send_error(400)
            return
        accepted, problems = self.server.on_decisions(data)
        payload = json.dumps({"ok": accepted, "problems": problems}).encode("utf-8")
        self.send_response(200 if accepted else 422)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        if accepted:
            self.server.finished = True
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *_a):  # silence default stderr access logging
        return


class _ReviewServer(http.server.HTTPServer):
    """Loopback HTTP server carrying the per-run token, page, decision sink, and an idle-timeout."""

    def __init__(self, payload, out_path, idle_timeout):
        super().__init__(("127.0.0.1", 0), _ReviewHandler)  # loopback only; OS-assigned random port
        self.review_token = secrets.token_urlsafe(32)
        self.out_path = out_path
        self.finished = False
        self._idle_timeout = idle_timeout
        self._timer: Optional[threading.Timer] = None
        self._ids = {f["id"] for f in payload["findings"]}
        self._sha = payload["source_sha256"]
        post_url = f"http://127.0.0.1:{self.server_address[1]}/finish?token={self.review_token}"
        self.review_page = render_review_page(payload, post_url=post_url)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/?token={self.review_token}"

    def on_decisions(self, data):
        """Validate the posted decisions against THIS audit (finding-ids + source_sha256 bound) and,
        if clean, write decisions.json. Returns (accepted, problems)."""
        problems = validate_decisions(data, audit_finding_ids=self._ids, expected_source_sha256=self._sha)
        if problems:
            return False, problems
        with open(self.out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        if self._timer is not None:
            self._timer.cancel()  # decisions saved; cancel the pending auto-shutdown timer (no leak)
        return True, []

    def touch(self):
        """(Re)arm the auto-shutdown deadline. Armed when serving starts (see serve_forever) and
        re-armed on each page GET — a total safety cap so a served-but-abandoned server never lingers,
        NOT a per-keystroke idle timer (the page is client-side after load). If it lapses mid-review the
        Finish POST fails gracefully and the user falls back to Export. ``idle_timeout=0`` disables it."""
        if self._timer is not None:
            self._timer.cancel()
        if self._idle_timeout:
            self._timer = threading.Timer(self._idle_timeout, self.shutdown)
            self._timer.daemon = True
            self._timer.start()

    def serve_forever(self, poll_interval=0.5):
        self.touch()  # arm the deadline WHEN serving starts, so an opened-but-never-loaded server still shuts down
        super().serve_forever(poll_interval)


def serve_review(payload: dict, out_path: str, *, idle_timeout: float = 900.0) -> _ReviewServer:
    """Build (do NOT start) a loopback review server for `payload`. The caller prints `server.url`,
    opens it, then `server.serve_forever()` (which arms the auto-shutdown deadline); a valid
    `POST /finish` writes `decisions.json` to `out_path`, sets `finished`, and shuts the server down.
    `idle_timeout` is a total safety cap (default 900s), not a per-keystroke idle timer; 0 disables it.
    Returns the server so a test can drive it."""
    return _ReviewServer(payload, out_path, idle_timeout)


# --------------------------------------------------------------------------- CLI
def _load_overlay():
    """Build the keep-only learned overlay from the local feedback ledger (#63/P5). Best-effort: any
    failure → None (no overlay), so a missing/corrupt ledger never breaks the review."""
    try:
        from slopslap_corpus.learn import learn_from_feedback
        from slopslap_review.feedback import read_feedback
        return learn_from_feedback(list(read_feedback()))
    except Exception:  # noqa: BLE001 — learning is advisory; never block the review
        return None


def _build(target: str, fmt: str, genre, overlay=None):
    """Audit → findings → review payload for `target`. Imports the sibling engine packages lazily so
    the module stays importable (and unit-testable) without the whole engine on the path; the module
    load already put `scripts/` on sys.path. ``overlay`` (the learned keep-only overlay) tunes only the
    recommendation each finding shows — authorization stays the user's, the verifier stays the gate."""
    from slopslap_assemble.assemble import audit_document
    from slopslap_review.findings import build_findings
    stage = audit_document(target, fmt=fmt, declared_genre=genre)
    if stage.status != "ok":
        raise RuntimeError(f"audit failed: {stage.code} — {stage.message}")
    audit = stage.data
    with open(target, "rb") as fh:
        doc = fh.read()
    return build_review_payload(audit, doc, build_findings(audit, doc, overlay=overlay))


def main(argv=None) -> int:
    """`slopslap review <target>` — the interactive review stage. Serves a loopback, token-gated
    review page (writing `decisions.json` on Finish), or with `--static` writes the same page for a
    no-server browser / claude.ai artifact (Export decisions.json → `apply --decisions`)."""
    import argparse
    ap = argparse.ArgumentParser(prog="slopslap review", description="Interactive de-slop review stage.")
    ap.add_argument("target")
    ap.add_argument("--format", default="markdown", choices=["markdown", "text"])
    ap.add_argument("--genre", default=None)
    ap.add_argument("--static", metavar="OUT.html", default=None,
                    help="write the static review page (no server) instead of serving")
    ap.add_argument("--findings-out", default="findings.json", help="where to write the findings payload")
    ap.add_argument("--out", default="decisions.json", help="where the server writes decisions.json on Finish")
    ap.add_argument("--idle-timeout", type=float, default=900.0,
                    help="auto-shutdown deadline in seconds (total safety cap, not a per-keystroke idle timer; 0 disables)")
    ap.add_argument("--no-learn", action="store_true",
                    help="ignore the local feedback ledger — do NOT apply the learned recommendation overlay (#63/P5)")
    args = ap.parse_args(argv)
    try:
        payload = _build(args.target, args.format, args.genre,
                         overlay=None if args.no_learn else _load_overlay())
    except (RuntimeError, OSError) as err:
        print(f"error: {err}")
        return 1
    with open(args.findings_out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    if args.static is not None:
        with open(args.static, "w", encoding="utf-8") as fh:
            fh.write(render_review_page(payload, post_url=None))
        print(f"static review page → {args.static} ({len(payload['findings'])} findings). "
              f"Open it, Export decisions.json, then: slopslap apply --decisions decisions.json")
        return 0
    srv = serve_review(payload, args.out, idle_timeout=args.idle_timeout)
    # flush=True: the URL must appear immediately — serve_forever() blocks, so a buffered stdout
    # would never reach the user who needs to open the link.
    print(f"review → {srv.url}\n(loopback only, per-run token; {len(payload['findings'])} findings; "
          f"decisions → {args.out}; idle-timeout {args.idle_timeout:g}s)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0 if srv.finished else 2


__all__ = ["build_review_payload", "decisions_from_actions", "render_review_page", "serve_review",
           "main", "REVIEW_SCHEMA_VERSION"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
