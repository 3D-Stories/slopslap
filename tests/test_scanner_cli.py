"""CLI envelope + exit-code contract (design R3). Runs scan_prose.py as a subprocess."""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = os.path.join(REPO, "scripts", "scan_prose.py")


def _run(args, stdin=None):
    return subprocess.run(
        [sys.executable, SCAN, *args], input=stdin, capture_output=True, text=True, cwd=REPO
    )


def test_format_required_when_absent():
    r = _run([], stdin="hello")
    assert r.returncode == 2
    assert json.loads(r.stdout)["status"] == "format_required"


def test_format_required_when_unknown():
    r = _run(["--format", "html"], stdin="hello")
    assert r.returncode == 2
    assert json.loads(r.stdout)["status"] == "format_required"


def test_format_required_when_given_twice():
    r = _run(["--format", "text", "--format", "markdown"], stdin="hi")
    assert r.returncode == 2


def test_unknown_option_is_error():
    r = _run(["--wat"], stdin="hi")
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert d["status"] == "error" and d["error_kind"] == "bad_arguments"


def test_missing_file_is_error():
    r = _run(["--format", "text", "/no/such/file.md"])
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert d["status"] == "error" and d["error_kind"] == "file_not_found"


def test_non_utf8_is_error(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe not utf8")
    r = _run(["--format", "text", str(bad)])
    assert r.returncode == 1
    assert json.loads(r.stdout)["error_kind"] == "decode_error"


def test_text_ok_envelope():
    r = _run(["--format", "text"], stdin="Hello world. It works fine here.\n")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["status"] == "ok" and d["format"] == "text"
    assert d["extraction_profile"] == "text-v1"
    assert "sentence_length_distribution" in d["metrics"]


def test_markdown_ok_envelope():
    r = _run(["--format", "markdown"], stdin="# Title\n\nBody text here.\n")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["status"] == "ok" and d["format"] == "markdown"
    assert d["capabilities"]["markdown_commonmark"]["available"] is True


def test_every_metric_declares_purpose_candidate_only():
    r = _run(["--format", "text"], stdin="A sentence. Another sentence here. And a third one.\n")
    d = json.loads(r.stdout)
    for name, res in d["metrics"].items():
        assert res["purpose"] == "candidate_selection_only", name
        assert res["confidence"] in ("normal", "medium", "low"), name
