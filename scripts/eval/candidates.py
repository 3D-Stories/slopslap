"""Deterministic candidate generators for the eval loop (design R1–R4, R8).

Three baselines, each a pure function of the input bytes so the SAME function runs on pass 1
(the original) AND pass 2 (the repaired output) — idempotence falls out because the slopslap
generator keys on the HARM CONTENT, which is gone after a repair.

- slopslap: apply the SKILL judgment — repair demonstrated editorial harm within editable
  ranges; ABSTAIN (explicit disposition, empty edits) on clean/distinctive prose (keystone rule).
- humanizer_emulation: a declared, versioned de-stylizing POLICY applied doc-wide, WITHOUT
  consulting slopslap's expected failures (representative/emulated — NOT the upstream product).
- original_unchanged: empty edits.

Candidates are authored by the live session engine (Opus 4.8) applying skills/slopslap/SKILL.md;
the pinned first-pass output digests (test_eval_run) freeze that demonstrated output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from slopslap_verification.editscript import Edit, apply_edits, derive_edits, sha256_hex

SLOPSLAP_POLICY_VERSION = "slopslap-judgment-v1"
HUMANIZER_POLICY_VERSION = "humanizer-emulation-v1"


@dataclass
class Candidate:
    baseline: str
    fixture: str
    input_sha256: str
    disposition: str  # "repair" | "abstain"
    reason: str
    edits: List[Edit]
    provenance: dict = field(default_factory=dict)

    def to_envelope(self, original: bytes, baseline_name: str = None) -> dict:
        revision = apply_edits(original, self.edits)
        return {
            "baseline": baseline_name or self.baseline,
            "pass_index": 1,
            "edits": [{"start_byte": e.start_byte, "end_byte": e.end_byte,
                       "replacement_b64": _b64(e.replacement)} for e in self.edits],
            "revision_sha256": sha256_hex(revision),
        }


def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode()


def _span(data: bytes, sub: bytes) -> Tuple[int, int]:
    i = data.find(sub)
    return (i, i + len(sub)) if i >= 0 else (-1, -1)


# ---- slopslap: content-keyed repairs (idempotent) ------------------------
# each entry: fixture -> [(harm substring, replacement)] within its editable range.
_SLOPSLAP_REPAIRS = {
    "distinctive-essay": [
        (b"In today's fast-paced world, it is important to note that soldering remains a valuable "
         b"and essential skill for countless hobbyists and professionals alike. Whether you are a "
         b"beginner or an expert, mastering the fundamentals can unlock a wide range of exciting "
         b"opportunities and possibilities.",
         b"Soldering is a skill worth learning, beginner or expert."),
        (b"Furthermore, it is worth mentioning that patience and practice are key components of "
         b"success in this domain. By dedicating time and effort, individuals can achieve remarkable "
         b"results and continuously improve their abilities over time.",
         b"It rewards patience and practice."),
    ],
    "normative-spec": [
        (b"The system should be robust, intuitive, and user-friendly under all conditions.",
         b"[Requirement unclear] Define measurable criteria: 'robust/intuitive/user-friendly' is "
         b"not testable as written."),
    ],
    "underspecified-prd": [
        (b"We will delight users with a seamless, best-in-class notification experience that feels "
         b"magical.",
         b"[Unsupported aspiration] State the measurable delivery requirement, or mark this a non-goal."),
    ],
}


def build_slopslap(fixture: str, original: bytes) -> Candidate:
    prov = {"policy": SLOPSLAP_POLICY_VERSION, "engine": "opus-4.8",
            "engine_note": "authoring engine recorded, not selected by the plugin (advisory)"}
    repairs = _SLOPSLAP_REPAIRS.get(fixture, [])
    edits: List[Edit] = []
    for harm, repl in repairs:
        s, e = _span(original, harm)
        if s >= 0:  # harm present -> repair; absent (control/repaired) -> nothing (idempotent)
            edits.append(Edit(s, e, repl))
    edits.sort(key=lambda x: x.start_byte)
    if edits:
        return Candidate("slopslap", fixture, sha256_hex(original), "repair",
                         f"repaired {len(edits)} demonstrated-harm passage(s)", edits, prov)
    return Candidate("slopslap", fixture, sha256_hex(original), "abstain",
                     "no demonstrated editorial harm (keystone rule)", [], prov)


# ---- humanizer_emulation: doc-wide de-stylizing policy -------------------
# representative of humanizer treating stylistic features as contaminants; NOT the product.
_HUMANIZER_RULES = [
    ("—", ", "),                 # strip em-dashes (a "tell")
    ("; ", ". "),                # semicolons -> periods
    ("In today's fast-paced world, ", ""),
    ("It is important to note that ", ""),
    (" does not ", " doesn't "),  # "naturalize" via contractions
    (" do not ", " don't "),
]


def build_humanizer(fixture: str, original: bytes) -> Candidate:
    text = original.decode("utf-8", errors="surrogateescape")
    for a, b in _HUMANIZER_RULES:
        text = text.replace(a, b)
    transformed = text.encode("utf-8", errors="surrogateescape")
    edits = derive_edits(original, transformed)
    prov = {"policy": HUMANIZER_POLICY_VERSION,
            "note": "representative/emulated de-stylizing policy, NOT the upstream humanizer product"}
    disp = "repair" if edits else "abstain"
    return Candidate("humanizer_emulation", fixture, sha256_hex(original), disp,
                     f"applied {HUMANIZER_POLICY_VERSION} doc-wide", edits, prov)


def build_original(fixture: str, original: bytes) -> Candidate:
    return Candidate("original_unchanged", fixture, sha256_hex(original), "abstain",
                     "no edits", [], {"policy": "identity"})


BUILDERS = {
    "slopslap": build_slopslap,
    "humanizer_emulation": build_humanizer,
    "original_unchanged": build_original,
}
