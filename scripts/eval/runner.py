"""Two-stage eval runner: deterministic_state (hard gates) then acceptance_state (+judge).

A candidate is an edit-script envelope in ORIGINAL coordinates:
  {fixture, baseline, pass_index, edits:[{start_byte,end_byte,replacement_b64}], revision_sha256}
The runner reconstructs the revision and verifies its sha256 before any gate runs — an
inconsistent envelope is a FIXTURE_ERROR, never a silent pass. An optional second-pass
envelope (pass_index=2, base_hash == sha256 of the reconstructed first-pass revision, edits
in FIRST-PASS-REVISION coordinates) feeds the idempotence gate (design R4).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_verification import gates as G  # noqa: E402
from slopslap_verification.editscript import apply_edits, parse_edits, sha256_hex  # noqa: E402
from slopslap_verification.gates import GateResult, GateStatus  # noqa: E402

from .loader import load_fixture, validate_manifest  # noqa: E402


class State(str):
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"
    FIXTURE_ERROR = "FIXTURE_ERROR"


@dataclass
class JudgeOutcome:
    """Result of the LLM-judge A/B (design R7). Populated live in #eval-run."""

    present: bool = False
    errored: bool = False
    beat: bool = False
    detail: str = ""


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
    edits = parse_edits(envelope.get("edits", []))
    revision = apply_edits(original, edits)
    declared = envelope.get("revision_sha256")
    if declared is not None and sha256_hex(revision) != declared:
        raise RunError(
            f"revision_sha256 mismatch: declared {declared[:10]} != actual "
            f"{sha256_hex(revision)[:10]}"
        )
    return revision


def _second_pass_revision(first_pass: bytes, second_env: Optional[dict]) -> Optional[bytes]:
    if second_env is None:
        return None
    base = second_env.get("base_hash")
    if base is not None and base != sha256_hex(first_pass):
        raise RunError(
            f"second pass base_hash {base[:10]} != first-pass sha {sha256_hex(first_pass)[:10]}"
        )
    edits = parse_edits(second_env.get("edits", []))
    return apply_edits(first_pass, edits)


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


def _acceptance_state(det: str, is_control: bool, judge: JudgeOutcome) -> str:
    if det in (State.FAIL, State.FIXTURE_ERROR, State.INCOMPLETE):
        return det
    # det == PASS
    if is_control:
        return State.PASS  # abstention already proven deterministically
    if not judge.present or judge.errored:
        return State.INCOMPLETE  # canonical acceptance needs the A/B result
    return State.PASS if judge.beat else State.FAIL


def run(
    fixture_dir: str,
    candidate: dict,
    second_pass: Optional[dict] = None,
    judge: Optional[JudgeOutcome] = None,
) -> RunResult:
    fixture_name = os.path.basename(fixture_dir.rstrip("/"))
    baseline = candidate.get("baseline", "unknown")
    original, manifest = load_fixture(fixture_dir)

    problems = validate_manifest(original, manifest)
    if problems:
        return RunResult(
            fixture_name,
            baseline,
            State.FIXTURE_ERROR,
            State.FIXTURE_ERROR,
            gates=[{"name": "manifest", "status": "fixture_error", "detail": "; ".join(problems)}],
            detail="manifest invalid",
        )

    try:
        revision = reconstruct(original, candidate)
        second_rev = _second_pass_revision(revision, second_pass)
    except RunError as err:
        return RunResult(
            fixture_name,
            baseline,
            State.FIXTURE_ERROR,
            State.FIXTURE_ERROR,
            gates=[{"name": "reconstruct", "status": "fixture_error", "detail": str(err)}],
            detail=str(err),
        )

    edits = parse_edits(candidate.get("edits", []))
    is_control = bool(manifest.get("control"))
    results: List[GateResult] = []

    if is_control:
        ctrl = G.control_abstention(original, revision, manifest)
        results.append(ctrl)
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
    acc = _acceptance_state(det, is_control, judge or JudgeOutcome())
    return RunResult(
        fixture_name,
        baseline,
        det,
        acc,
        gates=[r.to_dict() for r in results],
        detail="",
    )
