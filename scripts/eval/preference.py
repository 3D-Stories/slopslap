#!/usr/bin/env python3
"""Blind paired-preference eval of slopslap's own output (#102).

Each `tests/fixtures/eval/pair-*` directory whose manifest carries an `eval_pair` block holds a
verbatim `original.md` and an `applied.md` that `assemble.py apply` produced from a committed
edit-script. This script shows each pair as a randomized blind A/B and records which side a rater
preferred — a human (terminal loop or a static page) or a cross-model LLM judge — then reports
the two separately. It measures preference; it never emits a single "AI %" or sloppiness score.

Blinding, in two artifacts. The PRIVATE blind file (`build`) carries the two texts as A/B, the
pair's `source_sha256` (the AC2 binding), an unpredictable per-build `token`, and a salted hash of
the bytes on each side (`sha256(run_id + ":" + bytes)`). The RATER-FACING artifact (the static
page) carries only the two texts, the two side hashes and the token: never `source_sha256` and
never `pair_id`, because a rater holding both texts can hash them and read the source side off
either one. A pick carries the side letter plus both side hashes, so the side order rides with the
pick and a later change to the fixture set cannot silently re-map it: `report` resolves each pick
to its fixture (by `pair_id` when a pick carries one, else by matching the side hashes against
each fixture's two files), recovers the roles, refuses anything that does not resolve to exactly
{original, applied}, and writes `source_sha256` back into the published record.

Exit codes: 0 ok · 2 invalid input / refusal (nothing written) · 4 execution failure.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES_DEFAULT = os.path.join(REPO, "tests", "fixtures", "eval")
SCHEMA_VERSION = 1
EXIT_OK, EXIT_INVALID, EXIT_FAILED = 0, 2, 4


class PairError(ValueError):
    """The fixture set or an input file cannot be used as-is (a refusal, exit 2)."""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def side_hash(run_id: str, text: bytes) -> str:
    """The salted hash of the bytes shown on one side: equals neither the source nor the applied
    sha, so it reveals no role by inspection, yet lets `report` recover the role per fixture."""
    return _sha(f"{run_id}:".encode("utf-8") + text)


def pair_id_for(source_sha256: str, applied_sha256: str) -> str:
    return _sha(f"{source_sha256}:{applied_sha256}".encode("utf-8"))[:16]


@dataclass(frozen=True)
class EvalPair:
    dir_name: str
    path: str
    pair_id: str
    source_sha256: str
    applied_sha256: str
    original: bytes
    applied: bytes
    engine_model: str
    genre: str


_MACHINE_HEADER = re.compile(
    r"^\s*(#\s*Adversarial Review|#\s*Peer\b|#\s*Code Review|- Reviewer:|- Model:|- Backend:|Reviewer:\s)",
    re.I | re.M)
_REVIEWS_PATH = re.compile(r"(^|[\s`'\"(/,])docs/reviews/", re.I)


def _refuse_machine_prose(name: str, manifest: dict, ep: dict, original: bytes) -> None:
    """#102 critical finding: every pair the first run shipped was a paragraph of a machine-authored
    adversarial review under `docs/reviews/`, and two cross-model review rounds missed it — so the
    published percentage measured slopslap on deepseek prose. The eval exists to measure slopslap on
    the owner's writing. A fixture whose provenance (structured `source.path` or the free-text
    `provenance`) names a path under `docs/reviews/`, or whose source opens with a review header
    (`# Adversarial Review`, `- Reviewer:`, `- Model:` …), is refused here, before it can be judged.
    """
    # The boundary fails CLOSED (Step 11 re-run F3): a pair must state where its original came from,
    # in one of two canonical shapes. Path and header detection below are an extra deny-list only.
    src = ep.get("source")
    if not isinstance(src, dict):
        raise PairError(f"{name}: eval_pair.source is missing — a pair must state where its original "
                        f"came from (public-repo shape: repo/path/lines/commit/license; owner-supplied "
                        f"shape: kind/document/anonymized/license)")
    kind = src.get("kind")
    if kind == "owner-supplied":
        for k in ("document", "license"):
            if not src.get(k):
                raise PairError(f"{name}: eval_pair.source.{k} is missing from an owner-supplied source")
        if src.get("anonymized") is not True:
            raise PairError(f"{name}: eval_pair.source.anonymized must be true — owner-supplied prose "
                            f"is published only after every identifying name was replaced")
        if src.get("license") != "owner-granted":
            raise PairError(f"{name}: eval_pair.source.license {src.get('license')!r} is not "
                            f"'owner-granted' for an owner-supplied source")
    elif kind in (None, "public-repo"):
        missing = [k for k in ("repo", "path", "lines", "commit", "license") if not src.get(k)]
        if missing:
            raise PairError(f"{name}: eval_pair.source is incomplete for a public-repo source "
                            f"(missing {', '.join(missing)})")
    else:
        raise PairError(f"{name}: eval_pair.source.kind {kind!r} is not a known provenance shape")
    src_path = str(src.get("path") or "")
    if _REVIEWS_PATH.search(src_path) or _REVIEWS_PATH.search(str(manifest.get("provenance") or "")):
        raise PairError(f"{name}: provenance names a path under docs/reviews/ — the reports there are "
                        f"machine-authored review output, not the owner's prose; an eval pair must come "
                        f"from human-written text")
    head = "\n".join(original[:1024].decode("utf-8", "replace").splitlines()[:12])
    if _MACHINE_HEADER.search(head):
        raise PairError(f"{name}: original.md opens with a machine-authored review header — not eligible "
                        f"as a source paragraph for an eval of slopslap on human prose")


def load_eval_pairs(fixtures_dir: str) -> List[EvalPair]:
    """Every `pair-*` manifest with an `eval_pair` block, sorted by directory name.

    A pair is slopslap output or it is not a pair, and this is the place that proves it: matching
    manifest hashes only show that two files differ. So this also REPLAYS the committed edit script
    over `original.md` and requires it to reproduce the applied bytes. Refuses (raises PairError) a
    manifest whose shas do not match its bytes, a recorded apply that did not exit 0, a missing or
    empty edit script, an applied side the edit script does not reproduce, a missing engine_model
    (the cross-model guard cannot fail closed without one), identical sides (a no-op apply is an
    abstention, never a pair), and two pairs sharing a `pair_id`.
    """
    from slopslap_verification.editscript import apply_edits, parse_edits  # noqa: PLC0415 (lazy; pure)
    dirs = sorted(d for d in glob.glob(os.path.join(fixtures_dir, "pair-*")) if os.path.isdir(d))
    pairs: List[EvalPair] = []
    for d in dirs:
        name = os.path.basename(d)
        with open(os.path.join(d, "fixture.json"), "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        ep = manifest.get("eval_pair")
        if not isinstance(ep, dict):
            continue  # a hand-written golden pair: its after side is not slopslap output
        with open(os.path.join(d, "original.md"), "rb") as fh:
            original = fh.read()
        _refuse_machine_prose(name, manifest, ep, original)
        with open(os.path.join(d, manifest.get("clean_file", "applied.md")), "rb") as fh:
            applied = fh.read()
        src, app = _sha(original), _sha(applied)
        if ep.get("source_sha256") != src or ep.get("applied_sha256") != app:
            raise PairError(f"{name}: eval_pair sha256 fields do not match the file bytes (drift)")
        if src == app:
            raise PairError(f"{name}: identical sides (source_sha256 == applied_sha256) — "
                            f"a no-op apply is an abstention, not a pair")
        if ep.get("apply_exit") != 0:
            raise PairError(f"{name}: eval_pair apply_exit is {ep.get('apply_exit')!r}, not 0 — "
                            f"a failed apply did not produce slopslap output")
        engine_model = str(ep.get("engine_model") or "").strip()
        if not engine_model:
            raise PairError(f"{name}: eval_pair carries no engine_model — the cross-model guard "
                            f"cannot fail closed against an unknown author")
        edits_name = str(ep.get("edits_file") or "").strip()
        if not edits_name:
            raise PairError(f"{name}: eval_pair names no edits_file — nothing can replay the applied "
                            f"side, so nothing shows it is engine output rather than hand-written")
        edits_path = os.path.join(d, edits_name)
        if not os.path.isfile(edits_path):
            raise PairError(f"{name}: edits_file {edits_name!r} is missing")
        with open(edits_path, "r", encoding="utf-8") as fh:
            raw_edits = json.load(fh)
        if not raw_edits:
            raise PairError(f"{name}: {edits_name} is empty — an eval pair carries at least one edit")
        try:
            replayed = apply_edits(original, parse_edits(raw_edits))
        except Exception as err:  # noqa: BLE001 - any parse/apply failure is one refusal
            # Name the FILE and the error class first: a bare interpreter message like "string
            # indices must be integers" reads as a slopslap bug rather than a bad fixture.
            raise PairError(f"{name}: {edits_name} is not a usable edit script "
                            f"({type(err).__name__}: {err})") from err
        if replayed != applied:
            raise PairError(f"{name}: replaying the committed edit script does not reproduce the "
                            f"applied side — those bytes are not this edit script's output")
        result_name = str(ep.get("apply_result_file") or "").strip()
        if not result_name:
            raise PairError(f"{name}: eval_pair names no apply_result_file — nothing records that "
                            f"the engine ran, or over which source it ran")
        result_path = os.path.join(d, result_name)
        if not os.path.isfile(result_path):
            raise PairError(f"{name}: apply_result_file {result_name!r} is missing")
        with open(result_path, "r", encoding="utf-8") as fh:
            apply_result = json.load(fh)
        if not isinstance(apply_result, dict) or apply_result.get("status") != "ok":
            raise PairError(f"{name}: apply_result status is "
                            f"{(apply_result or {}).get('status')!r}, not 'ok' — the recorded run "
                            f"did not succeed")
        stages = apply_result.get("stages")
        audit = None
        if isinstance(stages, list):
            audit = next((st.get("data") for st in stages
                          if isinstance(st, dict) and st.get("stage") == "audit"), None)
        if not isinstance(audit, dict) or audit.get("source_sha256") != src:
            raise PairError(f"{name}: apply_result audit stage does not bind to this source "
                            f"(expected {src}, found "
                            f"{(audit or {}).get('source_sha256')!r}) — the record belongs to "
                            f"another document")
        pairs.append(EvalPair(dir_name=name, path=d, pair_id=pair_id_for(src, app),
                              source_sha256=src, applied_sha256=app, original=original,
                              applied=applied, engine_model=engine_model,
                              genre=str(manifest.get("genre") or "")))
    seen: dict = {}
    for p in pairs:
        if p.pair_id in seen:
            raise PairError(f"duplicate pair_id {p.pair_id}: {seen[p.pair_id]} and {p.dir_name}")
        seen[p.pair_id] = p.dir_name
    return pairs


def build_pairs(pairs: List[EvalPair], seed: Optional[str] = None, run_id: Optional[str] = None) -> dict:
    """The BLIND file. Side order per pair comes from `random.Random(seed)` in the sorted fixture
    order, so one seed gives one order and one set of pair_ids; `run_id` is fresh per build.

    Each pair also gets a `token`: an unpredictable per-build handle, and the ONLY pair identifier
    the rater-facing page may carry. `pair_id` is `sha256(source:applied)`, so a rater holding both
    visible texts can hash them, try both orders, and read the source side straight off a matching
    pair_id. A token drawn from `secrets` is not reachable that way.
    """
    if not pairs:
        raise PairError("no eval pairs found (no pair-* manifest carries an eval_pair block)")
    seed = seed if seed is not None else secrets.token_hex(8)
    run_id = run_id if run_id is not None else secrets.token_hex(16)
    rng = random.Random(seed)
    items = []
    for p in pairs:
        applied_first = rng.random() < 0.5
        a, b = (p.applied, p.original) if applied_first else (p.original, p.applied)
        items.append({
            "pair_id": p.pair_id,
            "token": secrets.token_hex(8),
            "source_sha256": p.source_sha256,
            "a_text": a.decode("utf-8"),
            "b_text": b.decode("utf-8"),
            "a_side_hash": side_hash(run_id, a),
            "b_side_hash": side_hash(run_id, b),
        })
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "seed": seed,
            "created_at": _now(), "pairs": items}


def validate_blind_json(blind: dict, pairs: List[EvalPair]) -> None:
    """A supplied blind file must BE this fixture set, not merely look like a blind file.

    It was checked only for its schema version, a pairs list and a `run_id`. So a stale or trimmed
    `pairs.json` holding one favorable pair drove a judge run that reported `completed` over that
    subset, which is the opposite of the drift refusal this file promises. Every pair must be
    present exactly once, and each one's texts, source hash and side hashes must recompute from the
    fixture bytes under the file's own `run_id`.
    """
    run_id = blind.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PairError("blind file has no run_id")
    items = blind.get("pairs")
    if not isinstance(items, list) or not items:
        raise PairError("blind file carries no pairs")
    by_id = {p.pair_id: p for p in pairs}
    seen: dict = {}
    tokens: dict = {}
    for bp in items:
        if not isinstance(bp, dict):
            raise PairError("a blind pair entry is not an object")
        pid = bp.get("pair_id")
        fx = by_id.get(pid)
        if fx is None:
            raise PairError(f"blind file names pair_id {pid!r}, which this fixture set does not hold")
        if pid in seen:
            raise PairError(f"blind file carries pair_id {pid} twice")
        seen[pid] = True
        token = bp.get("token")
        if not isinstance(token, str) or not token:
            raise PairError(f"blind pair {pid}: no token")
        if token in tokens:
            raise PairError(f"blind file reuses token {token!r} across pairs")
        tokens[token] = True
        if bp.get("source_sha256") != fx.source_sha256:
            raise PairError(f"blind pair {pid}: source_sha256 is not this fixture's")
        try:
            a = str(bp["a_text"]).encode("utf-8")
            b = str(bp["b_text"]).encode("utf-8")
        except KeyError as err:
            raise PairError(f"blind pair {pid}: missing {err.args[0]}") from err
        if {a, b} != {fx.original, fx.applied}:
            raise PairError(f"blind pair {pid}: its two side texts are not this fixture's "
                            f"original.md and applied.md")
        for side, text in (("a", a), ("b", b)):
            if bp.get(f"{side}_side_hash") != side_hash(run_id, text):
                raise PairError(f"blind pair {pid}: {side}_side_hash does not match the text it "
                                f"sits beside under run_id {run_id!r}")
    missing = sorted(set(by_id) - set(seen))
    if missing:
        raise PairError(f"blind file covers {len(seen)} of {len(by_id)} pair(s); it must cover the "
                        f"whole current fixture set, and it omits: {', '.join(missing)}")


def _write_json(path: str, obj: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def _load_blind(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        blind = json.load(fh)
    if not isinstance(blind, dict) or blind.get("schema_version") != SCHEMA_VERSION \
            or not isinstance(blind.get("pairs"), list) or not blind.get("run_id"):
        raise PairError(f"{path}: not a schema_version-{SCHEMA_VERSION} blind pairs file")
    return blind


def _pick_record(bp: dict, pick: str) -> dict:
    return {"pair_id": bp["pair_id"], "token": bp["token"], "source_sha256": bp["source_sha256"],
            "pick": pick, "a_side_hash": bp["a_side_hash"], "b_side_hash": bp["b_side_hash"]}


# ---------------------------------------------------------------------------- human: terminal loop
_PROMPT = "[a] A reads better   [b] B reads better   [=] no preference   [s] skip   [q] quit > "
_KEYS = {"a": "A", "b": "B", "=": "equal", "s": "skip", "q": "quit"}


def run_human_cli(blind: dict, rater: str, stdin, stdout) -> dict:
    """Show each pair blind, read one key per pair. Skips record nothing; quit ends the session."""
    picks = []
    total = len(blind["pairs"])
    for i, bp in enumerate(blind["pairs"], 1):
        print(f"\n=== Pair {i} of {total} — which version reads better? ===", file=stdout)
        print("--- Version A ---", file=stdout)
        print(bp["a_text"].rstrip("\n"), file=stdout)
        print("--- Version B ---", file=stdout)
        print(bp["b_text"].rstrip("\n"), file=stdout)
        choice = None
        while choice is None:
            print(_PROMPT, end="", file=stdout)
            stdout.flush()
            line = stdin.readline()
            if not line:
                choice = "quit"
                break
            choice = _KEYS.get(line.strip().lower())
            if choice is None:
                print("  please answer a, b, =, s or q", file=stdout)
        if choice == "quit":
            break
        if choice == "skip":
            continue
        picks.append(_pick_record(bp, choice))
    print(f"\nrecorded {len(picks)} pick(s)", file=stdout)
    return {"schema_version": SCHEMA_VERSION, "run_id": blind["run_id"], "rater": rater,
            "mode": "cli", "created_at": _now(), "picks": picks}


# ---------------------------------------------------------------------------- human: static page
# The page embeds the blind data as JSON inside a <script type="application/json"> element. Every
# `</` in that JSON is written as `<\/` (a valid JSON escape), so no fixture byte can close the
# data element and inject markup. The app script builds the DOM with createElement/textContent
# only. Nothing in the data or the copy names a role; the seed is not embedded.
_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blind A/B rating</title>
<style>
body{font:16px/1.55 Georgia,serif;max-width:64rem;margin:2rem auto;padding:0 1rem;background:#fbf8f1;color:#222}
h1{font-size:1.4rem;margin:0 0 .25rem} .sub{color:#666;font:14px/1.4 system-ui,sans-serif;margin-bottom:1.5rem}
.pair{border:1px solid #d8d2c4;border-radius:8px;padding:1rem;margin:1rem 0;background:#fff}
.sides{display:grid;grid-template-columns:1fr 1fr;gap:1rem} .side{white-space:pre-wrap;padding:.75rem;border:1px solid #eee;border-radius:6px;background:#fdfcf9}
.side h3{font:600 13px/1 system-ui,sans-serif;margin:0 0 .5rem;color:#555}
.btns{margin-top:.75rem;display:flex;gap:.5rem;font:14px system-ui,sans-serif} button{padding:.4rem .8rem;border-radius:6px;border:1px solid #999;background:#f4f1ea;cursor:pointer}
button.on{background:#2b6cb0;color:#fff;border-color:#2b6cb0} .bar{position:sticky;top:0;background:#fbf8f1;padding:.5rem 0;font:14px system-ui,sans-serif;display:flex;gap:1rem;align-items:center;border-bottom:1px solid #d8d2c4}
input{padding:.3rem .5rem;font:14px system-ui,sans-serif} #status{color:#555}
</style></head><body>
<h1>Blind A/B rating</h1>
<div class="sub">Two versions of one paragraph. Pick the one that reads better for the kind of document it is. Side order is random per pair. When you finish, export your picks.</div>
<div class="bar"><label>Rater <input id="rater" placeholder="your name"></label><span id="status"></span><button id="export">Export picks</button></div>
<div id="pairs"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  var data = JSON.parse(document.getElementById('data').textContent);
  var picks = {};
  var root = document.getElementById('pairs');
  function el(tag, cls, text){ var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function status(){ var n = Object.keys(picks).length; document.getElementById('status').textContent = n + ' of ' + data.pairs.length + ' rated'; }
  data.pairs.forEach(function(p, i){
    var box = el('div', 'pair'); box.appendChild(el('h2', null, 'Pair ' + (i + 1) + ' of ' + data.pairs.length));
    var sides = el('div', 'sides');
    var a = el('div', 'side'); a.appendChild(el('h3', null, 'Version A')); a.appendChild(el('div', null, p.a_text));
    var b = el('div', 'side'); b.appendChild(el('h3', null, 'Version B')); b.appendChild(el('div', null, p.b_text));
    sides.appendChild(a); sides.appendChild(b); box.appendChild(sides);
    var btns = el('div', 'btns');
    [['A', 'A reads better'], ['B', 'B reads better'], ['equal', 'No preference']].forEach(function(opt){
      var btn = el('button', null, opt[1]);
      btn.addEventListener('click', function(){
        picks[p.token] = opt[0];
        Array.prototype.forEach.call(btns.children, function(c){ c.className = ''; });
        btn.className = 'on'; status();
      });
      btns.appendChild(btn);
    });
    box.appendChild(btns); root.appendChild(box);
  });
  status();
  document.getElementById('export').addEventListener('click', function(){
    var rater = document.getElementById('rater').value.trim() || 'rater';
    var out = { schema_version: data.schema_version, run_id: data.run_id, rater: rater, mode: 'static-page',
                created_at: new Date().toISOString(), picks: [] };
    data.pairs.forEach(function(p){
      if (!picks[p.token]) return;
      out.picks.push({ token: p.token, pick: picks[p.token],
                       a_side_hash: p.a_side_hash, b_side_hash: p.b_side_hash });
    });
    var blob = new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' });
    var link = document.createElement('a'); link.href = URL.createObjectURL(blob);
    link.download = 'picks-' + rater.replace(/[^A-Za-z0-9_-]/g, '_') + '.json'; link.click();
  });
})();
</script>
</body></html>
"""


def render_static_page(blind: dict) -> str:
    """The rater-facing artifact. It carries the two texts, the two salted side hashes of exactly
    those two texts, and an opaque `token` per pair — and NEITHER `source_sha256` NOR `pair_id`,
    because each of those lets a rater recover which side is the source by hashing what is on
    screen. `report` re-binds each pick to its fixture from the side hashes, so AC2's
    source_sha256 binding survives in the record without the page ever holding it."""
    data = {"schema_version": blind["schema_version"], "run_id": blind["run_id"],
            "pairs": [{k: p[k] for k in ("token", "a_text", "b_text",
                                         "a_side_hash", "b_side_hash")} for p in blind["pairs"]]}
    # `</` alone is already enough to stop a raw-text end tag (it carries no letter, so
    # `</SCRIPT>` and `</ScRiPt>` are covered too — measured). This goes further and leaves NO
    # literal `<` or `>` from fixture bytes in the page at all, so the guarantee stops depending
    # on anyone reasoning correctly about HTML raw-text rules.
    payload = (json.dumps(data, ensure_ascii=False)
               .replace("<", "\\u003c").replace(">", "\\u003e"))
    return _PAGE.replace("__DATA__", payload)


# ---------------------------------------------------------------------------- judge (SLOPSLAP_LIVE)
def _cross_model_guard(judge_model: str, engine_models: List[str]) -> None:
    """Refuse a judge that is the rewrite engine (the same token rule as invoke._model_confirmed,
    checked in both directions so an alias on either side still matches). An engine identity that
    is absent or empty is a REFUSAL, never a pass: a filtered-out empty model would let the run
    report cross-model completion while the judge was the author."""
    from slopslap_invoke.invoke import models_match  # noqa: PLC0415 (lazy; pure)
    if not engine_models:
        raise PairError("cross-model guard: the fixture set names no rewrite engine; the judge "
                        "cannot be shown to differ from an author nobody recorded")
    for em in engine_models:
        if not str(em or "").strip():
            raise PairError("cross-model guard: a fixture carries no engine model; refusing rather "
                            "than judging against an unknown author")
        if models_match(judge_model, [em]) or models_match(em, [judge_model]):
            raise PairError(f"cross-model guard: judge model {judge_model!r} matches the rewrite "
                            f"engine {em!r}; the judge must be a different model")


def _verdict_json(v) -> dict:
    return {"present": v.present, "errored": v.errored, "beat": v.beat, "detail": v.detail,
            "candidate_median": v.candidate_median, "baseline_median": v.baseline_median}


def run_judge(pairs: List[EvalPair], blind: dict, *, model: str, trials: int, timeout_s: float,
              transport=None) -> dict:
    """Live judge over every pair: `trials` blinded trials each, a fresh side order per trial,
    scored through the judge.py scaffold. A failed call is a missing trial — never a verdict."""
    from eval import judge as J  # noqa: PLC0415
    by_id = {p.pair_id: p for p in pairs}
    sink: dict = {}
    fn = J.judge_fn_for(model, timeout_s=timeout_s, transport=transport, status_sink=sink)
    run_id, seed = blind["run_id"], blind["seed"]
    out_pairs = []
    tot_attempted = 0                     # calls we actually made, so a reason cannot misreport it
    tot_valid = tot_failed = 0            # raw judge CALLS: how the transport did
    tot_scored = tot_app = tot_orig = tot_eq = 0   # only pairs with a present, non-errored verdict
    for bp in blind["pairs"]:
        fx = by_id.get(bp["pair_id"])
        if fx is None:
            raise PairError(f"blind file pair {bp['pair_id']} is not in the fixture set (stale pairs.json)")
        recs, jtrials = [], []
        app = orig = eq = 0
        for t in range(trials):
            tot_attempted += 1
            applied_first = random.Random(f"{seed}:{fx.pair_id}:{t}").random() < 0.5
            a, b = (fx.applied, fx.original) if applied_first else (fx.original, fx.applied)
            applied_side = "A" if applied_first else "B"
            parsed = fn(a.decode("utf-8"), b.decode("utf-8"))
            rec = {"trial": t, "applied_side": applied_side, "a_side_hash": side_hash(run_id, a),
                   "b_side_hash": side_hash(run_id, b), "ok": parsed is not None}
            if parsed is None:
                rec.update(preferred_side=None, preferred_role=None)
                tot_failed += 1
            else:
                role = J.role_of(parsed["preferred"], applied_side)
                rec.update(preferred_side=parsed["preferred"], preferred_role=role,
                           dimensions_role={d: J.role_of(v, applied_side) for d, v in parsed["dimensions"].items()},
                           reason=parsed["reason"][:500])
                jtrials.append(J.trial_from_blind(parsed, applied_side))
                if role == "applied":
                    app += 1
                elif role == "original":
                    orig += 1
                else:
                    eq += 1
            recs.append(rec)
        verdict = J.evaluate(jtrials)
        tot_valid += len(jtrials)
        # The renderer states that errored pairs are excluded from the percentages, so their trials
        # must never reach the totals those percentages come from. A pair with one or two valid
        # trials is ERRORED (judge.evaluate needs three), and it used to contaminate the number.
        if verdict.present and not verdict.errored:
            tot_scored += len(jtrials); tot_app += app; tot_orig += orig; tot_eq += eq
        # `majority_applied` is a WIN claim, and the results document prints it as one. An
        # errored or short pair has won nothing, however its few answered trials fell.
        scored_pair = verdict.present and not verdict.errored and len(jtrials) == trials
        out_pairs.append({"pair_id": fx.pair_id, "dir_name": fx.dir_name, "genre": fx.genre,
                          "trials": recs, "valid_trials": len(jtrials), "verdict": _verdict_json(verdict),
                          "applied_preferred_trials": app, "original_preferred_trials": orig,
                          "equal_trials": eq,
                          "majority_applied": bool(scored_pair and app > orig)})
    decided = tot_app + tot_orig
    summary = {
        "pairs": len(out_pairs),
        # a pair is COMPLETED only with a present, non-errored verdict; zero valid trials is errored
        # (judge.evaluate([]) says present=False — "no trials" — which must never read as completed).
        "pairs_completed": sum(1 for p in out_pairs if p["verdict"]["present"] and not p["verdict"]["errored"]),
        "pairs_errored": sum(1 for p in out_pairs if not p["verdict"]["present"] or p["verdict"]["errored"]),
        "trials_valid": tot_valid, "trials_failed": tot_failed, "trials_scored": tot_scored,
        "applied_preferred_trials": tot_app, "original_preferred_trials": tot_orig, "equal_trials": tot_eq,
        "applied_preference_pct_of_decided": (round(100.0 * tot_app / decided, 1) if decided else None),
        "pairs_majority_applied": sum(1 for p in out_pairs if p["majority_applied"]),
        "pairs_beat": sum(1 for p in out_pairs if p["verdict"]["beat"]),
    }
    # COMPLETED means every pair reached a present, non-errored verdict on a full set of trials —
    # never "at least one call came back". `_cmd_judge` turns anything else into EXIT_FAILED, so a
    # run automation accepts is a run where every pair actually has a usable verdict.
    every_pair_complete = bool(out_pairs) and summary["pairs_completed"] == summary["pairs"] and all(
        p["valid_trials"] == trials for p in out_pairs)
    status = "completed" if every_pair_complete else ("partial" if tot_valid else "failed")
    obj = {"schema_version": SCHEMA_VERSION, "status": status, "model": model,
           "model_confirmed": bool(sink.get("model_confirmed", False)),
           "engine_models": sorted({p.engine_model for p in pairs if p.engine_model}),
           "run_id": run_id, "seed": seed, "trials_per_pair": trials, "timeout_s": timeout_s,
           "created_at": _now(), "pairs": out_pairs, "summary": summary}
    if status == "failed" and not tot_attempted:
        # "every call failed" would send an operator hunting a transport fault that never happened.
        obj["reason"] = (f"no judge call was attempted (trials_per_pair={trials} over "
                         f"{len(out_pairs)} pair(s)); nothing to score")
    elif status == "failed":
        obj["reason"] = (f"every judge call failed ({tot_attempted} attempted, last "
                         f"invocation_status={sink.get('invocation_status', 'unknown')}); "
                         f"nothing to score")
    elif status == "partial":
        obj["reason"] = (f"{summary['pairs_completed']} of {summary['pairs']} pair(s) reached a "
                         f"present, non-errored verdict with {trials} valid trial(s) each; "
                         f"{summary['trials_failed']} call(s) failed")
    return obj


def _cmd_judge(args, stdin, stdout, judge_transport=None) -> int:
    from eval.judge import live_judge_available  # noqa: PLC0415
    if args.trials < 1:
        raise PairError(f"--trials must be at least 1, not {args.trials}; a run that asks for no "
                        f"trial cannot produce a verdict (and note judge.evaluate needs 3 for a "
                        f"non-errored one)")
    pairs = load_eval_pairs(args.fixtures)
    _cross_model_guard(args.model, sorted({p.engine_model for p in pairs}))
    blind = _blind_from_args(args)
    if not live_judge_available():
        _write_json(args.out, {
            "schema_version": SCHEMA_VERSION, "status": "not_run", "model": args.model,
            "model_confirmed": False, "created_at": _now(),
            "reason": ("SLOPSLAP_LIVE is not '1' — the live judge did not run and nothing was called; "
                       "set SLOPSLAP_LIVE=1 (Codex CLI + auth required) to run it")})
        print(f"wrote {args.out}: judge not_run (SLOPSLAP_LIVE is not '1')", file=stdout)
        return EXIT_OK
    obj = run_judge(pairs, blind, model=args.model, trials=args.trials, timeout_s=args.timeout,
                    transport=judge_transport)
    _write_json(args.out, obj)
    s = obj["summary"]
    print(f"wrote {args.out}: status {obj['status']}, {s['pairs']} pair(s), {s['trials_valid']} valid trial(s), "
          f"{s['trials_failed']} failed, applied preferred in {s['applied_preferred_trials']} "
          f"({s['applied_preference_pct_of_decided']}% of decided)", file=stdout)
    return EXIT_OK if obj["status"] == "completed" else EXIT_FAILED


# ---------------------------------------------------------------------------- report
def recover_applied_side(pick: dict, fx: EvalPair, run_id: str) -> str:
    """Which blind side held the applied text, recovered from THIS fixture's bytes under the picks
    file's run_id. Refuses (PairError) a drifted source, missing/equal side hashes, a side that
    matches neither file or both, or a recovered role set other than exactly {original, applied}."""
    pid = pick.get("pair_id") or pick.get("token")
    if "source_sha256" in pick and pick.get("source_sha256") != fx.source_sha256:
        raise PairError(f"pick {pid}: source_sha256 does not match the fixture (drifted file / replay)")
    a, b = pick.get("a_side_hash"), pick.get("b_side_hash")
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
        raise PairError(f"pick {pid}: side hashes are missing or equal")
    h_orig, h_app = side_hash(run_id, fx.original), side_hash(run_id, fx.applied)
    roles = {}
    for side, h in (("A", a), ("B", b)):
        if h == h_orig and h != h_app:
            roles[side] = "original"
        elif h == h_app and h != h_orig:
            roles[side] = "applied"
        else:
            raise PairError(f"pick {pid}: side {side} hash matches neither fixture file (or both) "
                            f"under run_id {run_id!r}")
    if set(roles.values()) != {"original", "applied"}:
        raise PairError(f"pick {pid}: recovered roles are {sorted(roles.values())}, not exactly original+applied")
    return "A" if roles["A"] == "applied" else "B"


def _fixture_for_pick(pk: dict, by_id: dict, by_sides: dict) -> EvalPair:
    """The fixture a pick belongs to. A terminal pick names its `pair_id`; a page pick cannot (the
    page never holds one), so its two side hashes identify the fixture instead — the same salted
    hashes `recover_applied_side` then uses to recover the roles."""
    pid = pk.get("pair_id")
    if pid is not None:
        fx = by_id.get(pid)
        if fx is None:
            raise PairError(f"pick names unknown pair_id {pid!r}")
        return fx
    a, b = pk.get("a_side_hash"), pk.get("b_side_hash")
    label = pk.get("token")
    # Name the ACTUAL cause. Falling through to the side-hash lookup reported "matches no fixture"
    # for a pick that carried no identifier at all, and for one whose two hashes were equal.
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
        raise PairError(f"pick {label!r} carries neither a pair_id nor two side hashes, so nothing "
                        f"identifies which pair it rates")
    if a == b:
        raise PairError(f"pick {label!r}: its two side hashes are equal, so the pair it rates "
                        f"cannot be identified and no preference could be recovered from it")
    fx = by_sides.get(frozenset((a, b)))
    if fx is None:
        raise PairError(f"pick {label!r}: its side hashes match no fixture under this run_id")
    return fx


def score_picks(picks_obj: dict, by_id: dict) -> dict:
    """One rater's picks → counts. Every pick is validated (PairError on any drift), and a pair may
    be picked at most ONCE: repeating one valid pick would otherwise inflate both `pairs_rated` and
    the preference count straight into the published percentage."""
    if not isinstance(picks_obj, dict) or picks_obj.get("schema_version") != SCHEMA_VERSION:
        raise PairError("picks file is not schema_version 1")
    run_id = picks_obj.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PairError("picks file has no run_id")
    picks = picks_obj.get("picks")
    if not isinstance(picks, list):
        raise PairError("picks file has no picks list")
    by_sides = {frozenset((side_hash(run_id, p.original), side_hash(run_id, p.applied))): p
                for p in by_id.values()}
    app = orig = eq = 0
    out = []
    seen_pairs: dict = {}
    for pk in picks:
        if not isinstance(pk, dict):
            raise PairError("a pick is not an object")
        fx = _fixture_for_pick(pk, by_id, by_sides)
        if fx.pair_id in seen_pairs:
            raise PairError(f"pair {fx.pair_id} ({fx.dir_name}) is picked twice in one picks file — "
                            f"one rater gives one pair one pick")
        seen_pairs[fx.pair_id] = True
        applied_side = recover_applied_side(pk, fx, run_id)
        pick = pk.get("pick")
        if pick not in ("A", "B", "equal"):
            raise PairError(f"pick {fx.pair_id}: pick must be A, B or equal")
        role = "equal" if pick == "equal" else ("applied" if pick == applied_side else "original")
        if role == "applied":
            app += 1
        elif role == "original":
            orig += 1
        else:
            eq += 1
        out.append({"pair_id": fx.pair_id, "dir_name": fx.dir_name, "pick": pick,
                    "source_sha256": fx.source_sha256, "applied_side": applied_side, "role": role})
    decided = app + orig
    return {"rater": str(picks_obj.get("rater") or "rater"), "mode": str(picks_obj.get("mode") or ""),
            "run_id": run_id, "pairs_rated": len(out), "applied_preferred": app,
            "original_preferred": orig, "equal": eq,
            "applied_pct_of_decided": (round(100.0 * app / decided, 1) if decided else None),
            "picks": out}


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:g}%"


_DISPOSITION_MEANING = {
    "shipped": "engine repair authorized, verifier ACCEPT, applied — a pair",
    "verifier_blocked": "engine proposed a repair; the byte-exact verifier rejected it and no safe alternative existed",
    "verifier_withheld": "engine proposed a repair and the verify stage accepted it, but the live Layer-3 semantic check withheld the hunk at apply time; nothing was written",
    "not_authorized": "no strip-recommended tell under the auto-classified genre, so the autonomous path authorized no range",
    "abstained": "authorized, but the engine found no demonstrated harm",
    "excluded_circular": "quotes slop examples itself; excluded as circular",
    "excluded_third_party": "authorized, but the paragraph quotes or paraphrases a third party; excluded",
    "excluded_machine_authored": "the source file is a machine-authored review report, not the owner's prose; excluded",
    "dropped_on_anonymization": "authorized before anonymization; the audit found nothing once the names were replaced",
}


def _funnel_rows(ab: dict, n_pairs: int) -> list:
    """The abstention funnel, top to bottom: sampled → authorized → repaired → paired. A ledger may
    carry it explicitly as `funnel: [{stage, count, meaning}, ...]`; an older ledger with only
    `sampled` + `breakdown` gets the four rows derived, so the funnel is never absent."""
    explicit = ab.get("funnel")
    if isinstance(explicit, list) and explicit:
        return [(str(r.get("stage")), r.get("count"), str(r.get("meaning") or "")) for r in explicit]
    bd = ab.get("breakdown") or {}
    items = ab.get("items") or []
    sampled = ab.get("sampled", len(items))
    # Authorized comes from item-level authorization when the ledger carries items: an excluded
    # paragraph may well have been authorized first (the old ledger's circular one was), so it must
    # not be subtracted (Step 11 re-run F5). Without items, only `not_authorized` is known to be out.
    if items:
        authorized = sum(1 for it in items if isinstance(it, dict) and it.get("authorization")
                         and it.get("authorization") != "reject_all")
    else:
        authorized = max(0, int(sampled) - int(bd.get("not_authorized", 0)))
    return [("sampled", sampled, "paragraphs the run examined"),
            ("authorized", authorized, "the offline audit authorized at least one range under the auto-classified genre"),
            ("repaired", bd.get("shipped", 0), "the engine proposed a repair, the byte-exact verifier accepted it, apply wrote it"),
            ("paired", n_pairs, "shipped as a blind A/B pair in this fixture set")]


def validate_ledger(ab: dict, n_pairs: int, *, name: str = "sampling ledger") -> None:
    """The funnel is evidence only if its numbers add up (Step 11 re-run F0/F2): `sampled` is a
    non-negative integer, every `breakdown` count is one and they sum to `sampled`, an explicit
    `funnel` is non-increasing with non-negative integer counts, and its last row is THIS fixture
    set's pair count — a ledger from another run is refused, never rendered under these pairs."""
    def _count(v, what):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise PairError(f"{name}: {what} must be a non-negative integer, got {v!r}")
        return v
    items = ab.get("items") or []
    sampled = _count(ab.get("sampled", len(items)), "sampled")
    if items and len(items) != sampled:
        raise PairError(f"{name}: sampled is {sampled} but the ledger carries {len(items)} items")
    bd = ab.get("breakdown")
    if bd:
        if not isinstance(bd, dict):
            raise PairError(f"{name}: breakdown is not an object")
        total = sum(_count(v, f"breakdown[{k}]") for k, v in bd.items())
        if total != sampled:
            raise PairError(f"{name}: breakdown sums to {total} but sampled is {sampled}")
    # With items present, `breakdown` and the explicit funnel are ASSERTIONS about them, not
    # free-standing numbers (Step 11 re-run D4): each is recomputed from the items and must agree.
    if items:
        if not all(isinstance(it, dict) for it in items):
            raise PairError(f"{name}: items is not a list of objects")
        seen: dict = {}
        for it in items:
            seen[str(it.get("disposition"))] = seen.get(str(it.get("disposition")), 0) + 1
        if bd and dict(bd) != seen:
            raise PairError(f"{name}: breakdown {dict(bd)} does not match the items' dispositions {seen}")
    funnel = ab.get("funnel")
    if funnel:
        if not isinstance(funnel, list) or not all(isinstance(r, dict) for r in funnel):
            raise PairError(f"{name}: funnel is not a list of rows")
        counts = [_count(r.get("count"), f"funnel[{r.get('stage')}]") for r in funnel]
        if items:
            by_stage = {str(r.get("stage")): c for r, c in zip(funnel, counts)}
            derived = {"sampled": len(items),
                       "authorized": sum(1 for it in items if it.get("authorization") and it.get("authorization") != "reject_all"),
                       "repaired": sum(1 for it in items if it.get("disposition") == "shipped")}
            for stage, want in derived.items():
                if stage in by_stage and by_stage[stage] != want:
                    raise PairError(f"{name}: funnel row {stage!r} says {by_stage[stage]} but the items give {want}")
        if any(a < b for a, b in zip(counts, counts[1:])):
            raise PairError(f"{name}: funnel counts must not increase from one stage to the next: {counts}")
        if counts and counts[0] != sampled:
            raise PairError(f"{name}: the funnel's first row is {counts[0]} but sampled is {sampled}")
        if counts and counts[-1] != n_pairs:
            raise PairError(f"{name}: the funnel's last row is {counts[-1]} but this fixture set has "
                            f"{n_pairs} pair(s) — the ledger belongs to a different run")


def _source_cell(src: Optional[dict]) -> str:
    if not src:
        return "(see fixture.json provenance)"
    if src.get("kind") == "owner-supplied":
        parts = ["owner-supplied", str(src.get("document") or "")]
        if src.get("anonymized"):
            parts.append("anonymized")
        parts.append(str(src.get("license") or ""))
        return " · ".join(p for p in parts if p)
    return " · ".join(str(src.get(k)) for k in ("repo", "path", "lines") if src.get(k)) or "(see fixture.json provenance)"


def render_results_md(results: dict) -> str:
    fx = results["fixtures"]
    ab = results.get("abstentions")
    lines = [
        "# Blind paired-preference eval of slopslap's own output — results (#102)", "",
        f"Generated {results['created_at']} by `scripts/eval/preference.py report`. Human raters and the "
        "LLM judge are reported in SEPARATE sections and never combined into one number. This document "
        "reports preference counts and percentages only; it carries no single quality score of any kind.", "",
        "## Abstention funnel — read this first", "",
    ]
    # ---- the funnel leads: how many paragraphs went in, how few came out as pairs. A preference
    # percentage further down is measured over the LAST row only, so it is read in that light.
    if ab:
        sampled = ab.get("sampled", len(ab.get("items", [])))
        lines += [f"{sampled} paragraphs sampled, {len(fx)} shipped as pairs. Every row below counts paragraphs; "
                  f"any preference percentage in this document is measured over the last row only.", ""]
        if ab.get("selection"):
            lines += [str(ab["selection"]), ""]
        lines += ["| stage | paragraphs | meaning |", "|---|---|---|"]
        for stage, count, meaning in _funnel_rows(ab, len(fx)):
            lines.append(f"| {stage} | {count} | {meaning} |")
        bd = ab.get("breakdown") or {}
        if bd:
            lines += ["", "Per-paragraph dispositions:", "", "| disposition | paragraphs | meaning |", "|---|---|---|"]
            for k in sorted(bd, key=lambda k: -bd[k]):
                lines.append(f"| {k} | {bd[k]} | {_DISPOSITION_MEANING.get(k, '')} |")
        lines += ["", f"The full per-paragraph ledger (source, disposition, note) is `{ab.get('file', 'the sampling ledger')}`."]
        if ab.get("status_note"):
            lines += ["", "### Status against the issue", "", str(ab["status_note"])]
    else:
        lines += ["Sampling: not recorded for this run. Without a funnel the pair count below has no denominator."]
    lines += [
        "", "## Method", "",
        "- Each fixture is one source paragraph (`original.md`; its provenance is the pair's `fixture.json`) "
        "and the output of `scripts/slopslap_assemble/assemble.py apply` on it (`applied.md`). The committed "
        "edit-script replays to `applied.md` byte for byte, and the recorded apply exited 0 with a live "
        "semantic pass; that the slopslap ENGINE authored the edit-script is process-reported in each "
        "fixture's provenance and is not something the committed artifacts can prove.",
        "- `build` shows the two as sides A and B in a seeded random order per pair; a rater picks A, B, or "
        "no preference. The pick is recorded with both side hashes (so the side order rides with the pick) "
        "and bound to the pair's `source_sha256`.",
        "- The LLM judge sees the same blind A/B, three trials per pair with a fresh side order each time, and "
        "answers per dimension plus an overall preference; the nine-dimension scaffold in "
        "`scripts/eval/judge.py` scores each trial as applied-vs-original.",
        "- Roles are recovered per fixture from the recorded hashes at report time; a pick that does not "
        "resolve to exactly one original and one applied side is refused, never counted.", "",
        f"## Fixture set — {len(fx)} pairs", "",
        "| pair | source | genre | engine |", "|---|---|---|---|",
    ]
    for f in fx:
        lines.append(f"| `{f['dir_name']}` | {_source_cell(f.get('source'))} | {f['genre']} | `{f['engine_model']}` |")
    # ---- human
    lines += ["", "## Human raters", ""]
    raters = results["human"]["raters"]
    if not raters:
        lines += ["**Human mode: not yet run — 0 raters.** The rating page and the terminal loop are built "
                  "(`preference.py human`), but no human has rated these pairs yet. No human preference "
                  "percentage exists to report."]
    else:
        lines += [f"{len(raters)} rater(s). Percentages are of DECIDED picks (A or B); no-preference picks are "
                  "counted separately and never folded into a percentage.", "",
                  "| rater | mode | pairs rated | applied preferred | original preferred | no preference | applied % of decided |",
                  "|---|---|---|---|---|---|---|"]
        for r in raters:
            lines.append(f"| {r['rater']} | {r['mode']} | {r['pairs_rated']} pairs | {r['applied_preferred']} | "
                         f"{r['original_preferred']} | {r['equal']} | {_pct(r['applied_pct_of_decided'])} |")
        n = len(raters)
        lines += ["", f"Sample: {n} rater(s) over {len(fx)} pairs — a small sample; read the percentage as a "
                  "direction, not a measurement."]
    # ---- llm judge
    lines += ["", "## LLM judge", ""]
    lj = results["llm_judge"]
    if lj.get("status") in ("completed", "partial"):
        s = lj["summary"]
        if lj.get("status") == "partial":
            lines += [f"**LLM judge: PARTIAL, not a completed run** — {lj.get('reason', 'no reason recorded')}. "
                      f"The percentages below come only from the pairs that reached a full, "
                      f"non-errored verdict; read them as a fragment, not as the run.", ""]
        lines += [f"Judge model: `{lj['model']}` (pinned by `-m`, not echoed by the Codex CLI — "
                  f"`model_confirmed: {str(lj.get('model_confirmed', False)).lower()}`). Rewrite engine(s): "
                  f"{', '.join('`' + e + '`' for e in lj.get('engine_models', [])) or 'unrecorded'} — cross-model by construction.",
                  "",
                  f"{s['trials_valid']} valid trials over {s['pairs']} pairs ({lj['trials_per_pair']} per pair, "
                  f"{s['trials_failed']} failed call(s), {s['pairs_errored']} pair(s) errored). "
                  f"The percentages below come from the {s['trials_scored']} trial(s) inside the "
                  f"{s['pairs_completed']} pair(s) that reached a present, non-errored verdict; an "
                  f"errored pair's trials are excluded.",
                  "",
                  f"- Applied text preferred in **{s['applied_preferred_trials']}** trial(s), original in "
                  f"**{s['original_preferred_trials']}**, no preference in **{s['equal_trials']}** → applied "
                  f"preferred in **{_pct(s['applied_preference_pct_of_decided'])}** of decided trials.",
                  f"- Pairs where the applied text won the majority of trials: **{s['pairs_majority_applied']} of {s['pairs']}**.",
                  f"- Pairs that BEAT the original on the nine-dimension scaffold criterion: **{s['pairs_beat']} of {s['pairs']}**.",
                  "", "| pair | valid trials | applied | original | no pref | beat |", "|---|---|---|---|---|---|"]
        for p in lj["pairs"]:
            lines.append(f"| `{p.get('dir_name', p['pair_id'])}` | {p['valid_trials']} | {p['applied_preferred_trials']} | "
                         f"{p['original_preferred_trials']} | {p['equal_trials']} | "
                         f"{'yes' if p['verdict']['beat'] else ('errored' if p['verdict']['errored'] else 'no')} |")
    elif lj.get("status") == "failed":
        lines += [f"**LLM judge: failed** — {lj.get('reason', 'no reason recorded')}. No judge percentage exists to report."]
    else:
        lines += [f"**LLM judge: not run** — {lj.get('reason', 'no judge.json was supplied')}."]
    # ---- limitations + reproduce
    lines += ["", "## Limitations", "",
              "- A rater's picks are evidence only against the blind file the operator issued: "
              "`report` refuses `--picks` without `--pairs`, and refuses a pick whose `run_id` or "
              "`token` that file never handed out. Side hashes alone recompute from the committed "
              "fixture bytes, so a self-consistent picks file proves only that its author can run "
              "sha256.",
              f"- Sample size: {len(fx)} pairs. Any percentage here is a direction, not a measurement.",
              "- Selection: every paragraph in the funnel's `sampled` row entered the run (the selection line at the "
              "top says how it was drawn); the audit's tell policy decided authorization, so the preference results "
              "cover only the repaired subset. Abstentions are reported, not hidden.",
              "- The judge model is pinned by the request and not confirmed from the CLI's output.",
              "- The rater-facing page carries neither `source_sha256` nor `pair_id`, so hashing the two texts on "
              "screen no longer recovers a role. A rater with repository access can still de-blind themselves from "
              "the fixture directories, the private blind file, or `judge.json` — those are operator artifacts.",
              "- The rewrite engine and the judge are different models; a human rating is the primary evidence and "
              "the LLM judge is secondary.", "",
              "## Reproduce", "", "```bash",
              "python3 scripts/eval/preference.py build --seed <seed> --out pairs.json",
              "python3 scripts/eval/preference.py human --pairs pairs.json --static rate.html   # or --rater NAME",
              "SLOPSLAP_LIVE=1 python3 scripts/eval/preference.py judge --pairs pairs.json --model gpt-5.6-sol --out judge.json",
              "python3 scripts/eval/preference.py report --pairs pairs.json --picks picks-<rater>.json \\",
              "    --judge judge.json --out results.md --json results.json   # --pairs is REQUIRED with --picks",
              "```", ""]
    return "\n".join(lines)


_JUDGE_STATUSES = ("completed", "partial", "failed", "not_run")


def validate_judge_json(lj, pairs: List[EvalPair], *, name: str = "judge file") -> None:
    """A judge.json becomes evidence only once it RECOMPUTES against these fixtures.

    Report used to accept any object carrying a `status` key. A stale, hand-edited or swapped file
    could therefore hand over arbitrary pair ids, trial counts, model metadata and percentages, and
    the published results document would carry them verbatim. So: a closed status set, every
    `pair_id` present in the current fixture set and named once, every trial's side hashes matching
    that fixture's own bytes under the file's `run_id`, every recorded role recomputed from the side
    it names, and every summary total recomputed from the trials the file itself carries.
    """
    if not isinstance(lj, dict):
        raise PairError(f"{name} is not a JSON object")
    if lj.get("schema_version") != SCHEMA_VERSION:
        raise PairError(f"{name} is not a judge run: schema_version {lj.get('schema_version')!r} "
                        f"is not {SCHEMA_VERSION}")
    status = lj.get("status")
    if status not in _JUDGE_STATUSES:
        raise PairError(f"{name} is not a judge run: status {status!r} is not one of "
                        f"{', '.join(_JUDGE_STATUSES)}")
    if status == "not_run":
        return
    run_id = lj.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PairError(f"{name} has no run_id, so no trial can be bound to a fixture")
    jpairs = lj.get("pairs")
    if not isinstance(jpairs, list) or not jpairs:
        raise PairError(f"{name} carries no pairs")
    trials_per_pair = lj.get("trials_per_pair")
    if not isinstance(trials_per_pair, int) or trials_per_pair < 1:
        raise PairError(f"{name}: trials_per_pair {trials_per_pair!r} is not a positive integer")
    from eval import judge as J  # noqa: PLC0415 (lazy; pure)
    by_id = {p.pair_id: p for p in pairs}
    seen: dict = {}
    tot_app = tot_orig = tot_eq = tot_scored = tot_valid = tot_failed = 0
    completed = errored = majority = beat = 0
    for jp in jpairs:
        if not isinstance(jp, dict):
            raise PairError(f"{name}: a pair entry is not an object")
        pid = jp.get("pair_id")
        fx = by_id.get(pid)
        if fx is None:
            raise PairError(f"{name} names pair_id {pid!r}, which this fixture set does not hold")
        if pid in seen:
            raise PairError(f"{name} reports pair_id {pid} twice")
        seen[pid] = True
        h_orig, h_app = side_hash(run_id, fx.original), side_hash(run_id, fx.applied)
        trials = jp.get("trials")
        if not isinstance(trials, list):
            raise PairError(f"{name}, pair {pid}: trials is not a list")
        p_app = p_orig = p_eq = p_valid = 0
        rebuilt: List = []
        for tr in trials:
            if not isinstance(tr, dict):
                raise PairError(f"{name}, pair {pid}: a trial is not an object")
            a, b = tr.get("a_side_hash"), tr.get("b_side_hash")
            if {a, b} != {h_orig, h_app}:
                raise PairError(f"{name}, pair {pid}: a trial's side hashes are not this fixture's "
                                f"two files under run_id {run_id!r}")
            recomputed = "A" if a == h_app else "B"
            if tr.get("applied_side") != recomputed:
                raise PairError(f"{name}, pair {pid}: recorded applied_side {tr.get('applied_side')!r} "
                                f"is not the {recomputed!r} its own side hashes recompute to")
            if not tr.get("ok"):
                tot_failed += 1
                continue
            p_valid += 1
            side, role = tr.get("preferred_side"), tr.get("preferred_role")
            expect = "equal" if side == "equal" else ("applied" if side == recomputed else "original")
            if role != expect:
                raise PairError(f"{name}, pair {pid}: preferred_role {role!r} is not the {expect!r} "
                                f"that preferred_side {side!r} recomputes to")
            if role == "applied":
                p_app += 1
            elif role == "original":
                p_orig += 1
            else:
                p_eq += 1
            # Rebuild the scaffold trial from the recorded per-dimension ROLES, so the verdict this
            # file claims can be re-derived rather than trusted. `beat` is the scaffold criterion
            # and the results document prints it, so it must recompute like every other number.
            dims = tr.get("dimensions_role")
            if not isinstance(dims, dict) or set(dims) != set(J.DIMENSIONS):
                raise PairError(f"{name}, pair {pid}: trial dimensions_role is not the complete "
                                f"dimension set")
            other = "B" if recomputed == "A" else "A"
            as_sides = {}
            for dim, dim_role in dims.items():
                if dim_role == "applied":
                    as_sides[dim] = recomputed
                elif dim_role == "original":
                    as_sides[dim] = other
                elif dim_role == "equal":
                    as_sides[dim] = "equal"
                else:
                    raise PairError(f"{name}, pair {pid}: dimension {dim} role {dim_role!r} is not "
                                    f"applied, original or equal")
            rebuilt.append(J.trial_from_blind({"dimensions": as_sides}, recomputed))
        if jp.get("valid_trials") != p_valid:
            raise PairError(f"{name}, pair {pid}: valid_trials {jp.get('valid_trials')!r} is not the "
                            f"{p_valid} valid trial(s) it records")
        verdict = jp.get("verdict")
        if not isinstance(verdict, dict):
            raise PairError(f"{name}, pair {pid}: verdict is not an object")
        for field, got, want in (("applied_preferred_trials", jp.get("applied_preferred_trials"), p_app),
                                 ("original_preferred_trials", jp.get("original_preferred_trials"), p_orig),
                                 ("equal_trials", jp.get("equal_trials"), p_eq)):
            if got != want:
                raise PairError(f"{name}, pair {pid}: {field} says {got!r} but its own trials "
                                f"recompute to {want}")
        recomputed_verdict = J.evaluate(rebuilt)
        for field, got, want in (("present", verdict.get("present"), recomputed_verdict.present),
                                 ("errored", verdict.get("errored"), recomputed_verdict.errored),
                                 ("beat", verdict.get("beat"), recomputed_verdict.beat)):
            if bool(got) != bool(want):
                raise PairError(f"{name}, pair {pid}: verdict {field} says {got!r} but its own "
                                f"trials recompute to {want!r}")
        scored_pair = recomputed_verdict.present and not recomputed_verdict.errored \
            and p_valid == trials_per_pair
        want_majority = bool(scored_pair and p_app > p_orig)
        if bool(jp.get("majority_applied")) != want_majority:
            raise PairError(f"{name}, pair {pid}: majority_applied says "
                            f"{jp.get('majority_applied')!r} but recomputes to {want_majority} "
                            f"(an errored or short pair has won nothing)")
        tot_valid += p_valid
        majority += int(want_majority)
        beat += int(recomputed_verdict.beat)
        if scored_pair or (recomputed_verdict.present and not recomputed_verdict.errored):
            completed += 1
            tot_scored += p_valid; tot_app += p_app; tot_orig += p_orig; tot_eq += p_eq
        else:
            errored += 1
    uncovered = sorted(set(by_id) - set(seen))
    if uncovered:
        raise PairError(f"{name} reports {len(seen)} of {len(by_id)} pair(s); a judge run must "
                        f"cover every current fixture, and it omits: {', '.join(uncovered)}")
    summary = lj.get("summary")
    if not isinstance(summary, dict):
        raise PairError(f"{name} carries no summary")
    decided = tot_app + tot_orig
    expected = {
        "pairs": len(jpairs), "pairs_completed": completed, "pairs_errored": errored,
        "trials_valid": tot_valid, "trials_failed": tot_failed, "trials_scored": tot_scored,
        "applied_preferred_trials": tot_app, "original_preferred_trials": tot_orig,
        "equal_trials": tot_eq,
        "applied_preference_pct_of_decided": (round(100.0 * tot_app / decided, 1) if decided else None),
        "pairs_majority_applied": majority, "pairs_beat": beat,
    }
    wrong = {k: (summary.get(k), v) for k, v in expected.items() if summary.get(k) != v}
    if wrong:
        detail = ", ".join(f"{k} says {got!r} but recomputes to {want!r}"
                           for k, (got, want) in sorted(wrong.items()))
        raise PairError(f"{name} summary does not recompute from its own trials: {detail}")


def _bind_picks_to_blind(picks_obj: dict, blind: dict) -> None:
    """A rater's picks are evidence only against the blind file the OPERATOR issued.

    Side hashes recompute from repository-visible fixture bytes under whatever `run_id` a picks
    file names, so a self-consistent file proves only that its author could run sha256. Requiring
    the issued `run_id` and a `token` that file actually handed out is what makes a picks file a
    rating session rather than an assertion — and it is why `report` refuses picks without
    `--pairs`.
    """
    run_id = picks_obj.get("run_id")
    if run_id != blind.get("run_id"):
        raise PairError(f"picks run_id {run_id!r} is not the issued blind file's "
                        f"{blind.get('run_id')!r} — this is not a rating session the operator began")
    by_token = {bp.get("token"): bp for bp in blind.get("pairs") or []}
    for pk in picks_obj.get("picks") or []:
        if not isinstance(pk, dict):
            raise PairError("a pick is not an object")
        token = pk.get("token")
        bp = by_token.get(token)
        if bp is None:
            raise PairError(f"pick token {token!r} is not one the issued blind file handed out")
        if {pk.get("a_side_hash"), pk.get("b_side_hash")} != {bp.get("a_side_hash"),
                                                              bp.get("b_side_hash")}:
            raise PairError(f"pick token {token}: its side hashes are not the pair the blind file "
                            f"issued under that token")


def _cmd_report(args, stdin, stdout) -> int:
    pairs = load_eval_pairs(args.fixtures)
    by_id = {p.pair_id: p for p in pairs}
    blind = None
    if args.picks:
        if not getattr(args, "pairs", None):
            raise PairError("--pairs is required with --picks: a rater's picks bind to the blind "
                            "file the operator issued, and without it any run_id and any side "
                            "hashes recompute from the committed fixture bytes")
        blind = _load_blind(args.pairs)
        validate_blind_json(blind, pairs)
    raters = []
    seen_sessions: dict = {}
    for pf in (args.picks or []):
        with open(pf, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        try:
            _bind_picks_to_blind(obj, blind)
            scored = score_picks(obj, by_id)
        except PairError as err:
            raise PairError(f"{pf}: {err}") from err
        session = (scored["run_id"], scored["rater"])
        if session in seen_sessions:
            raise PairError(f"{pf}: the same rater {scored['rater']!r} and run_id "
                            f"{scored['run_id']!r} already scored from {seen_sessions[session]} — "
                            f"one rating session is one file, or its picks are counted twice")
        seen_sessions[session] = pf
        raters.append(scored)
    if args.judge:
        with open(args.judge, "r", encoding="utf-8") as fh:
            lj = json.load(fh)
        validate_judge_json(lj, pairs, name=f"{args.judge}: judge file")
    else:
        lj = {"status": "not_run", "reason": "no judge.json was supplied to report"}
    abst = None
    if args.abstentions:
        with open(args.abstentions, "r", encoding="utf-8") as fh:
            abst = json.load(fh)
        if not isinstance(abst, dict):
            raise PairError(f"{args.abstentions}: the sampling ledger is not a JSON object")
        validate_ledger(abst, len(pairs), name=args.abstentions)
        abst = dict(abst, file=os.path.relpath(args.abstentions, REPO))
    elif args.judge or args.picks:
        # Step 11 re-run F0: a preference percentage with no funnel has no denominator. The funnel-first
        # layout is not a safeguard if the ledger can simply be left off, so publishing a judge run or
        # human picks REQUIRES the sampling ledger. A fixture-only render (no percentage) still works.
        raise PairError("--abstentions is required with --judge or --picks: a preference percentage "
                        "without the sampling funnel has no denominator")
    fixtures = []
    for p in pairs:
        with open(os.path.join(p.path, "fixture.json"), "r", encoding="utf-8") as fh:
            m = json.load(fh)
        src = m.get("eval_pair", {}).get("source") if isinstance(m.get("eval_pair"), dict) else None
        fixtures.append({"dir_name": p.dir_name, "pair_id": p.pair_id, "genre": p.genre,
                         "engine_model": p.engine_model, "source_sha256": p.source_sha256,
                         "applied_sha256": p.applied_sha256, "source": src if isinstance(src, dict) else None})
    results = {"schema_version": SCHEMA_VERSION, "issue": 102, "created_at": _now(), "fixtures": fixtures,
               "abstentions": abst, "human": {"raters": raters}, "llm_judge": lj}
    md = render_results_md(results)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(md)
    if args.json:
        _write_json(args.json, results)
    print(f"wrote {args.out}" + (f" and {args.json}" if args.json else ""), file=stdout)
    return EXIT_OK


# ---------------------------------------------------------------------------- CLI
def _blind_from_args(args, pairs: Optional[List[EvalPair]] = None) -> dict:
    fixture_pairs = load_eval_pairs(args.fixtures) if pairs is None else pairs
    if getattr(args, "pairs", None):
        blind = _load_blind(args.pairs)
        validate_blind_json(blind, fixture_pairs)
        return blind
    return build_pairs(fixture_pairs, seed=getattr(args, "seed", None))


def _cmd_build(args, stdin, stdout) -> int:
    blind = build_pairs(load_eval_pairs(args.fixtures), seed=args.seed)
    _write_json(args.out, blind)
    print(f"wrote {args.out}: {len(blind['pairs'])} blind pair(s), run_id {blind['run_id']}, seed {blind['seed']}",
          file=stdout)
    return EXIT_OK


def _cmd_human(args, stdin, stdout) -> int:
    blind = _blind_from_args(args)
    if args.static:
        with open(args.static, "w", encoding="utf-8") as fh:
            fh.write(render_static_page(blind))
        print(f"wrote {args.static}: open it in a browser, rate, then Export picks", file=stdout)
        return EXIT_OK
    if not args.rater:
        raise PairError("--rater is required for the terminal rating loop")
    picks = run_human_cli(blind, args.rater, stdin, stdout)
    _write_json(args.out, picks)
    print(f"wrote {args.out}", file=stdout)
    return EXIT_OK


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="preference", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="write the BLIND pairs file from the eval fixtures")
    b.add_argument("--fixtures", default=FIXTURES_DEFAULT)
    b.add_argument("--seed", default=None, help="side-order seed (recorded; random when omitted)")
    b.add_argument("--out", default="pairs.json")

    h = sub.add_parser("human", help="rate the pairs blind: terminal loop, or --static PAGE")
    h.add_argument("--pairs", default=None, help="an existing blind pairs.json (else build internally)")
    h.add_argument("--fixtures", default=FIXTURES_DEFAULT)
    h.add_argument("--seed", default=None)
    h.add_argument("--rater", default=None)
    h.add_argument("--out", default="picks.json")
    h.add_argument("--static", default=None, help="write a self-contained rating page instead of the loop")

    j = sub.add_parser("judge", help="cross-model LLM judge over the blind pairs (needs SLOPSLAP_LIVE=1)")
    j.add_argument("--pairs", default=None, help="an existing blind pairs.json (else build internally)")
    j.add_argument("--fixtures", default=FIXTURES_DEFAULT)
    j.add_argument("--seed", default=None)
    j.add_argument("--model", required=True, help="judge model id, e.g. gpt-5.6-sol (must differ from the engine)")
    j.add_argument("--trials", type=int, default=3)
    j.add_argument("--timeout", type=float, default=180.0)
    j.add_argument("--out", default="judge.json")

    r = sub.add_parser("report", help="score picks + judge.json into the results document")
    r.add_argument("--fixtures", default=FIXTURES_DEFAULT)
    r.add_argument("--pairs", default=None,
                   help="the blind file the picks were rated against; REQUIRED with --picks")
    r.add_argument("--picks", action="append", default=[], help="repeatable; a rater's picks JSON")
    r.add_argument("--judge", default=None, help="the judge.json from `judge`")
    r.add_argument("--abstentions", default=None, help="optional JSON listing sampled paragraphs the engine abstained on")
    r.add_argument("--out", default="results.md")
    r.add_argument("--json", default=None, help="also write the results object here")
    return ap


def main(argv=None, stdin=None, stdout=None, judge_transport=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    ap = _build_argparser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_INVALID
    try:
        if args.cmd == "judge":
            return _cmd_judge(args, stdin, stdout, judge_transport=judge_transport)
        return {"build": _cmd_build, "human": _cmd_human, "report": _cmd_report}[args.cmd](args, stdin, stdout)
    except PairError as err:
        print(f"preference {args.cmd}: refused — {err}", file=sys.stderr)
        return EXIT_INVALID
    except (OSError, ValueError) as err:
        print(f"preference {args.cmd}: failed — {err}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
