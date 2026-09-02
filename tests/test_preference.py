"""#102 — scripts/eval/preference.py: the blind paired-preference eval (build / human / judge / report).

Every test builds its own tiny fixture set under tmp_path in the committed `pair-*` shape, so the
suite never depends on the real pair-102-* fixtures (those have their own reproducibility guard).
"""
import base64
import hashlib
import io
import json
import os
import tempfile

import pytest

from eval import preference as P

ENGINE = "claude-fable-5-1"

# A minimal, internally consistent sampling ledger for the 2-pair `fixtures` set: `report` refuses to
# publish a judge run or human picks without one (Step 11 re-run F0). No explicit funnel, so it binds
# to no particular pair count and serves every fixture set the tests build.
_LEDGER_DIR = tempfile.mkdtemp(prefix="p102-ledger-")
LEDGER = os.path.join(_LEDGER_DIR, "sampled.json")
with open(LEDGER, "w", encoding="utf-8") as _fh:
    json.dump({"schema_version": 1, "sampled": 2, "count": 0, "breakdown": {"shipped": 2}, "items": []}, _fh)



def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _manifest(original: bytes, applied: bytes, *, eval_pair: bool = True, engine: str = ENGINE) -> dict:
    m = {
        "schema_version": 1, "genre": "spec", "control": False, "pair": True,
        "clean_file": "applied.md" if eval_pair else "clean.md",
        "provenance": "test fixture",
        "byte_policy": {"encoding": "utf-8", "trailing_newline": "preserve"},
        "editable_ranges": [], "protected_spans": [], "invariant_regions": [],
        "expected_invariants": [], "allowed_claim_atoms": [],
        "seeded_defects": [{"class": "emptiness", "region": "all", "note": "test"}],
        "control_reason": None,
    }
    if eval_pair:
        m["eval_pair"] = {"schema_version": 1, "engine_model": engine, "source_sha256": _sha(original),
                          "applied_sha256": _sha(applied), "apply_exit": 0, "semantic_mode": "live",
                          "edits_file": "edits.json", "apply_result_file": "apply_result.json",
                          # the loader fails closed on a missing provenance contract (Step 11 re-run F3)
                          "source": {"kind": "owner-supplied", "document": "a test document", "anonymized": True,
                                     "license": "owner-granted"}}
    return m


def _apply_result(original: bytes) -> dict:
    """The minimum RunResult shape `load_eval_pairs` binds to: an ok status, and an audit stage
    whose `source_sha256` is this fixture's own source. It carries no source bytes, like the real
    committed records."""
    return {"status": "ok", "stages": [
        {"stage": "audit", "data": {"source_sha256": _sha(original)}},
        {"stage": "candidate", "data": {}},
        {"stage": "verify", "data": {"decision": "ACCEPT"}},
        {"stage": "apply", "data": {"applied": True}},
    ]}


def _whole_file_edits(original: bytes, applied: bytes) -> list:
    """One edit that replaces the whole original with the applied bytes: the smallest edit-script
    that replays to `applied`, so a test fixture carries the same provenance the loader demands."""
    return [{"start_byte": 0, "end_byte": len(original),
             "replacement_b64": base64.b64encode(applied).decode("ascii")}]


def _write_pair(root, name, original: bytes, applied: bytes, *, edits=None, **kw):
    d = root / name
    d.mkdir()
    (d / "original.md").write_bytes(original)
    m = _manifest(original, applied, **kw)
    (d / m["clean_file"]).write_bytes(applied)
    (d / "fixture.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    ep = m.get("eval_pair")
    if ep and ep.get("edits_file"):
        e = _whole_file_edits(original, applied) if edits is None else edits
        (d / ep["edits_file"]).write_text(json.dumps(e, indent=1), encoding="utf-8")
    if ep and ep.get("apply_result_file"):
        (d / ep["apply_result_file"]).write_text(
            json.dumps(_apply_result(original), indent=1), encoding="utf-8")
    return d


ALPHA_O = b"In today's fast-paced world, the alpha service handles 100 requests per second.\n"
ALPHA_A = b"The alpha service handles 100 requests per second.\n"
BETA_O = b"It is important to note that </script> the beta job runs nightly; it must not skip a day.\n"
BETA_A = b"The beta job runs nightly; it must not skip a day.\n"


@pytest.fixture
def fixtures(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    _write_pair(root, "pair-102-01-qzx", ALPHA_O, ALPHA_A)
    _write_pair(root, "pair-102-02-wvy", BETA_O, BETA_A)
    _write_pair(root, "pair-hand-written", b"slop\n", b"clean\n", eval_pair=False)
    return root


# ---------------------------------------------------------------- loading + build (blind file)
def test_load_eval_pairs_excludes_hand_written_pairs_and_sorts(fixtures):
    pairs = P.load_eval_pairs(str(fixtures))
    assert [p.dir_name for p in pairs] == ["pair-102-01-qzx", "pair-102-02-wvy"]
    a = pairs[0]
    assert a.original == ALPHA_O and a.applied == ALPHA_A
    assert a.source_sha256 == _sha(ALPHA_O) and a.applied_sha256 == _sha(ALPHA_A)
    assert a.pair_id == _sha(f"{_sha(ALPHA_O)}:{_sha(ALPHA_A)}".encode())[:16]
    assert a.engine_model == ENGINE


def test_side_hash_is_the_run_id_salted_sha256_of_the_bytes():
    assert P.side_hash("r1", b"abc") == _sha(b"r1:abc")
    assert P.side_hash("r1", b"abc") != P.side_hash("r2", b"abc")


def test_build_is_deterministic_for_a_seed_except_run_id_and_created_at(fixtures):
    pairs = P.load_eval_pairs(str(fixtures))
    b1 = P.build_pairs(pairs, seed="abc")
    b2 = P.build_pairs(pairs, seed="abc")
    strip = lambda b: [(p["pair_id"], p["a_text"], p["b_text"]) for p in b["pairs"]]
    assert strip(b1) == strip(b2)
    assert b1["run_id"] != b2["run_id"] and len(b1["run_id"]) == 32
    assert b1["seed"] == "abc" and b1["schema_version"] == 1
    # a different seed can change the side order (probabilistic, so assert the mechanism instead)
    assert P.build_pairs(pairs, seed="abc", run_id="fixed")["run_id"] == "fixed"


def test_blind_file_reveals_no_role(fixtures):
    pairs = P.load_eval_pairs(str(fixtures))
    b = P.build_pairs(pairs, seed="s")
    dump = json.dumps(b)
    redacted = json.dumps({**b, "pairs": [{**p, "a_text": "", "b_text": ""} for p in b["pairs"]]})
    for word in ("applied", "original", "slopslap", "pair-102", "qzx", "wvy", "engine"):
        assert word not in redacted, word
    for p, fx in zip(b["pairs"], pairs):
        assert p["pair_id"] == fx.pair_id and p["source_sha256"] == fx.source_sha256
        assert fx.applied_sha256 not in dump
        assert {p["a_text"], p["b_text"]} == {fx.original.decode(), fx.applied.decode()}
        for h in (p["a_side_hash"], p["b_side_hash"]):
            assert h not in (fx.source_sha256, fx.applied_sha256)
        assert p["a_side_hash"] == P.side_hash(b["run_id"], p["a_text"].encode())
        assert p["b_side_hash"] == P.side_hash(b["run_id"], p["b_text"].encode())
        assert set(p) == {"pair_id", "token", "source_sha256", "a_text", "b_text",
                          "a_side_hash", "b_side_hash"}


def test_build_cli_writes_the_blind_file(fixtures, tmp_path):
    out = tmp_path / "pairs.json"
    assert P.main(["build", "--fixtures", str(fixtures), "--seed", "z", "--out", str(out)]) == 0
    b = json.loads(out.read_text())
    assert len(b["pairs"]) == 2 and b["seed"] == "z"


def test_build_refuses_zero_pairs(tmp_path, capsys):
    empty = tmp_path / "none"
    empty.mkdir()
    assert P.main(["build", "--fixtures", str(empty), "--out", str(tmp_path / "p.json")]) == 2
    assert not (tmp_path / "p.json").exists()


def test_build_refuses_identical_sides_naming_the_pair(tmp_path, capsys):
    root = tmp_path / "eval"
    root.mkdir()
    _write_pair(root, "pair-102-09-noop", b"same\n", b"same\n")
    assert P.main(["build", "--fixtures", str(root), "--out", str(tmp_path / "p.json")]) == 2
    assert "pair-102-09-noop" in capsys.readouterr().err


def test_build_refuses_duplicate_pair_ids(tmp_path, capsys):
    root = tmp_path / "eval"
    root.mkdir()
    _write_pair(root, "pair-102-01-x", ALPHA_O, ALPHA_A)
    _write_pair(root, "pair-102-02-y", ALPHA_O, ALPHA_A)
    assert P.main(["build", "--fixtures", str(root), "--out", str(tmp_path / "p.json")]) == 2
    assert "duplicate" in capsys.readouterr().err


# ---------------------------------------------------------------- human mode: CLI + static page
def test_human_cli_records_picks_bound_to_source_and_side_hashes(fixtures, tmp_path):
    pairs_file = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "s", "--out", str(pairs_file)])
    blind = json.loads(pairs_file.read_text())
    picks_file = tmp_path / "picks.json"
    rc = P.main(["human", "--pairs", str(pairs_file), "--fixtures", str(fixtures),
                 "--rater", "chris", "--out", str(picks_file)],
                stdin=io.StringIO("a\n=\n"), stdout=io.StringIO())
    assert rc == 0
    picks = json.loads(picks_file.read_text())
    assert picks["schema_version"] == 1 and picks["rater"] == "chris" and picks["mode"] == "cli"
    assert picks["run_id"] == blind["run_id"] and "seed" not in picks
    assert [p["pick"] for p in picks["picks"]] == ["A", "equal"]
    for pick, bp in zip(picks["picks"], blind["pairs"]):
        assert pick["pair_id"] == bp["pair_id"] and pick["source_sha256"] == bp["source_sha256"]
        assert pick["a_side_hash"] == bp["a_side_hash"] and pick["b_side_hash"] == bp["b_side_hash"]


def test_human_cli_skip_and_quit_record_nothing_for_those_pairs(fixtures, tmp_path):
    pairs_file = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--out", str(pairs_file)])
    picks_file = tmp_path / "picks.json"
    rc = P.main(["human", "--pairs", str(pairs_file), "--fixtures", str(fixtures),
                 "--rater", "r", "--out", str(picks_file)],
                stdin=io.StringIO("s\nq\n"), stdout=io.StringIO())
    assert rc == 0
    assert json.loads(picks_file.read_text())["picks"] == []


def test_human_without_pairs_builds_internally(fixtures, tmp_path):
    picks_file = tmp_path / "picks.json"
    rc = P.main(["human", "--fixtures", str(fixtures), "--rater", "r", "--out", str(picks_file)],
                stdin=io.StringIO("b\nb\n"), stdout=io.StringIO())
    assert rc == 0
    picks = json.loads(picks_file.read_text())
    assert len(picks["run_id"]) == 32 and [p["pick"] for p in picks["picks"]] == ["B", "B"]


def test_human_cli_shows_both_texts_and_nothing_that_names_a_role(fixtures, tmp_path):
    pairs_file = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--out", str(pairs_file)])
    out = io.StringIO()
    P.main(["human", "--pairs", str(pairs_file), "--fixtures", str(fixtures),
            "--rater", "r", "--out", str(tmp_path / "p.json")],
           stdin=io.StringIO("a\na\n"), stdout=out)
    shown = out.getvalue()
    assert ALPHA_O.decode().strip() in shown and ALPHA_A.decode().strip() in shown
    for word in ("applied", "slopslap", "pair-102", "qzx", "wvy"):
        assert word not in shown.lower(), word


def test_static_page_embeds_texts_safely_and_leaks_no_role(fixtures, tmp_path):
    pairs_file = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "seedtokenXYZ987", "--out", str(pairs_file)])
    blind = json.loads(pairs_file.read_text())
    page_file = tmp_path / "rate.html"
    assert P.main(["human", "--pairs", str(pairs_file), "--fixtures", str(fixtures),
                   "--static", str(page_file)]) == 0
    page = page_file.read_text(encoding="utf-8")
    assert page.lstrip().lower().startswith("<!doctype html")
    # both texts are present as JSON data; NO angle bracket from a fixture byte survives, so a
    # fixture cannot terminate the data script and inject markup (T3 security surface)
    assert page.count("</script>") == page.count("<script") == 2  # only the page's own two tags
    assert "\\u003c/script\\u003e" in page  # the fixture's own `</script>` bytes, fully escaped
    assert "alpha service handles 100 requests" in page
    assert blind["run_id"] in page and blind["seed"] not in page.replace(blind["run_id"], "")
    low = page.lower()
    for word in ("applied", "slopslap", "pair-102", "qzx", "wvy", "engine", "original.md"):
        assert word not in low, word
    assert "export" in low and "textcontent" in low  # DOM built with textContent, exported as JSON
    assert "innerhtml" not in low


# ---------------------------------------------------------------- judge mode (SLOPSLAP_LIVE-gated)
from eval import judge as J


def _judge_reply(preferred="A", fill=None):
    return {"preferred": preferred, "dimensions": {d: (fill or preferred) for d in J.DIMENSIONS}, "reason": "r"}


class _Transport:
    """A fake `invoke_judge`: records calls, answers from a script (a dict, or None for a failure)."""
    def __init__(self, answers):
        self.answers = list(answers); self.calls = []
    def __call__(self, request, *, model, schema, timeout_s, status_sink=None):
        self.calls.append({"model": model, "schema": schema, "request": json.loads(request)})
        if status_sink is not None:
            status_sink["model_confirmed"] = False
        ans = self.answers.pop(0) if self.answers else None
        if status_sink is not None:
            status_sink["invocation_status"] = "ok" if ans is not None else "timeout"
        return ans


def test_judge_offline_is_not_run_and_makes_no_call(fixtures, tmp_path, monkeypatch):
    monkeypatch.delenv("SLOPSLAP_LIVE", raising=False)
    t = _Transport([_judge_reply()] * 10)
    out = tmp_path / "judge.json"
    rc = P.main(["judge", "--fixtures", str(fixtures), "--model", "gpt-5.6-sol", "--out", str(out)],
                judge_transport=t)
    assert rc == 0
    j = json.loads(out.read_text())
    assert j["status"] == "not_run" and "SLOPSLAP_LIVE" in j["reason"]
    assert t.calls == []


def test_judge_live_runs_three_blinded_trials_per_pair(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([_judge_reply("A")] * 6)
    out = tmp_path / "judge.json"
    rc = P.main(["judge", "--fixtures", str(fixtures), "--seed", "s", "--model", "gpt-5.6-sol",
                 "--trials", "3", "--out", str(out)], judge_transport=t)
    assert rc == 0 and len(t.calls) == 6
    j = json.loads(out.read_text())
    assert j["status"] == "completed" and j["model"] == "gpt-5.6-sol" and j["model_confirmed"] is False
    assert j["trials_per_pair"] == 3 and len(j["pairs"]) == 2 and j["engine_models"] == [ENGINE]
    pairs = P.load_eval_pairs(str(fixtures))
    for jp, fx in zip(j["pairs"], pairs):
        assert jp["pair_id"] == fx.pair_id and len(jp["trials"]) == 3
        for tr in jp["trials"]:
            assert tr["applied_side"] in ("A", "B") and tr["preferred_side"] == "A"
            assert tr["preferred_role"] == ("applied" if tr["applied_side"] == "A" else "original")
            assert set(tr["dimensions_role"]) == set(J.DIMENSIONS)
            # each trial's request carried exactly the two texts, one per side, in its own order
            assert tr["a_side_hash"] != tr["b_side_hash"]
        assert jp["valid_trials"] == 3 and jp["verdict"]["present"] and not jp["verdict"]["errored"]
        assert jp["applied_preferred_trials"] + jp["original_preferred_trials"] + jp["equal_trials"] == 3
    s = j["summary"]
    assert s["pairs"] == 2 and s["trials_valid"] == 6 and s["trials_failed"] == 0
    assert s["applied_preferred_trials"] == sum(p["applied_preferred_trials"] for p in j["pairs"])
    # the requests were blind: no role words reached the judge
    for c in t.calls:
        assert c["model"] == "gpt-5.6-sol" and c["schema"] == J.JUDGE_SCHEMA
        assert "applied" not in c["request"]["instruction"].lower()


def test_judge_transport_failure_makes_that_pair_errored_never_a_win(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([_judge_reply("A"), None, _judge_reply("A")] + [_judge_reply("A")] * 3)
    out = tmp_path / "judge.json"
    # exit 4, not 0: one pair never reached a verdict, so this run is PARTIAL. It used to report
    # `completed` and exit 0, which let automation accept an evaluation with a pair missing.
    assert P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)], judge_transport=t) == 4
    j = json.loads(out.read_text())
    first, second = j["pairs"]
    assert first["valid_trials"] == 2 and first["verdict"]["errored"] is True
    assert second["valid_trials"] == 3 and second["verdict"]["errored"] is False
    assert j["summary"]["pairs_errored"] == 1 and j["summary"]["trials_failed"] == 1
    assert j["status"] == "partial" and "1 of 2 pair(s)" in j["reason"]


def test_judge_all_failures_is_failed_not_not_run(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([])  # every call fails
    out = tmp_path / "judge.json"
    assert P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)], judge_transport=t) == 4
    j = json.loads(out.read_text())
    assert j["status"] == "failed" and "timeout" in j["reason"]
    # zero valid trials is an ERRORED pair, never a completed one (found live: 9/9 calls failed
    # and the summary said pairs_completed 3)
    assert j["summary"]["pairs_errored"] == 2 and j["summary"]["pairs_completed"] == 0


def test_judge_refuses_a_judge_that_matches_the_engine(fixtures, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([_judge_reply()] * 6)
    for model in ("claude-fable-5-1", "fable"):
        rc = P.main(["judge", "--fixtures", str(fixtures), "--model", model, "--out", str(tmp_path / "j.json")],
                    judge_transport=t)
        assert rc == 2, model
    assert t.calls == [] and "cross-model" in capsys.readouterr().err


def test_judge_accepts_an_existing_blind_file(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    pairs_file = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "q", "--out", str(pairs_file)])
    t = _Transport([_judge_reply("B")] * 6)
    out = tmp_path / "judge.json"
    assert P.main(["judge", "--pairs", str(pairs_file), "--fixtures", str(fixtures), "--model", "m",
                   "--out", str(out)], judge_transport=t) == 0
    j = json.loads(out.read_text())
    assert j["seed"] == "q" and j["run_id"] == json.loads(pairs_file.read_text())["run_id"]


# ---------------------------------------------------------------- report
def _picks_preferring(fixtures, blind, role, rater="chris"):
    by_id = {p.pair_id: p for p in P.load_eval_pairs(str(fixtures))}
    picks = []
    for bp in blind["pairs"]:
        fx = by_id[bp["pair_id"]]
        applied_side = "A" if bp["a_text"].encode() == fx.applied else "B"
        if role == "applied":
            pick = applied_side
        elif role == "original":
            pick = "B" if applied_side == "A" else "A"
        else:
            pick = "equal"
        picks.append({"pair_id": bp["pair_id"], "token": bp["token"],
                      "source_sha256": bp["source_sha256"], "pick": pick,
                      "a_side_hash": bp["a_side_hash"], "b_side_hash": bp["b_side_hash"]})
    return {"schema_version": 1, "run_id": blind["run_id"], "rater": rater, "mode": "cli", "picks": picks}


def _blind(fixtures, seed="s"):
    return P.build_pairs(P.load_eval_pairs(str(fixtures)), seed=seed)


def _blind_file(fixtures, tmp_path, seed="s", name="pairs.json"):
    """Write the blind file `report` now requires alongside `--picks`, and hand back both."""
    pf = tmp_path / name
    P.main(["build", "--fixtures", str(fixtures), "--seed", seed, "--out", str(pf)])
    return pf, json.loads(pf.read_text())


def test_report_scores_human_picks_and_renders_separate_sections(fixtures, tmp_path):
    pf, blind = _blind_file(fixtures, tmp_path)
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps(_picks_preferring(fixtures, blind, "applied")))
    md, js = tmp_path / "results.md", tmp_path / "results.json"
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(picks),
                 "--out", str(md), "--json", str(js)])
    assert rc == 0
    text = md.read_text(encoding="utf-8")
    assert "## Human raters" in text and "## LLM judge" in text
    assert "2 pairs" in text and "100%" in text
    assert "AI %" not in text and "sloppiness score" not in text
    r = json.loads(js.read_text())
    rater = r["human"]["raters"][0]
    assert rater["rater"] == "chris" and rater["pairs_rated"] == 2 and rater["applied_preferred"] == 2
    assert rater["applied_pct_of_decided"] == 100.0
    for pk in rater["picks"]:
        assert pk["applied_side"] in ("A", "B") and pk["role"] == "applied"
    assert r["llm_judge"]["status"] == "not_run"


def test_report_counts_equal_and_original_separately(fixtures, tmp_path):
    pf, blind = _blind_file(fixtures, tmp_path)
    p1, p2 = tmp_path / "p1.json", tmp_path / "p2.json"
    p1.write_text(json.dumps(_picks_preferring(fixtures, blind, "original", rater="r1")))
    p2.write_text(json.dumps(_picks_preferring(fixtures, blind, "equal", rater="r2")))
    js = tmp_path / "r.json"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(p1),
                   "--picks", str(p2), "--out", str(tmp_path / "r.md"), "--json", str(js)]) == 0
    raters = {x["rater"]: x for x in json.loads(js.read_text())["human"]["raters"]}
    assert raters["r1"]["original_preferred"] == 2 and raters["r1"]["applied_pct_of_decided"] == 0.0
    assert raters["r2"]["equal"] == 2 and raters["r2"]["applied_pct_of_decided"] is None


def test_report_with_no_picks_says_the_human_mode_has_not_run(fixtures, tmp_path):
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## Human raters" in text and "not yet run" in text and "0 raters" in text


def test_report_refuses_drifted_or_tampered_picks(fixtures, tmp_path, capsys):
    pf, blind = _blind_file(fixtures, tmp_path)
    good = _picks_preferring(fixtures, blind, "applied")
    cases = {
        "source": lambda p: p["picks"][0].update(source_sha256="0" * 64),
        "unknown pair": lambda p: p["picks"][0].update(pair_id="deadbeefdeadbeef"),
        "side hash": lambda p: p["picks"][0].update(a_side_hash="f" * 64),
        "equal hashes": lambda p: p["picks"][0].update(b_side_hash=p["picks"][0]["a_side_hash"]),
        "run_id": lambda p: p.update(run_id="another-run"),
    }
    for name, mutate in cases.items():
        bad = json.loads(json.dumps(good)); mutate(bad)
        f = tmp_path / f"bad-{name.replace(' ', '_')}.json"; f.write_text(json.dumps(bad))
        rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(f),
                     "--out", str(tmp_path / "r.md")])
        assert rc == 2, name
        # the refusal always names the offending FILE; which identifier it can name depends on how
        # far the pick got — a drifted run_id or side hash is refused at the blind-file binding,
        # before any pair_id is resolved
        assert str(f) in capsys.readouterr().err, name


def test_report_renders_the_judge_section_from_judge_json(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf = tmp_path / "judge.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "gpt-5.6-sol", "--out", str(jf)],
           judge_transport=_Transport([_judge_reply("A")] * 6))
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf), "--out", str(md), "--json", str(js)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## LLM judge" in text and "gpt-5.6-sol" in text and "pinned" in text
    assert "6 valid trials" in text and "excluded" in text
    assert json.loads(js.read_text())["llm_judge"]["status"] == "completed"


def test_report_renders_a_not_run_judge_honestly(fixtures, tmp_path, monkeypatch):
    monkeypatch.delenv("SLOPSLAP_LIVE", raising=False)
    jf = tmp_path / "judge.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(jf)], judge_transport=_Transport([]))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## LLM judge" in text and "not run" in text and "SLOPSLAP_LIVE" in text


def test_report_renders_the_sampling_breakdown(fixtures, tmp_path):
    ledger = tmp_path / "sampled.json"
    ledger.write_text(json.dumps({"schema_version": 1, "sampled": 7, "count": 5, "selection": "public docs only",
                                  "breakdown": {"shipped": 2, "verifier_blocked": 3, "not_authorized": 2},
                                  "items": []}))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(ledger), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "7 paragraphs sampled, 2 shipped as pairs" in text and "public docs only" in text
    assert "| verifier_blocked | 3 |" in text and "| not_authorized | 2 |" in text
    assert "AI %" not in text and "sloppiness score" not in text
    # an explicit status note renders under its own heading when the ledger carries one
    ledger.write_text(json.dumps({"schema_version": 1, "sampled": 7, "count": 5, "breakdown": {"shipped": 2, "not_authorized": 5},
                                  "status_note": "AC4 asked for 5; this run ships 2.", "items": []}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(ledger), "--out", str(md)]) == 0
    assert "### Status against the issue" in md.read_text(encoding="utf-8") and "this run ships 2" in md.read_text(encoding="utf-8")


# ------------------------------------------- Step 8a review round (#102): the eight confirmed Highs
# Each test below pins one finding the cross-model reviewer (gpt-5.6-sol) and the inline pass raised
# against 63d9897, verified against the code before it was written.

# --- AC2 blinding: the rater-facing page must hand over nothing that recovers a role -------------
def test_static_page_carries_no_source_sha256_and_no_pair_id(fixtures):
    blind = _blind(fixtures)
    page = P.render_static_page(blind)
    for bp in blind["pairs"]:
        assert bp["source_sha256"] not in page, "hashing the two texts against this de-blinds the pair"
        assert bp["pair_id"] not in page, "pair_id is sha256(source:applied) — the order IS the tell"
        assert bp["token"] in page


def test_page_token_is_not_derivable_from_what_the_rater_can_see(fixtures):
    blind = _blind(fixtures)
    run_id = blind["run_id"]
    for bp in blind["pairs"]:
        ha = _sha(bp["a_text"].encode("utf-8"))
        hb = _sha(bp["b_text"].encode("utf-8"))
        for x, y in ((ha, hb), (hb, ha)):
            cand = hashlib.sha256(f"{x}:{y}".encode("utf-8")).hexdigest()[:16]
            assert bp["token"] != cand
            assert bp["token"] != hashlib.sha256(f"{run_id}:{cand}".encode("utf-8")).hexdigest()[:16]


def test_one_seed_repeats_the_side_order_but_never_a_token(fixtures):
    pairs = P.load_eval_pairs(str(fixtures))
    a, b = P.build_pairs(pairs, seed="s"), P.build_pairs(pairs, seed="s")
    assert [p["a_text"] for p in a["pairs"]] == [p["a_text"] for p in b["pairs"]]
    assert {p["token"] for p in a["pairs"]}.isdisjoint({p["token"] for p in b["pairs"]})


def test_report_scores_page_picks_carrying_only_a_token_and_side_hashes(fixtures, tmp_path):
    pf, blind = _blind_file(fixtures, tmp_path)
    by_id = {p.pair_id: p for p in P.load_eval_pairs(str(fixtures))}
    picks = []
    for bp in blind["pairs"]:
        fx = by_id[bp["pair_id"]]
        picks.append({"token": bp["token"], "pick": "A" if bp["a_text"].encode("utf-8") == fx.applied else "B",
                      "a_side_hash": bp["a_side_hash"], "b_side_hash": bp["b_side_hash"]})
    picks_file = tmp_path / "picks.json"
    picks_file.write_text(json.dumps({"schema_version": 1, "run_id": blind["run_id"], "rater": "web",
                                      "mode": "static", "picks": picks}))
    js = tmp_path / "r.json"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf),
                   "--picks", str(picks_file),
                   "--out", str(tmp_path / "r.md"), "--json", str(js)]) == 0
    rater = json.loads(js.read_text())["human"]["raters"][0]
    assert rater["pairs_rated"] == 2 and rater["applied_preferred"] == 2
    # AC2's binding is not lost: report recovers it from the fixture bytes and publishes it per pick
    for pk in rater["picks"]:
        assert pk["source_sha256"] == by_id[pk["pair_id"]].source_sha256


# --- one pick per pair, one picks file per rater and run -----------------------------------------
def test_report_refuses_the_same_pair_picked_twice(fixtures, tmp_path, capsys):
    pf, blind = _blind_file(fixtures, tmp_path)
    good = _picks_preferring(fixtures, blind, "applied")
    dup = json.loads(json.dumps(good))
    dup["picks"].append(json.loads(json.dumps(dup["picks"][0])))
    f = tmp_path / "dup.json"
    f.write_text(json.dumps(dup))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(f),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "twice" in capsys.readouterr().err


def test_report_refuses_two_picks_files_from_one_rater_and_run(fixtures, tmp_path, capsys):
    pf, blind = _blind_file(fixtures, tmp_path)
    body = json.dumps(_picks_preferring(fixtures, blind, "applied", rater="chris"))
    p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
    p1.write_text(body)
    p2.write_text(body)
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(p1),
                 "--picks", str(p2), "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "same rater" in capsys.readouterr().err


# --- a partial judge run is never a completed one ------------------------------------------------
def test_a_partial_judge_run_is_partial_and_exits_failed(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([_judge_reply("A")])  # exactly one valid answer; every later call fails
    out = tmp_path / "judge.json"
    rc = P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)], judge_transport=t)
    j = json.loads(out.read_text())
    assert j["status"] == "partial" and rc == 4
    assert j["summary"]["pairs_completed"] == 0 and j["summary"]["pairs_errored"] == 2


def test_errored_pair_trials_never_enter_the_preference_percentage(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    # pair 1 gets two valid trials (errored: fewer than three); pair 2 gets a full three
    t = _Transport([_judge_reply("A"), None, _judge_reply("A"),
                    _judge_reply("B"), _judge_reply("B"), _judge_reply("B")])
    out = tmp_path / "judge.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)], judge_transport=t)
    j = json.loads(out.read_text())
    first = j["pairs"][0]
    assert first["verdict"]["errored"] is True and first["valid_trials"] == 2
    s = j["summary"]
    assert s["trials_valid"] == 5, "raw valid calls keep their meaning"
    assert s["trials_scored"] == 3, "only a non-errored pair's trials are scored"
    assert s["applied_preferred_trials"] + s["original_preferred_trials"] + s["equal_trials"] == 3
    assert s["pairs_errored"] == 1 and s["pairs_completed"] == 1


# --- a fixture is engine output only when the committed edit script replays to it ----------------
def test_load_eval_pairs_refuses_a_recorded_apply_that_did_not_exit_zero(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    d = _write_pair(root, "pair-nonzero", ALPHA_O, ALPHA_A)
    m = json.loads((d / "fixture.json").read_text(encoding="utf-8"))
    m["eval_pair"]["apply_exit"] = 1
    (d / "fixture.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(P.PairError, match="apply_exit"):
        P.load_eval_pairs(str(root))


def test_load_eval_pairs_refuses_an_applied_side_the_edit_script_does_not_reproduce(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    _write_pair(root, "pair-handwritten", ALPHA_O, b"A paragraph no edit script produced.\n",
                edits=_whole_file_edits(ALPHA_O, ALPHA_A))
    with pytest.raises(P.PairError, match="edit script"):
        P.load_eval_pairs(str(root))


def test_load_eval_pairs_refuses_an_eval_pair_with_no_edit_script(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    d = _write_pair(root, "pair-noedits", ALPHA_O, ALPHA_A)
    os.remove(str(d / "edits.json"))
    with pytest.raises(P.PairError, match="edits"):
        P.load_eval_pairs(str(root))


# --- the cross-model guard fails closed on an unknown engine ------------------------------------
def test_load_eval_pairs_refuses_a_missing_engine_model(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    _write_pair(root, "pair-noengine", ALPHA_O, ALPHA_A, engine="")
    with pytest.raises(P.PairError, match="engine_model"):
        P.load_eval_pairs(str(root))


# --- report never publishes a judge object it did not recompute ----------------------------------
def test_report_refuses_an_object_that_is_merely_shaped_like_a_judge_run(fixtures, tmp_path, capsys):
    f = tmp_path / "fake.json"
    f.write_text(json.dumps({"status": "completed", "pairs": [{"pair_id": "deadbeefdeadbeef"}],
                             "summary": {"applied_preference_pct_of_decided": 99.9}}))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(f), "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "judge" in capsys.readouterr().err.lower()


def _live_judge_json(fixtures, tmp_path, name="judge.json"):
    jf = tmp_path / name
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(jf)],
           judge_transport=_Transport([_judge_reply("A")] * 6))
    return jf


def test_report_refuses_a_judge_run_naming_a_pair_the_fixture_set_does_not_hold(fixtures, tmp_path,
                                                                                monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf = _live_judge_json(fixtures, tmp_path)
    j = json.loads(jf.read_text())
    j["pairs"][0]["pair_id"] = "0" * 16
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf), "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "pair_id" in capsys.readouterr().err


def test_report_refuses_a_judge_summary_that_does_not_recompute(fixtures, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf = _live_judge_json(fixtures, tmp_path)
    j = json.loads(jf.read_text())
    j["summary"]["applied_preferred_trials"] = 99
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf), "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "summary" in capsys.readouterr().err


def test_report_refuses_a_trial_whose_applied_side_does_not_recompute(fixtures, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf = _live_judge_json(fixtures, tmp_path)
    j = json.loads(jf.read_text())
    tr = j["pairs"][0]["trials"][0]
    tr["applied_side"] = "B" if tr["applied_side"] == "A" else "A"
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf), "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "applied_side" in capsys.readouterr().err


# ------------------------------- Step 11 review round (#102): the confirmed findings
# The cross-model pass (gpt-5.6-sol, architecture + security) and the adversarial diff-review layer
# raised 9 distinct findings over the whole diff. Two were REFUTED by direct measurement and are
# pinned here anyway so they stay refuted; the rest are fixed below.

def _judge_run(fixtures, tmp_path, answers, name="judge.json"):
    out = tmp_path / name
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)],
           judge_transport=_Transport(answers))
    return out, json.loads(out.read_text())


class _PreferApplied:
    """Always prefers the APPLIED side, whichever letter it sits on, then fails every later call."""
    def __init__(self, ok_calls):
        self.left = ok_calls
    def __call__(self, request, *, model, schema, timeout_s, status_sink=None):
        if status_sink is not None:
            status_sink["model_confirmed"] = False
        req = json.loads(request)
        if self.left <= 0:
            if status_sink is not None:
                status_sink["invocation_status"] = "timeout"
            return None
        self.left -= 1
        applied = {ALPHA_A.decode(), BETA_A.decode()}
        side = "A" if req["text_a"] in applied else "B"
        if status_sink is not None:
            status_sink["invocation_status"] = "ok"
        return _judge_reply(side)


# --- a blind file must cover the whole current fixture set --------------------------------------
def test_judge_refuses_a_blind_file_that_drops_a_fixture(fixtures, tmp_path, monkeypatch, capsys):
    """Dropping an unfavorable pair from pairs.json used to yield `completed` over the subset."""
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    pf = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "s", "--out", str(pf)])
    blind = json.loads(pf.read_text())
    sf = tmp_path / "pairs-subset.json"
    sf.write_text(json.dumps(dict(blind, pairs=blind["pairs"][:1])))
    rc = P.main(["judge", "--pairs", str(sf), "--fixtures", str(fixtures), "--model", "m",
                 "--out", str(tmp_path / "j.json")], judge_transport=_Transport([_judge_reply()] * 6))
    assert rc == 2 and "fixture set" in capsys.readouterr().err


def test_judge_refuses_a_blind_file_whose_text_is_not_the_fixture(fixtures, tmp_path, monkeypatch,
                                                                  capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    pf = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "s", "--out", str(pf)])
    blind = json.loads(pf.read_text())
    blind["pairs"][0]["a_text"] = "a paragraph no fixture holds\n"
    sf = tmp_path / "pairs-bad.json"
    sf.write_text(json.dumps(blind))
    rc = P.main(["judge", "--pairs", str(sf), "--fixtures", str(fixtures), "--model", "m",
                 "--out", str(tmp_path / "j.json")], judge_transport=_Transport([_judge_reply()] * 6))
    assert rc == 2 and "side" in capsys.readouterr().err


def test_report_refuses_a_judge_run_that_does_not_cover_every_fixture(fixtures, tmp_path,
                                                                      monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf, j = _judge_run(fixtures, tmp_path, [_judge_reply("A")] * 6)
    j["pairs"] = j["pairs"][:1]
    p = j["pairs"][0]
    d = p["applied_preferred_trials"] + p["original_preferred_trials"]
    # every recomputable total is made to agree with the truncated list, so ONLY coverage is wrong
    j["summary"].update(
        pairs=1, pairs_completed=1, pairs_errored=0, trials_valid=3, trials_scored=3,
        trials_failed=0, applied_preferred_trials=p["applied_preferred_trials"],
        original_preferred_trials=p["original_preferred_trials"], equal_trials=p["equal_trials"],
        pairs_majority_applied=int(p["majority_applied"]), pairs_beat=int(p["verdict"]["beat"]),
        applied_preference_pct_of_decided=(
            round(100.0 * p["applied_preferred_trials"] / d, 1) if d else None))
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "every" in capsys.readouterr().err


# --- an errored pair is never a majority-applied win --------------------------------------------
def test_an_errored_pair_is_never_counted_as_a_majority_applied_win(fixtures, tmp_path, monkeypatch):
    """The results doc used to print `1 of 1` majority wins for a pair with zero scored trials."""
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    out = tmp_path / "j.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)],
           judge_transport=_PreferApplied(2))
    j = json.loads(out.read_text())
    first = j["pairs"][0]
    assert first["verdict"]["errored"] is True and first["applied_preferred_trials"] == 2
    assert first["majority_applied"] is False, "an errored pair has not won anything"
    assert j["summary"]["pairs_majority_applied"] == 0


# --- every published judge number recomputes ----------------------------------------------------
@pytest.mark.parametrize("field", ["pairs_majority_applied", "pairs_beat"])
def test_report_refuses_a_tampered_pair_level_summary_counter(fixtures, tmp_path, monkeypatch,
                                                              capsys, field):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf, j = _judge_run(fixtures, tmp_path, [_judge_reply("A")] * 6)
    j["summary"][field] = 99
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and field in capsys.readouterr().err


def test_report_refuses_a_tampered_per_pair_counter(fixtures, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf, j = _judge_run(fixtures, tmp_path, [_judge_reply("A")] * 6)
    j["pairs"][0]["applied_preferred_trials"] = 99
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "applied_preferred_trials" in capsys.readouterr().err


def test_report_refuses_a_fabricated_beat_verdict(fixtures, tmp_path, monkeypatch, capsys):
    """`beat` is the scaffold criterion, so it must be re-derived from the recorded dimensions."""
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf, j = _judge_run(fixtures, tmp_path, [_judge_reply("A", fill="equal")] * 6)
    assert j["pairs"][0]["verdict"]["beat"] is False, "these answers must not already beat"
    j["pairs"][0]["verdict"]["beat"] = True
    j["summary"]["pairs_beat"] = 1
    jf.write_text(json.dumps(j))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--judge", str(jf),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "beat" in capsys.readouterr().err


# --- a human pick is bound to the operator's own blind file -------------------------------------
def test_report_requires_the_blind_file_alongside_picks(fixtures, tmp_path, capsys):
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps(_picks_preferring(fixtures, _blind(fixtures), "applied")))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--picks", str(picks),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "--pairs" in capsys.readouterr().err


def test_report_refuses_picks_from_a_run_id_the_operator_never_issued(fixtures, tmp_path, capsys):
    """A picks file used to carry ANY run_id: its hashes recompute from repo-visible fixture bytes."""
    pf = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "s", "--out", str(pf)])
    forged = P.build_pairs(P.load_eval_pairs(str(fixtures)), seed="s")  # a DIFFERENT run_id
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps(_picks_preferring(fixtures, forged, "applied", rater="attacker")))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(picks),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "run_id" in capsys.readouterr().err


def test_report_refuses_a_pick_whose_token_the_blind_file_does_not_hold(fixtures, tmp_path, capsys):
    pf = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "s", "--out", str(pf)])
    obj = _picks_preferring(fixtures, json.loads(pf.read_text()), "applied")
    obj["picks"][0]["token"] = "0" * 16
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps(obj))
    rc = P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(picks),
                 "--out", str(tmp_path / "r.md")])
    assert rc == 2 and "token" in capsys.readouterr().err


def test_report_scores_picks_that_match_the_issued_blind_file(fixtures, tmp_path):
    pf = tmp_path / "pairs.json"
    P.main(["build", "--fixtures", str(fixtures), "--seed", "s", "--out", str(pf)])
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps(_picks_preferring(fixtures, json.loads(pf.read_text()), "applied")))
    js = tmp_path / "r.json"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", LEDGER, "--pairs", str(pf), "--picks", str(picks),
                   "--out", str(tmp_path / "r.md"), "--json", str(js)]) == 0
    rater = json.loads(js.read_text())["human"]["raters"][0]
    assert rater["pairs_rated"] == 2 and rater["applied_preferred"] == 2


# --- a fixture's recorded apply must bind to its own source -------------------------------------
def test_load_eval_pairs_refuses_an_apply_result_bound_to_another_source(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    d = _write_pair(root, "pair-drifted", ALPHA_O, ALPHA_A)
    res = json.loads((d / "apply_result.json").read_text(encoding="utf-8"))
    for stage in res["stages"]:
        if stage["stage"] == "audit":
            stage["data"]["source_sha256"] = "0" * 64
    (d / "apply_result.json").write_text(json.dumps(res), encoding="utf-8")
    with pytest.raises(P.PairError, match="apply_result"):
        P.load_eval_pairs(str(root))


def test_load_eval_pairs_refuses_an_apply_result_that_did_not_succeed(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    d = _write_pair(root, "pair-notok", ALPHA_O, ALPHA_A)
    res = json.loads((d / "apply_result.json").read_text(encoding="utf-8"))
    res["status"] = "refused"
    (d / "apply_result.json").write_text(json.dumps(res), encoding="utf-8")
    with pytest.raises(P.PairError, match="apply_result"):
        P.load_eval_pairs(str(root))


# --- the page carries no literal angle bracket from fixture data (a REFUTED finding, pinned) ----
def test_page_embeds_no_literal_angle_bracket_from_fixture_data(tmp_path):
    """A reviewer read the `</` escape as lowercase-only. It is not — `</` carries no letter — and
    every case variant measured as escaped. This pins the STRONGER invariant anyway: the embedded
    JSON holds no literal `<` at all, so the guarantee no longer rests on HTML raw-text rules."""
    root = tmp_path / "eval"
    root.mkdir()
    nasty = (b"</SCRIPT><script>window.x=1</script> </ScRiPt><img src=x onerror=alert(1)> "
             b"</script > and a lone < plus > and &.\n")
    _write_pair(root, "pair-nasty", nasty, b"Clean.\n")
    page = P.render_static_page(P.build_pairs(P.load_eval_pairs(str(root)), seed="s"))
    marker = '<script id="data" type="application/json">'
    start = page.index(marker) + len(marker)
    payload = page[start:page.index("</script>", start)]
    assert "<" not in payload and ">" not in payload
    for variant in ("</SCRIPT>", "</ScRiPt>", "</script>", "</script "):
        assert variant not in payload, variant
    assert json.loads(payload)["pairs"], "the payload still parses as JSON"
    # exactly the page's OWN two script tags survive: the fixture's `<script>` bytes are escaped
    assert page.count("<script") == 2 and page.lower().count("</script>") == 2


# ------------------------------- inline Medium and Low findings from the Step 11 round
# Each is a message-quality defect on a refusal that already behaved correctly. Owner asked for
# them, so each one gets the same treatment as any other finding: a failing test first.

def test_judge_refuses_a_trial_count_below_one(fixtures, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([_judge_reply()] * 6)
    rc = P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--trials", "0",
                 "--out", str(tmp_path / "j.json")], judge_transport=t)
    assert rc == 2 and "trials" in capsys.readouterr().err
    assert t.calls == [], "a refusal must not spend a judge call"


def test_a_judge_run_that_attempted_no_call_does_not_claim_calls_failed(fixtures, tmp_path,
                                                                        monkeypatch):
    """`trials=0` reported 'every judge call failed' although zero calls were made, which sends an
    operator hunting a transport fault that does not exist. The CLI now refuses below 1, so this
    covers the library path a caller can still reach directly."""
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    pairs = P.load_eval_pairs(str(fixtures))
    blind = P.build_pairs(pairs, seed="s")
    obj = P.run_judge(pairs, blind, model="m", trials=0, timeout_s=1.0,
                      transport=_Transport([_judge_reply()] * 6))
    assert obj["status"] == "failed"
    assert "no judge call was attempted" in obj["reason"]
    assert "every judge call failed" not in obj["reason"]


def test_a_pick_with_no_identifier_says_so(fixtures, tmp_path):
    by_id = {p.pair_id: p for p in P.load_eval_pairs(str(fixtures))}
    blind = _blind(fixtures)
    with pytest.raises(P.PairError, match="carries neither"):
        P.score_picks({"schema_version": 1, "run_id": blind["run_id"], "rater": "r",
                       "picks": [{"pick": "A"}]}, by_id)


def test_a_pick_with_equal_side_hashes_says_so(fixtures, tmp_path):
    """It used to report 'side hashes match no fixture', which names the wrong cause."""
    by_id = {p.pair_id: p for p in P.load_eval_pairs(str(fixtures))}
    blind = _blind(fixtures)
    h = blind["pairs"][0]["a_side_hash"]
    with pytest.raises(P.PairError, match="equal"):
        P.score_picks({"schema_version": 1, "run_id": blind["run_id"], "rater": "r",
                       "picks": [{"token": blind["pairs"][0]["token"], "pick": "A",
                                  "a_side_hash": h, "b_side_hash": h}]}, by_id)


def test_a_malformed_edit_script_is_named_as_a_file_problem(tmp_path):
    """The refusal was right but its detail was a bare Python message, e.g. 'string indices must be
    integers'. It now names the file and the error class before that detail."""
    root = tmp_path / "eval"
    root.mkdir()
    _write_pair(root, "pair-badedits", ALPHA_O, ALPHA_A, edits={"not": "a list"})
    with pytest.raises(P.PairError, match=r"edits\.json is not a usable edit script \(TypeError"):
        P.load_eval_pairs(str(root))
