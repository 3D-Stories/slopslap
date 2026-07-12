"""Capability isolation tests — the vendored parser must load from the packaged layout with
site-packages invisible (`python -I -S`), and mismatches must fail closed (design R1/R4/R6/R8).
"""

import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _copy_plugin(dst):
    for sub in ("scripts", "vendor"):
        shutil.copytree(os.path.join(REPO, sub), os.path.join(dst, sub))


def _run_isolated(scan_path, args, cwd):
    # -I -S: isolated + no site => neither PYTHONPATH nor site-packages markdown-it-py is reachable,
    # so ONLY the vendored copy (added by scan_prose from its own path) can satisfy the import.
    return subprocess.run(
        [sys.executable, "-I", "-S", scan_path, *args],
        cwd=cwd, capture_output=True, text=True,
    )


def test_vendor_is_git_tracked_in_source():
    for rel in ("vendor/python/markdown_it/__init__.py", "vendor/python/mdurl/__init__.py"):
        assert os.path.exists(os.path.join(REPO, rel)), f"{rel} missing (packaging must include vendor/)"


def test_packaged_layout_isolated_ok(tmp_path):
    _copy_plugin(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text("# Heading\n\nA paragraph of prose here.\n", encoding="utf-8")
    scan = str(tmp_path / "scripts" / "scan_prose.py")
    r = _run_isolated(scan, ["--format", "markdown", str(doc)], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["status"] == "ok" and d["format"] == "markdown"
    origin = d["capabilities"]["markdown_commonmark"]["modules"]["markdown_it"]["origin"]
    assert origin.startswith(str(tmp_path)), f"parser not loaded from the packaged vendor tree: {origin}"


def test_vendor_absent_is_capability_unavailable(tmp_path):
    _copy_plugin(tmp_path)
    shutil.move(str(tmp_path / "vendor" / "python"), str(tmp_path / "vendor" / "python_gone"))
    doc = tmp_path / "doc.md"
    doc.write_text("# H\n\ntext\n", encoding="utf-8")
    scan = str(tmp_path / "scripts" / "scan_prose.py")
    r = _run_isolated(scan, ["--format", "markdown", str(doc)], cwd=str(tmp_path))
    assert r.returncode == 10
    d = json.loads(r.stdout)
    assert d["status"] == "capability_unavailable" and d["reason"] == "not_importable"
    assert d["metrics"] is None


def test_version_mismatch_is_capability_unavailable(tmp_path):
    _copy_plugin(tmp_path)
    init = tmp_path / "vendor" / "python" / "markdown_it" / "__init__.py"
    init.write_text(
        re.sub(r'__version__\s*=\s*"[^"]+"', '__version__ = "9.9.9"', init.read_text()),
        encoding="utf-8",
    )
    doc = tmp_path / "doc.md"
    doc.write_text("# H\n\ntext\n", encoding="utf-8")
    scan = str(tmp_path / "scripts" / "scan_prose.py")
    r = _run_isolated(scan, ["--format", "markdown", str(doc)], cwd=str(tmp_path))
    assert r.returncode == 10
    d = json.loads(r.stdout)
    assert d["status"] == "capability_unavailable" and d["reason"] == "version_mismatch"


def test_text_path_needs_no_parser(tmp_path):
    # the stdlib text path must work even with the vendor tree gone
    _copy_plugin(tmp_path)
    shutil.rmtree(str(tmp_path / "vendor" / "python"))
    doc = tmp_path / "doc.txt"
    doc.write_text("Plain text. Two sentences.\n", encoding="utf-8")
    scan = str(tmp_path / "scripts" / "scan_prose.py")
    r = _run_isolated(scan, ["--format", "text", str(doc)], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["status"] == "ok"
