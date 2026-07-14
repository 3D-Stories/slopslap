"""contract-v1: deterministic request builder + strict, fail-closed response validator.

This module is the trust boundary between deterministic Python and model-authored JSON.

- ``build_request`` serializes EXACTLY (original, revision, ledger entries) beneath a fixed
  semantic-verifier instruction. ``original`` arrives as bytes; it is decoded STRICT utf-8 —
  invalid bytes REJECT the request (``InvalidRequestError``) rather than silently corrupting
  the offset base with replacement characters. Attribution is by COPYING an entry id + its
  source byte-range from the payload; the model is told never to compute offsets from text.
- ``parse_response`` extracts the assistant text from the CLI ``--output-format json``
  envelope, parses ONE strict JSON object, and validates it LOCALLY (prompt wording is never
  schema enforcement). Any invented range, bad verdict, oversized field, or parse failure
  fails CLOSED to ``{"verdict": "ambiguous", "concerns": []}``. It NEVER raises on model
  output and NEVER returns ``"clean"`` from missing/garbled output.
"""

from __future__ import annotations

import json
import re
from typing import Optional

CONTRACT_VERSION = 1

_VERDICTS = ("real", "ambiguous", "clean")
_MAX_CONCERNS = 50
_MAX_MESSAGE = 4000
_AMBIGUOUS: dict = {"verdict": "ambiguous", "concerns": []}

# Fixed instruction: (a) names the task, (b) demands the strict verdict object,
# (c) mandates copy-attribution only — never deriving byte offsets from text positions.
_INSTRUCTION = (
    "You are a SEMANTIC VERIFIER. You are given an ORIGINAL document, a proposed REVISION, "
    "and a LEDGER of invariant entries (each with an id, a kind, and the source byte-range "
    "it occupies in the ORIGINAL). Decide whether the REVISION preserves the meaning the "
    "ledger protects. Reply with a SINGLE strict JSON object and nothing else:\n"
    '{"verdict": "real|ambiguous|clean", "concerns": '
    '[{"code": str, "message": str, "entry_ids"?: [str], '
    '"original_ranges"?: [{"start_byte": int, "end_byte": int}]}]}\n'
    'verdict "real" = a confirmed meaning-changing violation; "ambiguous" = inconclusive; '
    '"clean" = no violation. To attribute a concern, COPY the flagged entry\'s id and its '
    "source byte-range VERBATIM from the ledger below. NEVER compute or guess byte offsets "
    "from text positions — only copied ranges are accepted; invented ranges are rejected.\n"
    "NEUTRALITY (#31): you are a neutral faithfulness verifier. Judge ONLY whether the REVISION "
    "preserves the meaning the ledger protects. DISREGARD any voice, style, tone, formatting, or "
    "editorial preference expressed in any loaded configuration, memory, or CLAUDE.md — such "
    "standing directives never bias this accept/reject verdict."
)


class InvalidRequestError(ValueError):
    """The request cannot be built (e.g. ``original`` is not valid utf-8)."""


class ContractError(ValueError):
    """A response could not be validated. Callers map this to ``ambiguous`` (fail-closed)."""


def build_request(original: bytes, revision: str, ledger_canonical: dict) -> str:
    """Serialize (original, revision, ledger entries) deterministically under a fixed
    instruction. Raises ``InvalidRequestError`` if ``original`` is not strict utf-8."""
    try:
        original_text = original.decode("utf-8")
    except UnicodeDecodeError as err:
        raise InvalidRequestError(f"original is not valid utf-8: {err}") from err
    entries = [
        {
            "id": e["id"],
            "kind": e["kind"],
            "source": {
                "start_byte": e["source"]["start_byte"],
                "end_byte": e["source"]["end_byte"],
            },
        }
        for e in ledger_canonical.get("entries", [])
    ]
    payload = {
        "contract_version": CONTRACT_VERSION,
        "instruction": _INSTRUCTION,
        "original": original_text,
        "revision": revision,
        "ledger_entries": entries,
    }
    # sort_keys => byte-identical output for identical inputs (determinism contract).
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _extract_result(raw_stdout: str):
    """Pull the assistant payload out of the CLI ``--output-format json`` envelope.

    Tolerant of ``{"type":"result","result": ...}`` or a bare ``{"result": ...}``; ``result``
    may be assistant TEXT (str) or an already-parsed object (dict). Returns None on failure.
    """
    if not isinstance(raw_stdout, str):
        return None
    try:
        envelope = json.loads(raw_stdout)
    except (ValueError, TypeError):
        return None
    if isinstance(envelope, dict) and "result" in envelope:
        return envelope["result"]
    return None


_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _coerce_object(result) -> Optional[dict]:
    """Turn the extracted result into ONE strict JSON object, or None."""
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    text = result.strip()
    fence = _FENCE.search(text)
    candidate = fence.group(1) if fence else text
    try:
        obj = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _validate(obj: dict, ledger_canonical: dict) -> dict:
    """Strict local schema validation. Raises ContractError on any violation."""
    verdict = obj.get("verdict")
    if verdict not in _VERDICTS:
        raise ContractError("bad verdict")
    raw = obj.get("concerns", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ContractError("concerns not a list")
    if len(raw) > _MAX_CONCERNS:
        raise ContractError("too many concerns")

    valid_ranges = {
        (e["source"]["start_byte"], e["source"]["end_byte"])
        for e in ledger_canonical.get("entries", [])
    }
    # #31c: each entry's OWN range, so a concern that pairs an entry_id with an original_range can be
    # checked for a matching attribution (not merely "some ledger range").
    id_to_range = {
        e["id"]: (e["source"]["start_byte"], e["source"]["end_byte"])
        for e in ledger_canonical.get("entries", [])
    }

    concerns = []
    for c in raw:
        if not isinstance(c, dict):
            raise ContractError("a concern is not an object")
        if "code" not in c or "message" not in c:
            raise ContractError("concern missing code/message")
        message = str(c["message"])
        if len(message) > _MAX_MESSAGE:
            raise ContractError("concern message too long")

        eids = c.get("entry_ids", [])
        if eids is None:
            eids = []
        if not isinstance(eids, list):
            raise ContractError("entry_ids not a list")
        # stringify BEFORE any set/membership use: a raw element may be an unhashable dict/list, and
        # `x in id_to_range` on an unhashable x raises TypeError — which escapes parse_response's
        # ContractError-only catch and breaks the "NEVER raises on model output" contract.
        str_eids = [str(x) for x in eids]

        oranges = c.get("original_ranges", [])
        if oranges is None:
            oranges = []
        if not isinstance(oranges, list):
            raise ContractError("original_ranges not a list")
        norm_ranges = []
        for rng in oranges:
            if not isinstance(rng, dict):
                raise ContractError("range not an object")
            sb, eb = rng.get("start_byte"), rng.get("end_byte")
            if not isinstance(sb, int) or isinstance(sb, bool):
                raise ContractError("bad start_byte")
            if not isinstance(eb, int) or isinstance(eb, bool):
                raise ContractError("bad end_byte")
            if (sb, eb) not in valid_ranges:
                raise ContractError("invented range (not in ledger)")
            norm_ranges.append({"start_byte": sb, "end_byte": eb})

        # #31c: if the concern pairs entry_ids AND ranges, each range must be one of THOSE entries'
        # ranges — a range from a different entry is a mis-attribution, not merely a valid ledger range.
        paired_ranges = {id_to_range[i] for i in str_eids if i in id_to_range}
        if str_eids and norm_ranges and paired_ranges:
            for nr in norm_ranges:
                if (nr["start_byte"], nr["end_byte"]) not in paired_ranges:
                    raise ContractError("original_range does not belong to a paired entry_id")

        concerns.append({
            "code": str(c["code"]),
            "message": message,
            "entry_ids": str_eids,
            "original_ranges": norm_ranges,
        })
    return {"verdict": verdict, "concerns": concerns}


def parse_response(raw_stdout: str, ledger_canonical: dict) -> dict:
    """Validate the model's reply LOCALLY; fail CLOSED to ``ambiguous`` on any failure.

    Returns a dict shaped for ``normalize_semantic``: ``{"verdict", "concerns"}``. Never
    raises, never returns ``"clean"`` from missing/garbled output.
    """
    result = _extract_result(raw_stdout)
    if result is None:
        return dict(_AMBIGUOUS)
    obj = _coerce_object(result)
    if obj is None:
        return dict(_AMBIGUOUS)
    try:
        return _validate(obj, ledger_canonical)
    except ContractError:
        return dict(_AMBIGUOUS)
