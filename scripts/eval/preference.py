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


# ---------------------------------------------------------------------------- judge (SLOPSLAP_LIVE)
def _cross_model_guard(judge_model: str, engine_models: List[str]) -> None:
    """Refuse a judge that is the rewrite engine (the same token rule as invoke._model_confirmed,
    checked in both directions so an alias on either side still matches)."""
    from slopslap_invoke.invoke import models_match  # noqa: PLC0415 (lazy; pure)
    for em in engine_models:
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
    tot_valid = tot_failed = tot_app = tot_orig = tot_eq = 0
    for bp in blind["pairs"]:
        fx = by_id.get(bp["pair_id"])
        if fx is None:
            raise PairError(f"blind file pair {bp['pair_id']} is not in the fixture set (stale pairs.json)")
        recs, jtrials = [], []
        app = orig = eq = 0
        for t in range(trials):
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
        tot_valid += len(jtrials); tot_app += app; tot_orig += orig; tot_eq += eq
        out_pairs.append({"pair_id": fx.pair_id, "dir_name": fx.dir_name, "genre": fx.genre,
                          "trials": recs, "valid_trials": len(jtrials), "verdict": _verdict_json(verdict),
                          "applied_preferred_trials": app, "original_preferred_trials": orig,
                          "equal_trials": eq, "majority_applied": app > orig})
    decided = tot_app + tot_orig
    summary = {
        "pairs": len(out_pairs),
        # a pair is COMPLETED only with a present, non-errored verdict; zero valid trials is errored
        # (judge.evaluate([]) says present=False — "no trials" — which must never read as completed).
        "pairs_completed": sum(1 for p in out_pairs if p["verdict"]["present"] and not p["verdict"]["errored"]),
        "pairs_errored": sum(1 for p in out_pairs if not p["verdict"]["present"] or p["verdict"]["errored"]),
        "trials_valid": tot_valid, "trials_failed": tot_failed,
        "applied_preferred_trials": tot_app, "original_preferred_trials": tot_orig, "equal_trials": tot_eq,
        "applied_preference_pct_of_decided": (round(100.0 * tot_app / decided, 1) if decided else None),
        "pairs_majority_applied": sum(1 for p in out_pairs if p["majority_applied"]),
        "pairs_beat": sum(1 for p in out_pairs if p["verdict"]["beat"]),
    }
    status = "completed" if tot_valid else "failed"
    obj = {"schema_version": SCHEMA_VERSION, "status": status, "model": model,
           "model_confirmed": bool(sink.get("model_confirmed", False)),
           "engine_models": sorted({p.engine_model for p in pairs if p.engine_model}),
           "run_id": run_id, "seed": seed, "trials_per_pair": trials, "timeout_s": timeout_s,
           "created_at": _now(), "pairs": out_pairs, "summary": summary}
    if status == "failed":
        obj["reason"] = (f"every judge call failed (last invocation_status="
                         f"{sink.get('invocation_status', 'unknown')}); nothing to score")
    return obj


def _cmd_judge(args, stdin, stdout, judge_transport=None) -> int:
    from eval.judge import live_judge_available  # noqa: PLC0415
    pairs = load_eval_pairs(args.fixtures)
    _cross_model_guard(args.model, sorted({p.engine_model for p in pairs if p.engine_model}))
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
    pid = pick.get("pair_id")
    if pick.get("source_sha256") != fx.source_sha256:
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


def score_picks(picks_obj: dict, by_id: dict) -> dict:
    """One rater's picks → counts. Every pick is validated (PairError on any drift)."""
    if not isinstance(picks_obj, dict) or picks_obj.get("schema_version") != SCHEMA_VERSION:
        raise PairError("picks file is not schema_version 1")
    run_id = picks_obj.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PairError("picks file has no run_id")
    picks = picks_obj.get("picks")
    if not isinstance(picks, list):
        raise PairError("picks file has no picks list")
    app = orig = eq = 0
    out = []
    for pk in picks:
        if not isinstance(pk, dict):
            raise PairError("a pick is not an object")
        fx = by_id.get(pk.get("pair_id"))
        if fx is None:
            raise PairError(f"pick names unknown pair_id {pk.get('pair_id')!r}")
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
                    "applied_side": applied_side, "role": role})
    decided = app + orig
    return {"rater": str(picks_obj.get("rater") or "rater"), "mode": str(picks_obj.get("mode") or ""),
            "run_id": run_id, "pairs_rated": len(out), "applied_preferred": app,
            "original_preferred": orig, "equal": eq,
            "applied_pct_of_decided": (round(100.0 * app / decided, 1) if decided else None),
            "picks": out}


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:g}%"


def render_results_md(results: dict) -> str:
    fx = results["fixtures"]
    lines = [
        "# Blind paired-preference eval of slopslap's own output — results (#102)", "",
        f"Generated {results['created_at']} by `scripts/eval/preference.py report`. Human raters and the "
        "LLM judge are reported in SEPARATE sections and never combined into one number. This document "
        "reports preference counts and percentages only; it carries no single quality score of any kind.", "",
        "## Method", "",
        "- Each fixture is one real design-doc paragraph (`original.md`) and the output of "
        "`scripts/slopslap_assemble/assemble.py apply` on it (`applied.md`), produced from a committed "
        "edit-script authored by the slopslap engine — never hand-written.",
        "- `build` shows the two as sides A and B in a seeded random order per pair; a rater picks A, B, or "
        "no preference. The pick is recorded with both side hashes (so the side order rides with the pick) "
        "and bound to the pair's `source_sha256`.",
        "- The LLM judge sees the same blind A/B, three trials per pair with a fresh side order each time, and "
        "answers per dimension plus an overall preference; the nine-dimension scaffold in "
        "`scripts/eval/judge.py` scores each trial as applied-vs-original.",
        "- Roles are recovered per fixture from the recorded hashes at report time; a pick that does not "
        "resolve to exactly one original and one applied side is refused, never counted.", "",
        f"## Fixture set — {len(fx)} pairs", "",
        "| pair | source (repo · path · lines) | genre | engine |", "|---|---|---|---|",
    ]
    for f in fx:
        src = f.get("source") or {}
        where = " · ".join(str(src.get(k)) for k in ("repo", "path", "lines") if src.get(k)) or "(see fixture.json provenance)"
        lines.append(f"| `{f['dir_name']}` | {where} | {f['genre']} | `{f['engine_model']}` |")
    ab = results.get("abstentions")
    if ab:
        sampled = ab.get("sampled", len(ab.get("items", [])))
        lines += ["", f"### Sampling — {sampled} paragraphs sampled, {len(fx)} shipped as pairs", ""]
        if ab.get("selection"):
            lines += [str(ab["selection"]), ""]
        bd = ab.get("breakdown") or {}
        if bd:
            lines += ["| disposition | paragraphs | meaning |", "|---|---|---|"]
            meaning = {"shipped": "engine repair authorized, verifier ACCEPT, applied — a pair",
                       "verifier_blocked": "engine proposed a repair; the byte-exact verifier rejected it and no safe alternative existed",
                       "not_authorized": "no strip-recommended tell under the auto-classified genre, so the autonomous path authorized no range",
                       "abstained": "authorized, but the engine found no demonstrated harm",
                       "excluded_circular": "quotes slop examples itself; excluded as circular"}
            for k in sorted(bd, key=lambda k: -bd[k]):
                lines.append(f"| {k} | {bd[k]} | {meaning.get(k, '')} |")
        lines += ["", f"The full per-paragraph ledger (source, disposition, note) is `{ab.get('file', 'the sampling ledger')}`."]
    else:
        lines += ["", "Sampling: not recorded for this run."]
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
    if lj.get("status") == "completed":
        s = lj["summary"]
        lines += [f"Judge model: `{lj['model']}` (pinned by `-m`, not echoed by the Codex CLI — "
                  f"`model_confirmed: {str(lj.get('model_confirmed', False)).lower()}`). Rewrite engine(s): "
                  f"{', '.join('`' + e + '`' for e in lj.get('engine_models', [])) or 'unrecorded'} — cross-model by construction.",
                  "",
                  f"{s['trials_valid']} trials over {s['pairs']} pairs ({lj['trials_per_pair']} per pair, "
                  f"{s['trials_failed']} failed call(s), {s['pairs_errored']} pair(s) errored and excluded from percentages).",
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
              f"- Sample size: {len(fx)} pairs. Any percentage here is a direction, not a measurement.",
              "- Selection: paragraphs were sampled from the owner's public design docs where the measure-only scanner "
              "reported at least one tell, so the set skews toward flagged prose; abstentions are reported, not hidden.",
              "- The judge model is pinned by the request and not confirmed from the CLI's output.",
              "- A rater who inspects the fixture directories, `judge.json`, or hashes the side texts can de-blind "
              "themselves; the page and the blind file show no role in the clear.",
              "- The rewrite engine and the judge are different models; a human rating is the primary evidence and "
              "the LLM judge is secondary.", "",
              "## Reproduce", "", "```bash",
              "python3 scripts/eval/preference.py build --seed <seed> --out pairs.json",
              "python3 scripts/eval/preference.py human --pairs pairs.json --static rate.html   # or --rater NAME",
              "SLOPSLAP_LIVE=1 python3 scripts/eval/preference.py judge --pairs pairs.json --model gpt-5.6-sol --out judge.json",
              "python3 scripts/eval/preference.py report --picks picks-<rater>.json --judge judge.json --out results.md --json results.json",
              "```", ""]
    return "\n".join(lines)


def _cmd_report(args, stdin, stdout) -> int:
    pairs = load_eval_pairs(args.fixtures)
    by_id = {p.pair_id: p for p in pairs}
    raters = []
    for pf in (args.picks or []):
        with open(pf, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        try:
            raters.append(score_picks(obj, by_id))
        except PairError as err:
            raise PairError(f"{pf}: {err}") from err
    if args.judge:
        with open(args.judge, "r", encoding="utf-8") as fh:
            lj = json.load(fh)
        if not isinstance(lj, dict) or "status" not in lj:
            raise PairError(f"{args.judge}: not a judge.json")
    else:
        lj = {"status": "not_run", "reason": "no judge.json was supplied to report"}
    abst = None
    if args.abstentions:
        with open(args.abstentions, "r", encoding="utf-8") as fh:
            abst = json.load(fh)
        abst = dict(abst, file=os.path.relpath(args.abstentions, REPO)) if isinstance(abst, dict) else None
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
