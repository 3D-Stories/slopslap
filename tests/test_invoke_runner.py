"""Bounded fresh-context claude -p runner + invoke_semantic API (#26, Task 3).

Every test is HERMETIC and FAST: the "CLI" is a tiny python/sh script written to tmp and
made executable — the real ``claude`` binary is NEVER invoked. We assert the runner's
bounded-execution contract (byte cap, process-group timeout kill, no orphans), the exact
pinned lockdown argv, per-failure diagnostic codes, and that invoke_semantic ALWAYS returns
exactly {verdict, concerns} with an ambiguous default on every failure status.
"""

import json
import logging
import os
import signal
import stat
import time

import pytest

from slopslap_invoke import contract, invoke
from slopslap_invoke.invoke import InvocationResult, invoke_semantic
from slopslap_verification.editscript import sha256_hex
from slopslap_verification.ledger import Ledger, LedgerEntry

MODEL = "claude-test-model"


def _canon():
    orig = b"the client MUST wait 200 ms here.\n"
    led = Ledger(sha256_hex(orig), entries=[
        LedgerEntry("e0", "number_or_quantity", 21, 27, sha256_hex(orig[21:27]),
                    {"200|ms": 1}, "lexically_exact", 950)])
    return orig, led.canonical_obj()


def _write_exec(tmp_path, name, source):
    p = tmp_path / name
    p.write_text(source)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


def _py_cli(tmp_path, body, name="fake_claude.py"):
    return _write_exec(tmp_path, name, "#!/usr/bin/env python3\n" + body)


# a fake that emits a valid success envelope whose result is `result_body` (a python literal
# that json-dumps to the assistant text). It echoes the requested --model unless model_override.
def _success_cli(tmp_path, result_obj, model_override=None, name="ok_cli.py"):
    body = (
        "import sys, json\n"
        "argv = sys.argv[1:]\n"
        "model = argv[argv.index('--model')+1] if '--model' in argv else ''\n"
        f"override = {model_override!r}\n"
        f"result = {json.dumps(json.dumps(result_obj))}\n"
        "env = {'type': 'result', 'model': override if override is not None else model, "
        "'result': result, 'argv': argv}\n"
        "sys.stdout.write(json.dumps(env))\n"
    )
    return _py_cli(tmp_path, body, name=name)


# ---- success / envelope parsing ----
def test_success_envelope_ok(tmp_path):
    _orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable=exe)
    assert res.status == "ok"
    assert res.envelope["result"]
    assert res.diagnostic_code is None


def test_invalid_json_envelope_is_parse_error(tmp_path):
    exe = _py_cli(tmp_path, "import sys\nsys.stdout.write('NOT JSON <<<')\n")
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable=exe)
    assert res.status == "parse_error"
    assert res.diagnostic_code == "semantic_invalid_response"


def test_nonzero_exit(tmp_path):
    exe = _py_cli(tmp_path, "import sys\nsys.stderr.write('boom failure detail')\nsys.exit(7)\n")
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable=exe)
    assert res.status == "nonzero_exit"
    assert "boom" in res.stderr_tail
    assert res.diagnostic_code == "semantic_transport_error"


def test_model_mismatch(tmp_path):
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []}, model_override="some-other-model")
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable=exe)
    assert res.status == "model_mismatch"
    assert res.diagnostic_code == "semantic_invalid_response"


def test_cli_missing():
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable="/nonexistent/claude-xyz")
    assert res.status == "cli_missing"
    assert res.diagnostic_code == "semantic_transport_error"


def test_empty_model_raises(tmp_path):
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    with pytest.raises(ValueError):
        invoke._run_claude("req", model="", timeout_s=5.0, executable=exe)


# ---- bounded execution: byte cap ----
def test_oversized_stdout_mid_run_is_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(invoke, "_MAX_STDOUT_BYTES", 1024)
    # write past the cap, then sleep long; the cap must kill the group and return parse_error
    exe = _py_cli(tmp_path, "import sys, time\nsys.stdout.write('x'*8192)\nsys.stdout.flush()\ntime.sleep(30)\n")
    start = time.monotonic()
    res = invoke._run_claude("req", model=MODEL, timeout_s=20.0, executable=exe)
    elapsed = time.monotonic() - start
    assert res.status == "parse_error"
    assert res.diagnostic_code == "semantic_invalid_response"
    assert elapsed < 10.0  # killed on cap, did NOT wait out the 30s sleep or the 20s timeout


# ---- bounded execution: timeout + process-group kill + no orphans ----
def test_timeout_kills_process_group_no_orphan(tmp_path):
    # the fake spawns a descendant that records ITS pid to the path read from stdin, then both
    # sleep for a long time; a process-group kill must reap the descendant too (no orphan).
    body = (
        "import sys, os, subprocess, time\n"
        "pidfile = sys.stdin.read().strip()\n"
        "child = subprocess.Popen([sys.executable, '-c',\n"
        "  \"import os,sys,time; open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(60)\",\n"
        "  pidfile])\n"
        "time.sleep(60)\n"
    )
    exe = _py_cli(tmp_path, body)
    pidfile = tmp_path / "orphan.pid"
    start = time.monotonic()
    res = invoke._run_claude(str(pidfile), model=MODEL, timeout_s=1.0, executable=exe)
    elapsed = time.monotonic() - start
    assert res.status == "timeout"
    assert res.diagnostic_code == "semantic_timeout"
    assert elapsed < 8.0  # returned within ~timeout + grace, not the 60s sleep
    # the descendant must be dead (reaped by the process-group kill) — no orphan left behind
    assert pidfile.exists(), "descendant never recorded its pid"
    descendant_pid = int(pidfile.read_text().strip())
    _assert_dead(descendant_pid)


def _assert_dead(pid, tries=50):
    for _ in range(tries):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            return
        time.sleep(0.1)
    pytest.fail(f"process {pid} survived the process-group kill (orphan)")


# ---- argv construction: the Task-1 PINNED lockdown argv, nothing more ----
def test_argv_is_pinned_lockdown(tmp_path):
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable=exe)
    argv = res.envelope["argv"]
    # lockdown flags present
    for flag in ("-p", "--model", "--output-format", "json", "--no-session-persistence",
                 "--tools", "--strict-mcp-config", "--mcp-config"):
        assert flag in argv, f"missing lockdown flag {flag}"
    assert argv[argv.index("--model") + 1] == MODEL
    assert '{"mcpServers":{}}' in argv
    # prohibited flags MUST NOT appear
    for bad in ("--resume", "--continue", "--fallback-model"):
        assert bad not in argv, f"prohibited flag {bad} present"


def test_child_env_is_scrubbed_to_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_SECRET_LEAK", "should-not-pass")
    monkeypatch.setenv("CLAUDE_KEEP_ME", "kept")
    # the fake echoes back the env keys it received
    body = (
        "import sys, os, json\n"
        "env = {'type': 'result', 'model': "
        "(sys.argv[1:][sys.argv[1:].index('--model')+1] if '--model' in sys.argv[1:] else ''), "
        "'result': json.dumps({'verdict':'clean','concerns':[]}), "
        "'env_keys': sorted(os.environ.keys())}\n"
        "sys.stdout.write(json.dumps(env))\n"
    )
    exe = _py_cli(tmp_path, body)
    res = invoke._run_claude("req", model=MODEL, timeout_s=5.0, executable=exe)
    keys = res.envelope["env_keys"]
    assert "SLOPSLAP_SECRET_LEAK" not in keys  # arbitrary vars scrubbed
    assert "CLAUDE_KEEP_ME" in keys            # CLAUDE* allowlisted for auth
    assert "PATH" in keys                      # PATH kept (executable resolution)


# ---- invoke_semantic public boundary: ALWAYS {verdict, concerns} ----
def test_invoke_semantic_success_returns_parsed(tmp_path):
    orig, canon = _canon()
    body = {"verdict": "real", "concerns": [
        {"code": "c", "message": "m", "original_ranges": [{"start_byte": 21, "end_byte": 27}]}]}
    exe = _success_cli(tmp_path, body)
    out = invoke_semantic(orig, "rev", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert set(out.keys()) == {"verdict", "concerns"}
    assert out["verdict"] == "real"


def test_invoke_semantic_schema_violation_is_ambiguous(tmp_path):
    orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "not-a-verdict", "concerns": []})
    out = invoke_semantic(orig, "rev", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "ambiguous", "concerns": []}


@pytest.mark.parametrize("make_exe, code_substr", [
    (lambda tp: _py_cli(tp, "import sys\nsys.stdout.write('NOT JSON')\n"), "semantic_invalid_response"),
    (lambda tp: _py_cli(tp, "import sys\nsys.exit(3)\n"), "semantic_transport_error"),
    (lambda tp: "/nonexistent/claude-xyz", "semantic_transport_error"),
])
def test_invoke_semantic_failure_statuses_are_ambiguous_and_logged(tmp_path, caplog, make_exe, code_substr):
    orig, canon = _canon()
    exe = make_exe(tmp_path)
    with caplog.at_level(logging.WARNING, logger="slopslap.invoke"):
        out = invoke_semantic(orig, "rev", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "ambiguous", "concerns": []}
    assert any(code_substr in rec.getMessage() for rec in caplog.records), caplog.text


def test_invoke_semantic_invalid_utf8_is_ambiguous(tmp_path, caplog):
    _orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    with caplog.at_level(logging.WARNING, logger="slopslap.invoke"):
        out = invoke_semantic(b"\xff\xfe", "rev", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "ambiguous", "concerns": []}


def test_invoke_semantic_accepts_bytes_revision_from_verify_seam(tmp_path):
    # verify() passes revision as BYTES (apply_edits output); the adapter must coerce it.
    orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    out = invoke_semantic(orig, b"revised bytes here", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "clean", "concerns": []}


def test_invoke_semantic_non_utf8_revision_is_ambiguous(tmp_path, caplog):
    orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    with caplog.at_level(logging.WARNING, logger="slopslap.invoke"):
        out = invoke_semantic(orig, b"\xff\xfe", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "ambiguous", "concerns": []}


def test_invoke_semantic_empty_model_raises(tmp_path):
    orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    with pytest.raises(ValueError):
        invoke_semantic(orig, "rev", canon, model="", timeout_s=5.0, executable=exe)


def test_invocation_result_never_crosses_public_boundary(tmp_path):
    orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    out = invoke_semantic(orig, "rev", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert isinstance(out, dict) and not isinstance(out, InvocationResult)
    assert set(out.keys()) == {"verdict", "concerns"}


# ---- model identity: real envelope shape (modelUsage keys), alias match, fail-closed ----
def _modelusage_cli(tmp_path, result_obj, model_key, name="mu_cli.py"):
    """A fake matching the REAL claude -p envelope: no top-level `model`, resolved id in
    modelUsage keys, is_error/subtype present."""
    body = (
        "import sys, json\n"
        f"result = {json.dumps(json.dumps(result_obj))}\n"
        f"env = {{'type':'result','subtype':'success','is_error':False,"
        f"'modelUsage':{{{model_key!r}:{{'inputTokens':1}}}},'result':result}}\n"
        "sys.stdout.write(json.dumps(env))\n"
    )
    return _py_cli(tmp_path, body, name=name)


def test_alias_request_matches_canonical_modelusage_key(tmp_path):
    # request alias "sonnet"; envelope reports canonical "claude-sonnet-5" in modelUsage — MATCH.
    _orig, canon = _canon()
    exe = _modelusage_cli(tmp_path, {"verdict": "real", "concerns": []}, "claude-sonnet-5")
    res = invoke._run_claude("req", model="sonnet", timeout_s=5.0, executable=exe)
    assert res.status == "ok"


def test_absent_model_identity_fails_closed(tmp_path):
    # no modelUsage AND no top-level model -> identity unverifiable -> model_mismatch (fail closed)
    body = ("import sys, json\n"
            "env={'type':'result','subtype':'success','is_error':False,"
            "'result':json.dumps({'verdict':'clean','concerns':[]})}\n"
            "sys.stdout.write(json.dumps(env))\n")
    exe = _py_cli(tmp_path, body, name="no_model.py")
    res = invoke._run_claude("req", model="sonnet", timeout_s=5.0, executable=exe)
    assert res.status == "model_mismatch"


def test_is_error_envelope_is_transport_failure(tmp_path):
    # exit 0 but is_error:true (e.g. max-turns) must NOT be trusted as ok
    body = ("import sys, json\n"
            "env={'type':'result','subtype':'error_max_turns','is_error':True,"
            "'modelUsage':{'claude-sonnet-5':{}},'result':'hit max turns'}\n"
            "sys.stdout.write(json.dumps(env))\n")
    exe = _py_cli(tmp_path, body, name="err_env.py")
    res = invoke._run_claude("req", model="sonnet", timeout_s=5.0, executable=exe)
    assert res.status == "nonzero_exit"


def test_malformed_ledger_fails_closed_not_raises(tmp_path):
    # a ledger entry missing 'source' must collapse to ambiguous, never raise out of the seam
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    bad_canon = {"schema_version": 1, "source_sha256": "0" * 64,
                 "entries": [{"id": "e0", "kind": "literal"}], "protected_spans": []}
    out = invoke_semantic(b"hello", "rev", bad_canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "ambiguous", "concerns": []}


def test_str_original_fails_closed_not_raises(tmp_path):
    # `original` documented as bytes; a str must fail closed, not AttributeError out of the seam
    _orig, canon = _canon()
    exe = _success_cli(tmp_path, {"verdict": "clean", "concerns": []})
    out = invoke_semantic("not-bytes", "rev", canon, model=MODEL, timeout_s=5.0, executable=exe)
    assert out == {"verdict": "ambiguous", "concerns": []}
