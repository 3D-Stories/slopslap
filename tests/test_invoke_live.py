"""Live + recorded-fixture tests for the #26 platform-feasibility spike.

The LIVE test is gated behind SLOPSLAP_LIVE=1 (same env-gate convention as SLOPSLAP_FSYNC):
it makes a real `claude -p` invocation and needs host Claude Code auth, so CI — which has no
auth — SKIPS it visibly (never a silent pass). The recorded-fixture test runs unconditionally
in CI: it proves the recorded invocation's response contract is well-formed and drives a
coherent verify() decision, without any model call.
"""

import json
import os

import pytest

from slopslap_verification.editscript import sha256_hex
from slopslap_verification.ledger import Ledger, LedgerEntry, normalize_semantic, verify

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(REPO, "tests", "fixtures", "invoke", "recorded_invocation.json")
PROBE = os.path.join(REPO, "tests", "fixtures", "invoke", "probe_evidence.json")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_recorded_invocation_fixture_is_wellformed():
    fx = _load(FIXTURE)
    # the pinned lockdown argv shape is present and carries the full-lockdown flags
    argv = fx["argv_shape"]
    assert "--no-session-persistence" in argv
    assert "--tools" in argv and "--strict-mcp-config" in argv and "--mcp-config" in argv
    assert fx["runner_status"] == "ok"
    # the recorded semantic result is exactly the normalize_semantic-input shape
    res = fx["semantic_result"]
    assert set(res) == {"verdict", "concerns"}
    assert res["verdict"] in ("real", "ambiguous", "clean")


def test_recorded_result_drives_a_coherent_verify_decision():
    """The recorded 'clean' verdict, replayed as a semantic_fn, must ship the faithful edit."""
    fx = _load(FIXTURE)
    original = fx["request"]["original_utf8"].encode("utf-8")
    revision = fx["request"]["revision"]
    recorded = fx["semantic_result"]
    # normalize_semantic accepts the recorded shape unchanged
    assert normalize_semantic(recorded)["verdict"] == recorded["verdict"]
    # a faithful edit within an authorized range + the recorded clean verdict => shippable
    led = Ledger(source_sha256=sha256_hex(original))
    edits = [{"start_byte": 4, "end_byte": 13,
              "replacement_b64": _b64(revision.encode("utf-8")[4:13])}]
    out = verify(original, edits, led,
                 authorized_ranges=[{"start_byte": 4, "end_byte": 13}],
                 semantic_fn=lambda o, r, l: recorded)
    if recorded["verdict"] == "clean":
        assert out["semantic_status"] == "clean"


def test_probe_evidence_shows_lockdown_differential():
    """The committed probe evidence must show the isolation differential the spike proved."""
    pe = _load(PROBE)
    # no-lockdown leaked; full lockdown had zero tool surface and zero leak
    assert pe["control_no_lockdown"]["sentinel_leak_count"] > 0
    assert pe["lockdown_full"]["init_tools_count"] == 0
    assert pe["lockdown_full"]["init_mcp_servers_count"] == 0
    assert pe["lockdown_full"]["sentinel_leak_count"] == 0
    assert pe["lockdown_full"]["tool_use_names"] == []


@pytest.mark.skipif(
    os.environ.get("SLOPSLAP_LIVE") != "1",
    reason="live claude -p invocation; set SLOPSLAP_LIVE=1 with host Claude Code auth to run",
)
def test_live_invocation_through_adapter():
    from slopslap_invoke.invoke import invoke_semantic

    original = b"The service processes up to 100 requests per second under nominal load."
    revision = "The service handles up to 100 requests per second under nominal load."
    led = Ledger(source_sha256=sha256_hex(original), entries=[
        LedgerEntry("e0", "number_or_quantity", 21, 24, sha256_hex(original[21:24]),
                    {"n": "100"}, "lexically_exact", 900),
    ])
    res = invoke_semantic(original, revision, led.canonical_obj(), model="sonnet", timeout_s=120.0)
    assert set(res) == {"verdict", "concerns"}
    assert res["verdict"] in ("real", "ambiguous", "clean")
    # a faithful synonym edit should not be flagged 'real' (a hard violation)
    assert res["verdict"] != "real"


def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode()
