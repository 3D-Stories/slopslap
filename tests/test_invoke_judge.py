"""#102 — the Codex judge transport (`invoke_judge`) in slopslap_invoke.invoke.

The transport is exercised through a FAKE executable (a python script written to tmp) so every
failure class is driven deterministically without the real CLI: ok / cli_missing / nonzero_exit /
parse_error / timeout. The fake reads its behavior from a `MODE:<x>` token INSIDE the request
text (never from the environment — the child env is scrubbed, and that scrub is itself asserted).
"""
import json
import os
import stat
import sys
import time

import pytest

from slopslap_invoke.invoke import invoke_judge, models_match

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["preferred"],
          "properties": {"preferred": {"type": "string", "enum": ["A", "B", "equal"]}}}

FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
argv = sys.argv[1:]
req = sys.stdin.read()
here = os.path.dirname(os.path.abspath(__file__))
# record what we were given, for the argv/env/stdin assertions
with open(os.path.join(here, "record.json"), "w") as fh:
    json.dump({"argv": argv, "env": dict(os.environ), "stdin_len": len(req), "cwd": os.getcwd()}, fh)
out = argv[argv.index("-o") + 1] if "-o" in argv else None
mode = "ok"
for tok in req.split():
    if tok.startswith("MODE:"):
        mode = tok.split(":", 1)[1]
if mode == "ok":
    with open(out, "w") as fh:
        json.dump({"preferred": "B", "stdin_len": len(req)}, fh)
    sys.exit(0)
if mode == "nonzero":
    sys.stderr.write("boom\n"); sys.exit(3)
if mode == "badjson":
    with open(out, "w") as fh:
        fh.write("not json at all")
    sys.exit(0)
if mode == "noout":
    sys.exit(0)
if mode == "sleep":
    time.sleep(30); sys.exit(0)
sys.exit(9)
'''


@pytest.fixture
def fake(tmp_path):
    exe = tmp_path / "fakecodex"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def _record(fake):
    with open(fake.parent / "record.json") as fh:
        return json.load(fh)


def test_ok_returns_the_parsed_output_object_and_marks_model_unconfirmed(fake):
    sink = {}
    got = invoke_judge("judge this MODE:ok", model="gpt-5.6-sol", schema=SCHEMA,
                       executable=str(fake), status_sink=sink)
    assert got == {"preferred": "B", "stdin_len": len("judge this MODE:ok")}
    assert sink["invocation_status"] == "ok"
    # the codex CLI never echoes the model that answered — the transport must say so, not guess.
    assert sink["model_confirmed"] is False


def test_request_is_delivered_on_stdin(fake):
    req = "MODE:ok " + ("x" * 5000)
    got = invoke_judge(req, model="m", schema=SCHEMA, executable=str(fake))
    assert got["stdin_len"] == len(req)
    assert _record(fake)["stdin_len"] == len(req)


def test_argv_pins_the_lockdown_flags_and_the_model(fake):
    invoke_judge("MODE:ok", model="gpt-5.6-sol", schema=SCHEMA, executable=str(fake))
    argv = _record(fake)["argv"]
    assert argv[0] == "exec"
    assert argv[argv.index("-m") + 1] == "gpt-5.6-sol"
    for flag in ("--sandbox", "--ephemeral", "--skip-git-repo-check", "--output-schema", "-o", "-C"):
        assert flag in argv, flag
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[-1] == "-"  # the prompt comes from stdin, never from argv
    # the schema and out files lived INSIDE the private temp cwd, which is gone afterwards
    cwd = argv[argv.index("-C") + 1]
    assert argv[argv.index("--output-schema") + 1].startswith(cwd)
    assert argv[argv.index("-o") + 1].startswith(cwd)
    assert not os.path.exists(cwd)


def test_schema_file_carries_the_given_schema(fake, tmp_path):
    # the fake copies nothing, so assert via a second fake that snapshots the schema file
    snap = tmp_path / "snap"
    snap.write_text(FAKE.replace('"cwd": os.getcwd()', '"cwd": os.getcwd(), "schema": open(argv[argv.index("--output-schema")+1]).read()'))
    snap.chmod(snap.stat().st_mode | stat.S_IXUSR)
    invoke_judge("MODE:ok", model="m", schema=SCHEMA, executable=str(snap))
    assert json.loads(_record(snap)["schema"]) == SCHEMA


def test_child_env_is_scrubbed_to_the_allowlist(fake, monkeypatch):
    monkeypatch.setenv("SLOPSLAP_SECRET_TEST", "1")
    monkeypatch.setenv("CODEX_HOME_PROBE", "kept")
    invoke_judge("MODE:ok", model="m", schema=SCHEMA, executable=str(fake))
    env = _record(fake)["env"]
    assert "SLOPSLAP_SECRET_TEST" not in env
    assert "PATH" in env and "HOME" in env
    assert env.get("CODEX_HOME_PROBE") == "kept"  # CODEX* is the one new prefix (auth lives under HOME)


def test_missing_executable_is_cli_missing(tmp_path):
    sink = {}
    got = invoke_judge("MODE:ok", model="m", schema=SCHEMA,
                       executable=str(tmp_path / "nope"), status_sink=sink)
    assert got is None
    assert sink["invocation_status"] == "cli_missing"


def test_nonzero_exit_is_reported_and_yields_none(fake):
    sink = {}
    assert invoke_judge("MODE:nonzero", model="m", schema=SCHEMA, executable=str(fake), status_sink=sink) is None
    assert sink["invocation_status"] == "nonzero_exit"


def test_unparseable_output_is_parse_error(fake):
    sink = {}
    assert invoke_judge("MODE:badjson", model="m", schema=SCHEMA, executable=str(fake), status_sink=sink) is None
    assert sink["invocation_status"] == "parse_error"


def test_missing_output_file_is_parse_error_not_ok(fake):
    sink = {}
    assert invoke_judge("MODE:noout", model="m", schema=SCHEMA, executable=str(fake), status_sink=sink) is None
    assert sink["invocation_status"] == "parse_error"


def test_timeout_kills_the_child_and_reports_timeout(fake):
    sink = {}
    t0 = time.monotonic()
    got = invoke_judge("MODE:sleep", model="m", schema=SCHEMA, executable=str(fake),
                       timeout_s=1.5, status_sink=sink)
    assert got is None
    assert sink["invocation_status"] == "timeout"
    assert time.monotonic() - t0 < 12  # the bound held (kill grace included), never the 30 s sleep


def test_status_sink_is_sticky_worst(fake):
    sink = {}
    invoke_judge("MODE:nonzero", model="m", schema=SCHEMA, executable=str(fake), status_sink=sink)
    invoke_judge("MODE:ok", model="m", schema=SCHEMA, executable=str(fake), status_sink=sink)
    assert sink["invocation_status"] == "nonzero_exit"


def test_empty_model_is_a_caller_bug(fake):
    with pytest.raises(ValueError):
        invoke_judge("MODE:ok", model="", schema=SCHEMA, executable=str(fake))


def test_models_match_uses_the_token_rule():
    assert models_match("gpt-5.6-sol", ["claude-fable-5-1"]) is False
    assert models_match("sonnet", ["claude-sonnet-5"]) is True
    assert models_match("gpt-5.6-sol", ["gpt-5.6-sol"]) is True
    assert models_match("opus", ["claude-opusx-9"]) is False   # no loose substring match (#31e)
    assert models_match("sonnet", []) is False


def test_child_env_carries_no_anthropic_or_claude_variable(fake, monkeypatch):
    """#102 Step 8a: the judge is a DIFFERENT vendor, so an Anthropic credential must never cross
    into it. The allowlist inherited `_ENV_ALLOW_PREFIXES` from the claude transport, which passes
    every CLAUDE*/ANTHROPIC* variable — including an API key — to the codex child."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-cross")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "must-not-cross")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-kept")
    monkeypatch.setenv("CODEX_HOME_PROBE", "kept")
    invoke_judge("MODE:ok", model="m", schema=SCHEMA, executable=str(fake))
    env = _record(fake)["env"]
    assert [k for k in env if k.startswith(("ANTHROPIC", "CLAUDE"))] == []
    assert "sk-ant-must-not-cross" not in json.dumps(env)
    assert "PATH" in env and "HOME" in env
    assert env.get("CODEX_HOME_PROBE") == "kept" and env.get("XDG_CONFIG_HOME") == "/tmp/xdg-kept"
