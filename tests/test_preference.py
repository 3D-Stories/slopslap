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
