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
                # #81: emitted ONLY when present so alternative-less payloads stay byte-identical
                **({"alternatives": f.alternatives} if f.alternatives is not None else {}),
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
/* Design language: docs/planning/2026-07-13-deslop-pivot-design.html §02 (the ratified mockup). */
:root{{color-scheme:light dark;
  --paper:#F6F1E7; --card:#FCF9F2; --card2:#FFFDF8; --ink:#1E1B16; --soft:#5C554A; --faint:#8A8377;
  --hair:#E0D6C2; --hair2:#CDBFA6; --grid:rgba(51,85,110,.06);
  --red:#C0362C; --red-soft:rgba(192,54,44,.08); --blue:#33556E; --blue-soft:rgba(51,85,110,.09);
  --green:#3E7A52; --green-soft:rgba(62,122,82,.12); --amber:#9A6B12; --amber-soft:rgba(154,107,18,.13);
  --disp:Georgia,'Iowan Old Style Text','Times New Roman',serif;
  --sans:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,'SF Mono','IBM Plex Mono',Menlo,Consolas,monospace;
  --shadow:0 1px 0 rgba(30,27,22,.04),0 10px 30px -14px rgba(51,85,110,.30);
}}
@media (prefers-color-scheme:dark){{:root{{
  --paper:#15130F; --card:#1E1A15; --card2:#241F18; --ink:#EEE7D8; --soft:#A79E8C; --faint:#6E665A;
  --hair:#332C22; --hair2:#463C2E; --grid:rgba(143,178,203,.06);
  --red:#E27567; --red-soft:rgba(226,117,103,.13); --blue:#8FB2CB; --blue-soft:rgba(143,178,203,.12);
  --green:#77B58C; --green-soft:rgba(119,181,140,.14); --amber:#D6A24E; --amber-soft:rgba(214,162,78,.15);
  --shadow:0 1px 0 rgba(0,0,0,.3),0 14px 34px -14px rgba(0,0,0,.7);
}}}}
:root[data-theme="light"]{{
  --paper:#F6F1E7; --card:#FCF9F2; --card2:#FFFDF8; --ink:#1E1B16; --soft:#5C554A; --faint:#8A8377;
  --hair:#E0D6C2; --hair2:#CDBFA6; --grid:rgba(51,85,110,.06);
  --red:#C0362C; --red-soft:rgba(192,54,44,.08); --blue:#33556E; --blue-soft:rgba(51,85,110,.09);
  --green:#3E7A52; --green-soft:rgba(62,122,82,.12); --amber:#9A6B12; --amber-soft:rgba(154,107,18,.13);
  --shadow:0 1px 0 rgba(30,27,22,.04),0 10px 30px -14px rgba(51,85,110,.30);
}}
:root[data-theme="dark"]{{
  --paper:#15130F; --card:#1E1A15; --card2:#241F18; --ink:#EEE7D8; --soft:#A79E8C; --faint:#6E665A;
  --hair:#332C22; --hair2:#463C2E; --grid:rgba(143,178,203,.06);
  --red:#E27567; --red-soft:rgba(226,117,103,.13); --blue:#8FB2CB; --blue-soft:rgba(143,178,203,.12);
  --green:#77B58C; --green-soft:rgba(119,181,140,.14); --amber:#D6A24E; --amber-soft:rgba(214,162,78,.15);
  --shadow:0 1px 0 rgba(0,0,0,.3),0 14px 34px -14px rgba(0,0,0,.7);
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.6;
  -webkit-font-smoothing:antialiased;
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:26px 26px}}
.wrap{{max-width:880px;margin:0 auto;padding:26px 24px 60px}}
code{{font-family:var(--mono);font-size:.84em;background:var(--blue-soft);color:var(--blue);padding:1px 5px;border-radius:2px;word-break:break-word}}
.toggle{{position:fixed;top:14px;right:14px;z-index:20;font-family:var(--mono);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;background:var(--card);color:var(--soft);border:1px solid var(--hair2);border-radius:2px;padding:7px 11px;cursor:pointer}}
.toggle:hover{{color:var(--ink);border-color:var(--red)}} .toggle:focus-visible{{outline:2px solid var(--red);outline-offset:2px}}
.kicker{{font-family:var(--mono);font-size:11.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--red);
  display:flex;gap:14px;align-items:center;padding:10px 0;flex-wrap:wrap;border-bottom:2px solid var(--ink);margin-bottom:18px}}
.kicker .dot{{width:5px;height:5px;background:var(--red);border-radius:50%;display:inline-block}}
.kicker .muted{{color:var(--faint)}}
h1{{font-family:var(--disp);font-weight:700;letter-spacing:-.02em;line-height:1;font-size:clamp(30px,6vw,44px);margin:0 0 6px}}
h1 .slap{{color:var(--red);font-style:italic}}
#status{{color:var(--soft);font-size:14.5px;margin:6px 0 20px}}
.demo{{background:var(--card2);border:1px solid var(--hair2);border-left:3px solid var(--red);border-radius:3px;
  box-shadow:var(--shadow);overflow:hidden}}
.demo .bar{{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 16px;
  border-bottom:1px solid var(--hair);font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}}
.demo .bar b{{color:var(--red)}}
.f{{padding:16px 18px;border-bottom:1px dashed var(--hair2)}}
.f:last-of-type{{border-bottom:none}}
.f .top{{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}
.f .cat{{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--red);
  background:var(--red-soft);border:1px solid var(--red);border-radius:2px;padding:2px 7px}}
.f .gen{{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue);
  background:var(--blue-soft);border:1px solid var(--blue);border-radius:2px;padding:2px 7px}}
.f .rec{{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;border-radius:2px;padding:2px 7px}}
.f .rec.strip{{color:var(--red);border:1px solid var(--red);background:var(--red-soft)}}
.f .rec.keep{{color:var(--green);border:1px solid var(--green);background:var(--green-soft)}}
.f .rec.blockedchip{{color:var(--amber);border:1px solid var(--amber);background:var(--amber-soft)}}
.f .ms{{font-family:var(--disp);font-size:16.5px;line-height:1.8;margin:0 0 6px;white-space:pre-wrap}}
.f .ms .strike{{text-decoration:line-through;text-decoration-color:var(--red);text-decoration-thickness:2px;color:var(--faint)}}
.f .ms .to{{color:var(--green)}}
.f .why{{font-size:13px;color:var(--soft);margin:0 0 12px}}
.f .why .ev{{font-family:var(--mono);font-size:.92em;background:var(--blue-soft);color:var(--blue);border-radius:2px;padding:1px 5px}}
.btns{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.btn{{font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;padding:7px 14px;
  border-radius:2px;cursor:pointer;border:1.5px solid var(--hair2);background:var(--card);color:var(--soft)}}
.btn:focus-visible{{outline:2px solid var(--red);outline-offset:2px}}
.btn.apply:hover{{border-color:var(--red);color:var(--red)}}
.btn.edit:hover{{border-color:var(--amber);color:var(--amber)}}
.btn.discard:hover{{border-color:var(--blue);color:var(--blue)}}
.btn.recd{{border-color:var(--green);color:var(--green)}}
.btn.recd::after{{content:"· rec";margin-left:6px;font-size:9.5px;letter-spacing:.1em;opacity:.8}}
.btn.recd:hover{{background:var(--green);border-color:var(--green);color:var(--paper)}}
.f[data-state="apply"]{{background:var(--red-soft)}}
.f[data-state="apply"] .btn.apply{{background:var(--red);border-color:var(--red);color:var(--paper)}}
.f[data-state="edit"]{{background:var(--amber-soft)}}
.f[data-state="edit"] .btn.edit{{background:var(--amber);border-color:var(--amber);color:var(--paper)}}
.f[data-state="discard"]{{background:var(--blue-soft)}}
.f[data-state="discard"] .btn.discard{{background:var(--blue);border-color:var(--blue);color:var(--paper)}}
.f .state{{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-left:auto}}
.editbox{{display:none;margin:0 0 12px}}
.editbox.show{{display:block}}
.editbox textarea{{width:100%;min-height:46px;font-family:var(--disp);font-size:15px;color:var(--ink);
  background:var(--card);border:1px solid var(--amber);border-radius:2px;padding:8px 10px;line-height:1.6}}
.editbox textarea:focus-visible{{outline:2px solid var(--amber);outline-offset:1px}}
.editbox .hint{{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-top:5px}}
.f.blocked .btn.apply,.f.blocked .btn.edit{{display:none}}
.f.blocked .ms{{opacity:.85}}
.demo .foot{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:13px 16px;
  border-top:1px solid var(--hair);background:var(--card)}}
.tally{{font-family:var(--mono);font-size:12px;color:var(--soft)}}
.btn.finish{{border-color:var(--red);color:var(--red)}}
.btn.finish:hover{{background:var(--red);color:var(--paper)}}
.btn.export{{border-color:var(--green);color:var(--green)}}
.btn.export:hover{{background:var(--green);color:var(--paper)}}
footer{{padding:22px 0 0;color:var(--faint);font-family:var(--mono);font-size:12px}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important;animation:none!important}}}}
</style></head><body>
<button class="toggle" id="tg" aria-label="Toggle light or dark theme">◐ theme</button>
<div class="wrap">
<div class="kicker"><span class="dot"></span> slopslap · review <span class="muted">you hold the pen</span></div>
<h1>Review. <span class="slap">You</span> decide.</h1>
<p id="status">Apply, edit, or keep each finding — your click is the only authorization. Then Finish.</p>
<div class="demo">
  <div class="bar"><span>Review · <b>{doc_label}</b> · {count} findings · genre {genre}</span><span id="prog">0 / {count} decided</span></div>
  <div id="findings"></div>
  <div class="foot">
    <span class="tally" id="tally"></span>
    <div class="btns">
      <button class="btn finish" id="finish">{finish_label}</button>
      <button class="btn export" id="export">⇩ export decisions.json</button>
    </div>
  </div>
</div>
<footer>loopback only · per-run token · decisions bind to source_sha256 · the verifier still gates every applied edit</footer>
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
const actions = {};   // finding_id -> {action, reason?} ; edit replacements read live from the textarea
const boxes = {};     // finding_id -> {box, stateEl, ta}
function mk(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls; if(text!=null)e.textContent=text; return e; }
function b64utf8(s){ return btoa(unescape(encodeURIComponent(s))); }  // UTF-8-safe base64 for edits

// theme toggle (mock behavior: explicit data-theme wins over prefers-color-scheme)
document.getElementById('tg').onclick = () => {
  const root=document.documentElement;
  const cur=root.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  root.setAttribute('data-theme', cur==='dark'?'light':'dark');
};

const root = document.getElementById('findings');
PAYLOAD.findings.forEach(f => {
  const blocked = f.verifier_precheck && f.verifier_precheck.status === 'blocked';
  const box = mk('div','f'+(blocked?' blocked':'')); box.dataset.state='';

  // top row: category / genre / recommendation chips + live state label
  const top = mk('div','top');
  top.appendChild(mk('span','cat', f.category));
  if(f.genre) top.appendChild(mk('span','gen', f.genre));
  top.appendChild(mk('span','rec '+(f.recommendation==='strip'?'strip':'keep'),
    'recommend: '+f.recommendation+(f.confidence==='low'?' (low conf)':'')));
  if(blocked) top.appendChild(mk('span','rec blockedchip','blocked'));
  const stateEl = mk('span','state','');
  top.appendChild(stateEl);
  box.appendChild(top);

  // the passage: strike the original; show the engine's proposal in green when it differs.
  const ms = mk('p','ms');
  const proposal = (typeof f.proposed_rewrite === 'string') ? f.proposed_rewrite : null;
  if(f.recommendation==='strip' && proposal !== null && proposal !== f.span_text){
    ms.appendChild(mk('span','strike', f.span_text));
    ms.appendChild(document.createTextNode(' '));
    ms.appendChild(mk('span','to', proposal === '' ? '∅ (span deleted)' : proposal));
  } else {
    ms.appendChild(mk('span', null, f.span_text || ''));
  }
  box.appendChild(ms);

  // why: rationale + evidence + verifier precheck
  const why = mk('p','why');
  why.appendChild(document.createTextNode(f.rationale+' '));
  if(f.evidence){ why.appendChild(mk('span','ev', f.evidence)); why.appendChild(document.createTextNode(' ')); }
  if(blocked){
    why.appendChild(mk('b', null, 'Verifier precheck: BLOCKED'));
    if(f.verifier_precheck.reason) why.appendChild(document.createTextNode(' — '+f.verifier_precheck.reason));
    why.appendChild(document.createTextNode(' Selecting feedback only — this edit can never apply.'));
  } else {
    why.appendChild(document.createTextNode('Verifier precheck: safe.'));
  }
  box.appendChild(why);

  // inline edit box (mock: hand-tune of visible text; empty = delete is NOT allowed — use apply strip)
  const eb = mk('div','editbox');
  const ta = document.createElement('textarea');
  ta.value = f.span_text || '';
  ta.setAttribute('aria-label','Edit replacement for '+f.id);
  eb.appendChild(ta);
  eb.appendChild(mk('div','hint','your text replaces the whole span — verifier-gated exactly like the proposal; to delete the span use ✂ apply strip'));
  box.appendChild(eb);

  const act = mk('div','btns');
  function refreshOne(){
    const s = box.dataset.state;
    stateEl.textContent = s==='apply' ? '✂ will apply' : (s==='edit' ? '✎ will apply (edited)' : (s==='discard' ? '✓ kept original' : ''));
    if(s==='edit'){ eb.classList.add('show'); } else { eb.classList.remove('show'); }
    refreshTally();
  }
  function choose(action, extra){
    if(box.dataset.state===action){ delete actions[f.id]; box.dataset.state=''; }   // re-click = unset (mock)
    else { actions[f.id]=Object.assign({action:action}, extra||{}); box.dataset.state=action; }
    refreshOne();
  }
  function btn(cls, label, action, extra, recd){
    const b = mk('button','btn '+cls+(recd?' recd':''), label);
    b.onclick=()=>choose(action, extra);
    return b;
  }
  if(!blocked){
    act.appendChild(btn('apply','✂ apply strip','apply', null, f.recommendation==='strip'));
    act.appendChild(btn('edit','✎ edit','edit', null, false));
  }
  // agreeing with a keep recommendation is not a voice-override; only tag keep_voice when overriding a strip.
  act.appendChild(btn('discard', (f.recommendation==='keep'?'✓ keep original':'✋ keep original'), 'discard',
    f.recommendation==='keep' ? {} : {reason:'keep_voice'}, f.recommendation==='keep'));
  if(blocked){ act.appendChild(btn('discard','⚑ mark false positive','discard',{reason:'false_positive'}, false)); }
  box.appendChild(act);
  boxes[f.id] = {box:box, stateEl:stateEl, ta:ta};
  root.appendChild(box);
});

function refreshTally(){
  let a=0,e=0,d=0;
  PAYLOAD.findings.forEach(f=>{ const x=actions[f.id]; if(!x) return;
    if(x.action==='apply')a++; else if(x.action==='edit')e++; else if(x.action==='discard')d++; });
  const total=PAYLOAD.findings.length, u=total-a-e-d;
  document.getElementById('tally').textContent = a+' strip · '+e+' edited · '+d+' keep · '+u+' undecided';
  document.getElementById('prog').textContent = (a+e+d)+' / '+total+' decided';
}

// decisions are assembled at Finish/Export time so edits reflect the textarea's CURRENT text.
// Returns null (and reports) when an edit has an empty replacement — empty means "delete", which is
// the apply-strip action, never a silent empty edit.
function decisions(){
  const out=[];
  for(const f of PAYLOAD.findings){
    const a=actions[f.id]; if(!a) continue;
    const d={finding_id:f.id, user_action:a.action};
    if(a.action==='edit'){
      const t=boxes[f.id].ta.value;
      if(t===''){ boxes[f.id].box.scrollIntoView({block:'center'});
        document.getElementById('status').textContent='An edited finding has an empty replacement — type the replacement text, or use ✂ apply strip to delete the span.';
        return null; }
      d.replacement=b64utf8(t);
    }
    if(a.reason)d.reason=a.reason;
    out.push(d);
  }
  return {schema_version:1, doc:PAYLOAD.doc, source_sha256:PAYLOAD.source_sha256, decisions:out};
}
document.getElementById('export').onclick=()=>{
  const dec=decisions(); if(!dec) return;
  const blob=new Blob([JSON.stringify(dec,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='decisions.json'; a.click();
};
document.getElementById('finish').onclick=()=>{
  const dec=decisions(); if(!dec) return;
  if(!POST_URL){ document.getElementById('status').textContent='No server — use Export decisions.json.'; return; }
  fetch(POST_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(dec)})
    .then(r=>{ document.getElementById('status').textContent = r.ok ? 'Decisions saved. You can close this tab.' : 'Save failed (invalid decisions).'; })
    .catch(()=>{ document.getElementById('status').textContent='Save failed (server closed?).'; });
};
refreshTally();
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
        doc_label=html.escape(os.path.basename(str(payload.get("doc", ""))) or "document"),
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
    port = srv.server_address[1]
    # remote-browser hint: the server is loopback-only BY DESIGN, so a browser on another machine
    # reaches it via an SSH -L tunnel. SLOPSLAP_TUNNEL_HOST names the ssh destination (an
    # ~/.ssh/config alias or user@host) — override per environment; never a bind change.
    tunnel_host = os.environ.get("SLOPSLAP_TUNNEL_HOST", "claude-code")
    print(f"review → {srv.url}\n(loopback only, per-run token; {len(payload['findings'])} findings; "
          f"decisions → {args.out}; idle-timeout {args.idle_timeout:g}s)\n"
          f"remote browser? tunnel first:  ssh -L {port}:127.0.0.1:{port} {tunnel_host}\n"
          f"then open the URL above on that machine.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0 if srv.finished else 2


__all__ = ["build_review_payload", "decisions_from_actions", "render_review_page", "serve_review",
           "main", "REVIEW_SCHEMA_VERSION"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
