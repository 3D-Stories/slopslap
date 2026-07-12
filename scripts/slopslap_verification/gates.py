"""Deterministic hard-gate checkers (spec §Evaluation decision rule).

Each gate is a pure function returning a GateResult. The runner composes them into a
``deterministic_state``; the ledger-verify increment reuses the same checkers as its
layer-1 verifier. No model output can override a deterministic hard failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .atoms import CHECK_EXTRACTORS, new_claim_atoms
from .editscript import Edit, MapError, map_region, sha256_hex
from .mdstructure import PINNED_VERSION
from .mdstructure import compare as md_compare
from .mdstructure import parser_capability


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FIXTURE_ERROR = "fixture_error"


@dataclass
class GateResult:
    name: str
    status: GateStatus
    detail: str = ""
    evidence: List = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status is GateStatus.PASS

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def _decode(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


def material_equal(a: bytes, b: bytes, byte_policy: Optional[dict] = None) -> bool:
    """Byte equality modulo the declared trailing-newline policy (default: preserve)."""
    policy = (byte_policy or {}).get("trailing_newline", "preserve")
    if policy == "normalize":
        return a.rstrip(b"\n") == b.rstrip(b"\n")
    return a == b


# ---- gates ---------------------------------------------------------------


def edit_locality(edits: List[Edit], fixture: dict) -> GateResult:
    ranges = [
        (r["start_byte"], r["end_byte"]) for r in fixture.get("editable_ranges", [])
    ]
    bad = []
    for e in edits:
        if e.is_insertion:
            ok = any(rs <= e.start_byte <= re for rs, re in ranges)
        else:
            ok = any(rs <= e.start_byte and e.end_byte <= re for rs, re in ranges)
        if not ok:
            bad.append([e.start_byte, e.end_byte])
    if bad:
        return GateResult(
            "edit_locality",
            GateStatus.FAIL,
            f"{len(bad)} edit(s) outside authorized ranges",
            evidence=bad,
        )
    return GateResult("edit_locality", GateStatus.PASS)


def protected_spans_intact(
    revision: bytes, edits: List[Edit], fixture: dict
) -> GateResult:
    problems = []
    for sp in fixture.get("protected_spans", []):
        s, e = sp["start_byte"], sp["end_byte"]
        try:
            rs, re = map_region(edits, s, e)
        except MapError as err:
            problems.append(f"span [{s},{e}) boundary inside an edit: {err}")
            continue
        got = sha256_hex(revision[rs:re])
        if got != sp["sha256"]:
            problems.append(
                f"span [{s},{e}) kind={sp.get('kind','?')} sha {sp['sha256'][:10]} "
                f"!= revision {got[:10]}"
            )
    if problems:
        return GateResult(
            "protected_spans_intact", GateStatus.FAIL, "; ".join(problems), evidence=problems
        )
    return GateResult("protected_spans_intact", GateStatus.PASS)


def preservation_region_scoped(
    original: bytes, revision: bytes, edits: List[Edit], fixture: dict
) -> GateResult:
    problems = []
    for region in fixture.get("invariant_regions", []):
        s, e = region["start_byte"], region["end_byte"]
        try:
            rs, re = map_region(edits, s, e)
        except MapError as err:
            problems.append(f"region {region.get('id','?')} unmappable: {err}")
            continue
        o_text = _decode(original[s:e])
        r_text = _decode(revision[rs:re])
        for check in region.get("checks", []):
            extractor = CHECK_EXTRACTORS.get(check)
            if extractor is None:
                problems.append(f"region {region.get('id','?')} unknown check '{check}'")
                continue
            o_atoms, r_atoms = extractor(o_text), extractor(r_text)
            if o_atoms != r_atoms:
                problems.append(
                    f"region {region.get('id','?')} check '{check}': "
                    f"{dict(o_atoms)} -> {dict(r_atoms)}"
                )
    if problems:
        return GateResult(
            "preservation_region_scoped",
            GateStatus.FAIL,
            "; ".join(problems),
            evidence=problems,
        )
    return GateResult("preservation_region_scoped", GateStatus.PASS)


def no_new_claim_atoms(original: bytes, revision: bytes, fixture: dict) -> GateResult:
    introduced = new_claim_atoms(
        _decode(original), _decode(revision), fixture.get("allowed_claim_atoms")
    )
    if introduced:
        return GateResult(
            "no_new_claim_atoms",
            GateStatus.FAIL,
            f"introduced enumerable atoms: {introduced}",
            evidence=[introduced],
        )
    return GateResult("no_new_claim_atoms", GateStatus.PASS)


def markdown_structure(original: bytes, revision: bytes) -> GateResult:
    cap, version = parser_capability()
    if cap == "unavailable":
        return GateResult(
            "markdown_structure",
            GateStatus.CAPABILITY_UNAVAILABLE,
            "markdown-it-py not importable; markdown structure not verified",
        )
    if cap == "version_mismatch":
        return GateResult(
            "markdown_structure",
            GateStatus.FIXTURE_ERROR,
            f"markdown-it-py version {version} != pinned {PINNED_VERSION}",
        )
    violations = md_compare(_decode(original), _decode(revision))
    if violations:
        return GateResult(
            "markdown_structure", GateStatus.FAIL, "; ".join(violations), evidence=violations
        )
    return GateResult("markdown_structure", GateStatus.PASS)


def control_abstention(
    original: bytes, revision: bytes, fixture: dict
) -> Optional[GateResult]:
    """Required only for control fixtures; ANY material edit ⇒ FAIL (WF5 H1)."""
    if not fixture.get("control"):
        return None
    if material_equal(original, revision, fixture.get("byte_policy")):
        return GateResult("control_abstention", GateStatus.PASS)
    return GateResult(
        "control_abstention",
        GateStatus.FAIL,
        "clean-document control was materially edited (must abstain)",
    )


def idempotence(
    first_pass: bytes, second_pass: Optional[bytes], fixture: dict
) -> GateResult:
    if second_pass is None:
        return GateResult(
            "idempotence",
            GateStatus.NOT_EVALUATED,
            "no second-pass artifact supplied",
        )
    if material_equal(first_pass, second_pass, fixture.get("byte_policy")):
        return GateResult("idempotence", GateStatus.PASS)
    return GateResult(
        "idempotence", GateStatus.FAIL, "second pass materially differs from first"
    )
