"""Two-stage eval runner: deterministic_state (hard gates) then acceptance_state (+judge).

A candidate is an edit-script envelope in ORIGINAL coordinates:
  {fixture, baseline, pass_index:1, edits:[{start_byte,end_byte,replacement_b64}], revision_sha256}
The runner reconstructs the revision and verifies its sha256 before any gate runs; a missing
or mismatched hash, a malformed edit script, or corrupt (non-utf-8) bytes is a FIXTURE_ERROR,
never a silent pass (WF5-diff F6/F7/F8). An optional second-pass envelope (pass_index:2,
base_hash == sha256 of the reconstructed first-pass revision, edits in FIRST-PASS-REVISION
coordinates) feeds the idempotence gate (design R4).

Canonical acceptance requires the LLM-judge A/B beat-criterion to hold against BOTH baselines
(`humanizer` AND `original-unchanged`); ``judge`` is a mapping baseline -> validated
``judge.JudgeVerdict`` (produced by ``judge.evaluate`` over >=3 complete trials), never a raw
caller boolean (WF5-diff F1). Live judging is injected in #eval-run.
"""

from __future__ import annotations

import binascii
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_verification import gates as G  # noqa: E402
from slopslap_verification.editscript import (  # noqa: E402
    EditError,
    apply_edits,
    parse_edits,
    sha256_hex,
)
from slopslap_verification.gates import GateResult, GateStatus  # noqa: E402

from .judge import JudgeVerdict  # noqa: E402
from .loader import load_fixture, validate_manifest  # noqa: E402

REQUIRED_BASELINES = ("humanizer", "original-unchanged")

_MALFORMED = (EditError, binascii.Error, KeyError, TypeError, ValueError)


class State(str):
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"
    FIXTURE_ERROR = "FIXTURE_ERROR"


@dataclass
class RunResult:
    fixture: str
    baseline: str
    deterministic_state: str
    acceptance_state: str
    gates: List[dict] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "fixture": self.fixture,
            "baseline": self.baseline,
            "deterministic_state": self.deterministic_state,
            "acceptance_state": self.acceptance_state,
            "gates": self.gates,
            "detail": self.detail,
        }


class RunError(Exception):
    """Envelope/manifest inconsistency -> FIXTURE_ERROR."""


def reconstruct(original: bytes, envelope: dict) -> bytes:
    if envelope.get("pass_index", 1) != 1:
        raise RunError(f"candidate pass_index must be 1, got {envelope.get('pass_index')}")
    declared = envelope.get("revision_sha256")
    if not declared:
        raise RunError("candidate missing required revision_sha256")
    revision = apply_edits(original, parse_edits(envelope.get("edits", [])))
    if sha256_hex(revision) != declared:
        raise RunError(
            f"revision_sha256 mismatch: declared {declared[:10]} != actual "
            f"{sha256_hex(revision)[:10]}"
        )
    return revision


def _second_pass_revision(first_pass: bytes, second_env: Optional[dict]) -> Optional[bytes]:
    if second_env is None:
        return None
    if second_env.get("pass_index") != 2:
        raise RunError(f"second pass must have pass_index 2, got {second_env.get('pass_index')}")
    base = second_env.get("base_hash")
    if not base:
        raise RunError("second pass missing required base_hash")
    if base != sha256_hex(first_pass):
        raise RunError(
            f"second pass base_hash {base[:10]} != first-pass sha {sha256_hex(first_pass)[:10]}"
        )
    revision = apply_edits(first_pass, parse_edits(second_env.get("edits", [])))
    declared = second_env.get("revision_sha256")
    if declared and sha256_hex(revision) != declared:
        raise RunError("second pass revision_sha256 mismatch")
    return revision


def _strict_utf8(*blobs: bytes) -> None:
    for b in blobs:
        b.decode("utf-8")  # raises UnicodeDecodeError on corrupt bytes -> caught as FIXTURE_ERROR


def _deterministic_state(results: List[GateResult]) -> str:
    if any(r.status is GateStatus.FIXTURE_ERROR for r in results):
        return State.FIXTURE_ERROR
    if any(r.status is GateStatus.FAIL for r in results):
        return State.FAIL
    if any(
        r.status in (GateStatus.CAPABILITY_UNAVAILABLE, GateStatus.NOT_EVALUATED)
        for r in results
    ):
        return State.INCOMPLETE
    return State.PASS


def _acceptance_state(
    det: str, is_control: bool, judge: Optional[Dict[str, JudgeVerdict]]
) -> str:
    if det in (State.FAIL, State.FIXTURE_ERROR, State.INCOMPLETE):
        return det
    # det == PASS
    if is_control:
        return State.PASS  # abstention already proven deterministically
    if judge is None:
        return State.INCOMPLETE  # canonical acceptance needs the A/B result
    for baseline in REQUIRED_BASELINES:
        verdict = judge.get(baseline)
        if verdict is None or not verdict.present or verdict.errored:
            return State.INCOMPLETE  # judge absent/errored for a required baseline
    if all(judge[b].beat for b in REQUIRED_BASELINES):
        return State.PASS
    return State.FAIL  # lost/tied a required baseline


def _fixture_error(name: str, baseline: str, gate: str, detail: str) -> RunResult:
    return RunResult(
        name,
        baseline,
        State.FIXTURE_ERROR,
        State.FIXTURE_ERROR,
        gates=[{"name": gate, "status": "fixture_error", "detail": detail}],
        detail=detail,
    )


def run(
    fixture_dir: str,
    candidate: dict,
    second_pass: Optional[dict] = None,
    judge: Optional[Dict[str, JudgeVerdict]] = None,
) -> RunResult:
    fixture_name = os.path.basename(fixture_dir.rstrip("/"))
    baseline = candidate.get("baseline", "unknown")
    original, manifest = load_fixture(fixture_dir)

    problems = validate_manifest(original, manifest)
    if problems:
        return _fixture_error(fixture_name, baseline, "manifest", "; ".join(problems))

    try:
        revision = reconstruct(original, candidate)
        second_rev = _second_pass_revision(revision, second_pass)
    except RunError as err:
        return _fixture_error(fixture_name, baseline, "reconstruct", str(err))
    except _MALFORMED as err:
        return _fixture_error(
            fixture_name, baseline, "reconstruct", f"malformed edit script: {err}"
        )

    try:
        blobs = [original, revision] + ([second_rev] if second_rev is not None else [])
        _strict_utf8(*blobs)
    except UnicodeDecodeError as err:
        return _fixture_error(
            fixture_name, baseline, "encoding", f"non-utf-8 bytes: {err}"
        )

    edits = parse_edits(candidate.get("edits", []))
    is_control = bool(manifest.get("control"))
    results: List[GateResult] = []

    if is_control:
        results.append(G.control_abstention(original, revision, manifest))
        results.append(G.edit_locality(edits, manifest))
        results.append(G.markdown_structure(original, revision))
    else:
        results.append(G.edit_locality(edits, manifest))
        results.append(G.protected_spans_intact(revision, edits, manifest))
        results.append(G.preservation_region_scoped(original, revision, edits, manifest))
        results.append(G.no_new_claim_atoms(original, revision, manifest))
        results.append(G.markdown_structure(original, revision))
        results.append(G.idempotence(revision, second_rev, manifest))

    det = _deterministic_state(results)
    acc = _acceptance_state(det, is_control, judge)
    return RunResult(
        fixture_name,
        baseline,
        det,
        acc,
        gates=[r.to_dict() for r in results],
        detail="",
    )
