"""Invariant ledger + 3-layer verification + decision rule (spec §Invariant ledger, §Verification).

Layer 1 (deterministic gates) OWNS the hard accept/reject and reuses the increment-1 checkers.
Layer 2 is per-ENTRY survival/attachment over the ledger. Layer 3 is an optional fresh-context
semantic callable the eval-run injects. Decision precedence is strict: REJECT > ASK > SURFACE >
ACCEPT, and an omitted Layer 3 is never a silent ACCEPT (design R1). Byte offsets are canonical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import atoms
from . import gates as G
from .editscript import Edit, map_region_status, parse_edits, apply_edits, sha256_hex

SCHEMA_VERSION = 1

KIND_ENUM = {
    "literal", "number_or_quantity", "normative_statement", "condition", "exception",
    "causal_claim", "attribution", "defined_term", "cross_reference", "unsupported_intent",
    "missing_support", "intentional_repetition", "protected_span",
}
PRESERVATION_ENUM = {
    "byte_exact", "lexically_exact", "semantic_exact", "relationship_exact", "surface_only",
}

# supported deterministic Layer-2 kinds -> (extractor over region text). Others => ASK.
_L2_EXTRACT = {
    "number_or_quantity": lambda t: dict(atoms.quantities(t)),
    "normative_statement": lambda t: {"modals": dict(atoms.modality(t)), "neg": dict(atoms.negation(t))},
    "condition": lambda t: dict(atoms.conditions(t)),
    "exception": lambda t: dict(atoms.conditions(t)),
    "literal": lambda t: {"text": " ".join(t.split())},
    "defined_term": lambda t: {"text": " ".join(t.split())},
}

DECISIONS = ("REJECT", "ASK", "SURFACE", "ACCEPT")
_RANK = {"REJECT": 0, "ASK": 1, "SURFACE": 2, "ACCEPT": 3}


@dataclass
class LedgerEntry:
    id: str
    kind: str
    start_byte: int
    end_byte: int
    text_hash: str
    extracted: dict
    preservation: str
    confidence: int  # 0..1000

    def to_canon(self) -> dict:
        return {
            "id": self.id, "kind": self.kind,
            "source": {"start_byte": self.start_byte, "end_byte": self.end_byte,
                       "text_hash": self.text_hash},
            "extracted": self.extracted, "preservation": self.preservation,
            "confidence": self.confidence,
        }


@dataclass
class ProtectedSpanRec:
    id: str
    start_byte: int
    end_byte: int
    sha256: str

    def to_canon(self) -> dict:
        return {"id": self.id, "start_byte": self.start_byte, "end_byte": self.end_byte,
                "sha256": self.sha256}


@dataclass
class Ledger:
    source_sha256: str
    entries: List[LedgerEntry] = field(default_factory=list)
    protected_spans: List[ProtectedSpanRec] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def canonical_obj(self) -> dict:
        ents = sorted(self.entries, key=lambda e: (e.start_byte, e.end_byte, e.id))
        sps = sorted(self.protected_spans, key=lambda s: (s.start_byte, s.end_byte, s.id))
        return {
            "schema_version": self.schema_version,
            "source_sha256": self.source_sha256,
            "entries": [e.to_canon() for e in ents],
            "protected_spans": [s.to_canon() for s in sps],
        }

    def canonical_bytes(self) -> bytes:
        # EXACT byte-canonical form (design R2): sorted keys, compact separators, no ascii-escape,
        # no trailing newline; ledger_sha256 is NOT part of the hashed object.
        return json.dumps(self.canonical_obj(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")

    def ledger_sha256(self) -> str:
        return sha256_hex(self.canonical_bytes())

    def protected_spans_fixture(self) -> dict:
        return {"protected_spans": [
            {"start_byte": s.start_byte, "end_byte": s.end_byte, "sha256": s.sha256, "kind": "protected"}
            for s in self.protected_spans]}


def _overlaps(a, b) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def validate_ledger(original: bytes, ledger: Ledger) -> List[str]:
    problems: List[str] = []
    n = len(original)
    if sha256_hex(original) != ledger.source_sha256:
        problems.append("source_sha256 does not match the original bytes")
    ids = set()
    for e in ledger.entries:
        if e.id in ids:
            problems.append(f"duplicate id {e.id!r}")
        ids.add(e.id)
        if e.kind not in KIND_ENUM:
            problems.append(f"entry {e.id}: bad kind {e.kind!r}")
        if e.preservation not in PRESERVATION_ENUM:
            problems.append(f"entry {e.id}: bad preservation {e.preservation!r}")
        if not (0 <= e.start_byte <= e.end_byte <= n):
            problems.append(f"entry {e.id}: range out of bounds")
        elif sha256_hex(original[e.start_byte:e.end_byte]) != e.text_hash:
            problems.append(f"entry {e.id}: text_hash inconsistent with original bytes")
        if not isinstance(e.confidence, int) or not (0 <= e.confidence <= 1000):
            problems.append(f"entry {e.id}: confidence must be int 0..1000")
    # entries MAY overlap (containment is normal). protected_spans must be pairwise disjoint.
    sp_ids = set()
    sps = sorted(ledger.protected_spans, key=lambda s: (s.start_byte, s.end_byte))
    for s in ledger.protected_spans:
        if s.id in sp_ids:
            problems.append(f"duplicate protected_span id {s.id!r}")
        sp_ids.add(s.id)
        if not (0 <= s.start_byte <= s.end_byte <= n):
            problems.append(f"protected_span {s.id}: out of bounds")
        elif sha256_hex(original[s.start_byte:s.end_byte]) != s.sha256:
            problems.append(f"protected_span {s.id}: sha256 inconsistent")
    for a, b in zip(sps, sps[1:]):
        if _overlaps((a.start_byte, a.end_byte), (b.start_byte, b.end_byte)):
            problems.append(f"protected_spans overlap: {a.id} & {b.id}")
    return problems


# region-check -> (kind, preservation, confidence) for auto-derivation.
_CHECK_KIND = {
    "numbers": ("number_or_quantity", "lexically_exact", 950),
    "units": ("number_or_quantity", "lexically_exact", 950),
    "modality": ("normative_statement", "semantic_exact", 950),
    "negation": ("normative_statement", "semantic_exact", 900),
    "conditions": ("condition", "relationship_exact", 850),
}


def build_ledger(original: bytes, manifest: dict) -> Ledger:
    src = sha256_hex(original)
    entries: List[LedgerEntry] = []
    for ri, region in enumerate(manifest.get("invariant_regions", [])):
        s, e = region["start_byte"], region["end_byte"]
        region_text = original[s:e].decode("utf-8", errors="replace")
        for check in region.get("checks", []):
            if check not in _CHECK_KIND:
                continue
            kind, pres, conf = _CHECK_KIND[check]
            extract = _L2_EXTRACT.get(kind)
            extracted = extract(region_text) if extract else {}
            entries.append(LedgerEntry(
                id=f"e{ri}_{check}", kind=kind, start_byte=s, end_byte=e,
                text_hash=sha256_hex(original[s:e]), extracted=extracted,
                preservation=pres, confidence=conf,
            ))
    prot = [ProtectedSpanRec(id=f"ps{i}", start_byte=sp["start_byte"], end_byte=sp["end_byte"],
                             sha256=sp["sha256"]) for i, sp in enumerate(manifest.get("protected_spans", []))]
    return Ledger(source_sha256=src, entries=entries, protected_spans=prot)


# ---- verification --------------------------------------------------------
def _finding(layer, severity, code, message, entry_ids=None, o_ranges=None, hunks=None, disposition="reject"):
    return {
        "layer": layer, "severity": severity, "code": code, "message": message,
        "entry_ids": entry_ids or [], "original_ranges": o_ranges or [],
        "implicated_hunk_ids": hunks or [], "disposition": disposition,
    }


def _hunks_for_range(edits: List[Edit], start: int, end: int) -> List[str]:
    out = []
    for i, e in enumerate(sorted(edits, key=lambda x: (x.start_byte, x.end_byte))):
        if not (e.end_byte <= start or e.start_byte >= end):
            out.append(f"h{i}")
    return out


def normalize_semantic(output) -> dict:
    """Validate the Layer-3 callable's output; anything malformed => ambiguous (design R7)."""
    if not isinstance(output, dict):
        return {"verdict": "ambiguous", "concerns": [], "note": "non-dict output"}
    verdict = output.get("verdict")
    if verdict not in ("real", "ambiguous", "clean"):
        return {"verdict": "ambiguous", "concerns": [], "note": "bad verdict"}
    concerns = output.get("concerns") or []
    if not isinstance(concerns, list):
        return {"verdict": "ambiguous", "concerns": [], "note": "bad concerns"}
    return {"verdict": verdict, "concerns": concerns}


def verify(
    original: bytes,
    edits_input,
    ledger: Ledger,
    authorized_ranges: Optional[List[dict]] = None,
    semantic_fn: Optional[Callable] = None,
    allow_two_layer: bool = False,
) -> dict:
    edits: List[Edit] = edits_input if edits_input and isinstance(edits_input[0], Edit) else parse_edits(edits_input or [])
    problems = validate_ledger(original, ledger)
    if problems:
        return {"decision": "REJECT", "proposal_status": "BLOCKED", "semantic_status": "not_run",
                "findings": [_finding(0, "fixture", "invalid_ledger", "; ".join(problems))],
                "hunks": [], "ledger_sha256": ledger.ledger_sha256()}

    revision = apply_edits(original, edits)
    ordered = sorted(edits, key=lambda e: (e.start_byte, e.end_byte))
    hunk_recs = [{"hunk_id": f"h{i}", "original_range": [e.start_byte, e.end_byte],
                  "decision": "ACCEPT", "finding_ids": [], "revertable": True}
                 for i, e in enumerate(ordered)]
    findings: List[dict] = []

    # ---- Layer 1: deterministic hard gates (own the hard reject) ----
    l1 = []
    l1.append(G.protected_spans_intact(revision, edits, ledger.protected_spans_fixture()))
    l1.append(G.no_new_claim_atoms(original, revision, {"allowed_claim_atoms": []}))
    l1.append(G.markdown_structure(original, revision))
    if authorized_ranges is not None:
        l1.append(G.edit_locality(edits, {"editable_ranges": authorized_ranges}))
    for r in l1:
        if r.status is G.GateStatus.FAIL:
            findings.append(_finding(1, "hard", r.name, r.detail, disposition="reject"))
        elif r.status is G.GateStatus.FIXTURE_ERROR:
            findings.append(_finding(1, "fixture", r.name, r.detail, disposition="reject"))

    # ---- Layer 2: per-entry survival / attachment ----
    for entry in ledger.entries:
        interval, status = map_region_status(edits, entry.start_byte, entry.end_byte)
        hunks = _hunks_for_range(edits, entry.start_byte, entry.end_byte)
        if status == "unchanged":
            continue
        if status == "deleted":
            findings.append(_finding(2, "hard", "entry_dropped",
                                     f"ledger entry {entry.id} ({entry.kind}) region was deleted",
                                     entry_ids=[entry.id], hunks=hunks, disposition="reject"))
            continue
        if status == "ambiguous":
            findings.append(_finding(2, "uncertain", "entry_unmappable",
                                     f"ledger entry {entry.id} source boundary is inside an edit",
                                     entry_ids=[entry.id], hunks=hunks, disposition="ask"))
            continue
        # modified: re-extract and compare, if a deterministic rule exists
        extract = _L2_EXTRACT.get(entry.kind)
        if extract is None:
            findings.append(_finding(2, "uncertain", "entry_no_rule",
                                     f"entry {entry.id} kind {entry.kind} has no deterministic L2 rule",
                                     entry_ids=[entry.id], hunks=hunks, disposition="ask"))
            continue
        rs, re = interval
        rev_extract = extract(revision[rs:re].decode("utf-8", errors="replace"))
        if rev_extract != entry.extracted:
            findings.append(_finding(2, "hard", "entry_weakened",
                                     f"entry {entry.id} ({entry.kind}) changed: "
                                     f"{entry.extracted} -> {rev_extract}",
                                     entry_ids=[entry.id], hunks=hunks, disposition="reject"))

    # ---- Layer 3: optional adversarial semantic ----
    semantic_status = "not_run"
    if semantic_fn is not None:
        try:
            raw = semantic_fn(original, revision, ledger.canonical_obj())
            sem = normalize_semantic(raw)
        except Exception as err:  # noqa: BLE001 - a failing/hanging injector => ambiguous, never clean
            sem = {"verdict": "ambiguous", "concerns": [], "note": f"exception: {err!r}"}
        semantic_status = sem["verdict"]
        if sem["verdict"] == "real":
            for c in sem["concerns"] or [{"code": "semantic", "message": "unattributed"}]:
                eids = c.get("entry_ids") or []
                oranges = c.get("original_ranges") or []
                attributed = bool(eids or oranges)
                hunks = []
                for rng in oranges:
                    hunks += _hunks_for_range(edits, rng.get("start_byte", 0), rng.get("end_byte", 0))
                findings.append(_finding(3, "semantic", c.get("code", "semantic"),
                                         c.get("message", ""), entry_ids=eids, o_ranges=oranges,
                                         hunks=hunks, disposition="reject" if attributed else "reject_global"))
        elif sem["verdict"] == "ambiguous":
            findings.append(_finding(3, "semantic", "semantic_ambiguous",
                                     "adversarial semantic pass was inconclusive", disposition="surface"))

    # ---- fold decision (strict precedence) ----
    dispositions = {f["disposition"] for f in findings}
    global_reject = "reject_global" in dispositions
    if "reject" in dispositions or "reject_global" in dispositions:
        decision = "REJECT"
    elif "ask" in dispositions:
        decision = "ASK"
    elif "surface" in dispositions:
        decision = "SURFACE"
    elif semantic_fn is None and not allow_two_layer:
        decision = "SURFACE"  # design R1: no L3 => not shippable by default
    else:
        decision = "ACCEPT"

    # attribute findings to hunks
    fid = 0
    for f in findings:
        f["id"] = f"f{fid}"; fid += 1
        for h in hunk_recs:
            if h["hunk_id"] in f["implicated_hunk_ids"]:
                h["finding_ids"].append(f["id"])
                if f["disposition"] in ("reject", "reject_global"):
                    h["decision"] = "REJECT"
        if f["disposition"] == "reject_global" or (f["disposition"] == "reject" and not f["implicated_hunk_ids"]):
            for h in hunk_recs:
                h["revertable"] = False
    if global_reject:
        for h in hunk_recs:
            h["revertable"] = False

    return {
        "decision": decision,
        "proposal_status": "ACCEPT" if decision == "ACCEPT" else "BLOCKED",
        "semantic_status": semantic_status,
        "findings": findings,
        "hunks": hunk_recs,
        "ledger_sha256": ledger.ledger_sha256(),
    }
