"""#102 — scripts/eval/preference.py: the blind paired-preference eval (build / human / judge / report).

Every test builds its own tiny fixture set under tmp_path in the committed `pair-*` shape, so the
suite never depends on the real pair-102-* fixtures (those have their own reproducibility guard).
"""
import hashlib
import io
import json
import os

import pytest

from eval import preference as P

ENGINE = "claude-fable-5-1"


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
                          "applied_sha256": _sha(applied), "apply_exit": 0, "semantic_mode": "live"}
    return m


def _write_pair(root, name, original: bytes, applied: bytes, **kw):
    d = root / name
    d.mkdir()
    (d / "original.md").write_bytes(original)
    m = _manifest(original, applied, **kw)
    (d / m["clean_file"]).write_bytes(applied)
    (d / "fixture.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
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
        assert set(p) == {"pair_id", "source_sha256", "a_text", "b_text", "a_side_hash", "b_side_hash"}


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
    rc = P.main(["human", "--pairs", str(pairs_file), "--rater", "chris", "--out", str(picks_file)],
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
    rc = P.main(["human", "--pairs", str(pairs_file), "--rater", "r", "--out", str(picks_file)],
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
    P.main(["human", "--pairs", str(pairs_file), "--rater", "r", "--out", str(tmp_path / "p.json")],
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
    assert P.main(["human", "--pairs", str(pairs_file), "--static", str(page_file)]) == 0
    page = page_file.read_text(encoding="utf-8")
    assert page.lstrip().lower().startswith("<!doctype html")
    # both texts are present as JSON data; the raw `</script>` from the fixture never appears —
    # a fixture byte cannot terminate the data script and inject markup (T3 security surface)
    assert page.count("</script>") == page.count("<script")  # only the page's own tags balance
    assert "<\\/script>" in page
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
    assert P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)], judge_transport=t) == 0
    j = json.loads(out.read_text())
    first, second = j["pairs"]
    assert first["valid_trials"] == 2 and first["verdict"]["errored"] is True
    assert second["valid_trials"] == 3 and second["verdict"]["errored"] is False
    assert j["summary"]["pairs_errored"] == 1 and j["summary"]["trials_failed"] == 1
    assert j["status"] == "completed"


def test_judge_all_failures_is_failed_not_not_run(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    t = _Transport([])  # every call fails
    out = tmp_path / "judge.json"
    assert P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(out)], judge_transport=t) == 4
    j = json.loads(out.read_text())
    assert j["status"] == "failed" and "timeout" in j["reason"]


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
        picks.append({"pair_id": bp["pair_id"], "source_sha256": bp["source_sha256"], "pick": pick,
                      "a_side_hash": bp["a_side_hash"], "b_side_hash": bp["b_side_hash"]})
    return {"schema_version": 1, "run_id": blind["run_id"], "rater": rater, "mode": "cli", "picks": picks}


def _blind(fixtures, seed="s"):
    return P.build_pairs(P.load_eval_pairs(str(fixtures)), seed=seed)


def test_report_scores_human_picks_and_renders_separate_sections(fixtures, tmp_path):
    blind = _blind(fixtures)
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps(_picks_preferring(fixtures, blind, "applied")))
    md, js = tmp_path / "results.md", tmp_path / "results.json"
    rc = P.main(["report", "--fixtures", str(fixtures), "--picks", str(picks), "--out", str(md), "--json", str(js)])
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
    blind = _blind(fixtures)
    p1, p2 = tmp_path / "p1.json", tmp_path / "p2.json"
    p1.write_text(json.dumps(_picks_preferring(fixtures, blind, "original", rater="r1")))
    p2.write_text(json.dumps(_picks_preferring(fixtures, blind, "equal", rater="r2")))
    js = tmp_path / "r.json"
    assert P.main(["report", "--fixtures", str(fixtures), "--picks", str(p1), "--picks", str(p2),
                   "--out", str(tmp_path / "r.md"), "--json", str(js)]) == 0
    raters = {x["rater"]: x for x in json.loads(js.read_text())["human"]["raters"]}
    assert raters["r1"]["original_preferred"] == 2 and raters["r1"]["applied_pct_of_decided"] == 0.0
    assert raters["r2"]["equal"] == 2 and raters["r2"]["applied_pct_of_decided"] is None


def test_report_with_no_picks_says_the_human_mode_has_not_run(fixtures, tmp_path):
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## Human raters" in text and "not yet run" in text and "0 raters" in text


def test_report_refuses_drifted_or_tampered_picks(fixtures, tmp_path, capsys):
    blind = _blind(fixtures)
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
        rc = P.main(["report", "--fixtures", str(fixtures), "--picks", str(f), "--out", str(tmp_path / "r.md")])
        assert rc == 2, name
        assert good["picks"][0]["pair_id"] in capsys.readouterr().err or name == "unknown pair"


def test_report_renders_the_judge_section_from_judge_json(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_LIVE", "1")
    jf = tmp_path / "judge.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "gpt-5.6-sol", "--out", str(jf)],
           judge_transport=_Transport([_judge_reply("A")] * 6))
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    assert P.main(["report", "--fixtures", str(fixtures), "--judge", str(jf), "--out", str(md), "--json", str(js)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## LLM judge" in text and "gpt-5.6-sol" in text and "pinned" in text and "6 trials" in text
    assert json.loads(js.read_text())["llm_judge"]["status"] == "completed"


def test_report_renders_a_not_run_judge_honestly(fixtures, tmp_path, monkeypatch):
    monkeypatch.delenv("SLOPSLAP_LIVE", raising=False)
    jf = tmp_path / "judge.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(jf)], judge_transport=_Transport([]))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--judge", str(jf), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "## LLM judge" in text and "not run" in text and "SLOPSLAP_LIVE" in text
