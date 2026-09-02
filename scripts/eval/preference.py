#!/usr/bin/env python3
"""Blind paired-preference eval of slopslap's own output (#102).

Each `tests/fixtures/eval/pair-*` directory whose manifest carries an `eval_pair` block holds a
verbatim `original.md` and an `applied.md` that `assemble.py apply` produced from a committed
edit-script. This script shows each pair as a randomized blind A/B and records which side a rater
preferred — a human (terminal loop or a static page) or a cross-model LLM judge — then reports
the two separately. It measures preference; it never emits a single "AI %" or sloppiness score.

Blinding, in one paragraph: the blind file (`build`) carries the two texts as A/B, the pair's
`source_sha256` (the AC2 binding), and a salted hash of the bytes on each side
(`sha256(run_id + ":" + bytes)`) — no role, no fixture name, no applied hash in the clear. A pick
carries the side letter plus both side hashes, so the side order is recorded with the pick and a
later change to the fixture set cannot silently re-map it: `report` recovers roles per fixture
(by `pair_id`, then by matching the side hashes against THAT fixture's two files) and refuses
anything that does not resolve to exactly {original, applied}.

Exit codes: 0 ok · 2 invalid input / refusal (nothing written) · 4 execution failure.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
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
_SIDES = ("A", "B")


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


def load_eval_pairs(fixtures_dir: str) -> List[EvalPair]:
    """Every `pair-*` manifest with an `eval_pair` block, sorted by directory name. Refuses (raises
    PairError) a pair whose manifest shas do not match its bytes, a pair with identical sides (a
    no-op apply is an abstention, never a pair), and two pairs sharing a `pair_id`."""
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
        with open(os.path.join(d, manifest.get("clean_file", "applied.md")), "rb") as fh:
            applied = fh.read()
        src, app = _sha(original), _sha(applied)
        if ep.get("source_sha256") != src or ep.get("applied_sha256") != app:
            raise PairError(f"{name}: eval_pair sha256 fields do not match the file bytes (drift)")
        if src == app:
            raise PairError(f"{name}: identical sides (source_sha256 == applied_sha256) — "
                            f"a no-op apply is an abstention, not a pair")
        pairs.append(EvalPair(dir_name=name, path=d, pair_id=pair_id_for(src, app),
                              source_sha256=src, applied_sha256=app, original=original,
                              applied=applied, engine_model=str(ep.get("engine_model") or ""),
                              genre=str(manifest.get("genre") or "")))
    seen: dict = {}
    for p in pairs:
        if p.pair_id in seen:
            raise PairError(f"duplicate pair_id {p.pair_id}: {seen[p.pair_id]} and {p.dir_name}")
        seen[p.pair_id] = p.dir_name
    return pairs


def build_pairs(pairs: List[EvalPair], seed: Optional[str] = None, run_id: Optional[str] = None) -> dict:
    """The BLIND file. Side order per pair comes from `random.Random(seed)` in the sorted fixture
    order, so one seed gives one order and one set of pair_ids; `run_id` is fresh per build."""
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
            "source_sha256": p.source_sha256,
            "a_text": a.decode("utf-8"),
            "b_text": b.decode("utf-8"),
            "a_side_hash": side_hash(run_id, a),
            "b_side_hash": side_hash(run_id, b),
        })
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "seed": seed,
            "created_at": _now(), "pairs": items}


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
    return {"pair_id": bp["pair_id"], "source_sha256": bp["source_sha256"], "pick": pick,
            "a_side_hash": bp["a_side_hash"], "b_side_hash": bp["b_side_hash"]}


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
<div class="sub">Two versions of one paragraph. Pick the one that reads better for a technical design document. Side order is random per pair. When you finish, export your picks.</div>
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
        picks[p.pair_id] = opt[0];
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
      if (!picks[p.pair_id]) return;
      out.picks.push({ pair_id: p.pair_id, source_sha256: p.source_sha256, pick: picks[p.pair_id],
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
    data = {"schema_version": blind["schema_version"], "run_id": blind["run_id"],
            "pairs": [{k: p[k] for k in ("pair_id", "source_sha256", "a_text", "b_text",
                                           "a_side_hash", "b_side_hash")} for p in blind["pairs"]]}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _PAGE.replace("__DATA__", payload)


# ---------------------------------------------------------------------------- CLI
def _blind_from_args(args) -> dict:
    if getattr(args, "pairs", None):
        return _load_blind(args.pairs)
    return build_pairs(load_eval_pairs(args.fixtures), seed=getattr(args, "seed", None))


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
    return ap


_COMMANDS = {"build": _cmd_build, "human": _cmd_human}


def main(argv=None, stdin=None, stdout=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    ap = _build_argparser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_INVALID
    try:
        return _COMMANDS[args.cmd](args, stdin, stdout)
    except PairError as err:
        print(f"preference {args.cmd}: refused — {err}", file=sys.stderr)
        return EXIT_INVALID
    except (OSError, ValueError) as err:
        print(f"preference {args.cmd}: failed — {err}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
