"""Frozen schema validators for the review-decisions and feedback-ledger formats.

Both validators follow the repo's established ``loader.validate_manifest`` idiom: a pure
function returning ``List[str]`` of problems (empty == valid), never raising, checking
required/typed fields first and bailing before it would index anything unsafely. The
``*Error`` classes exist for callers that need to hard-fail on structurally-unrecoverable
input (idiom #2, e.g. ``FixtureError``/``LedgerBuildError``).

``decisions.json`` is UNTRUSTED input to ``apply`` (the keystone: the user's review decision
authorizes edits, the byte-exact verifier still hard-gates every applied edit). This module is
the first fail-closed boundary in front of that: strict key allowlist, enum allowlist, sha
shape, base64-only replacement payloads (data, never executed). It is a pure function over an
already-parsed object — no file/path I/O, so no traversal surface. JSON decoding happens in the
caller; these validators only see parsed Python objects.

Schema versions are frozen at 1. ``decisions.json`` is always version-guarded (mirroring
``loader.SCHEMA_VERSION``); a ``feedback.jsonl`` line is versionless by default (file-level
versioning) but carries an OPTIONAL ``schema_version`` field that is guarded when present.
"""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from typing import List, Optional, Set

from eval.loader import VALID_GENRES  # single source of truth for the genre enum

DECISIONS_SCHEMA_VERSION = 1
FEEDBACK_SCHEMA_VERSION = 1

USER_ACTIONS = {"apply", "edit", "discard"}
RECOMMENDATIONS = {"strip", "keep"}
# One shared reason enum across decisions.json and feedback.jsonl (a discard captures WHY).
REASONS = {"false_positive", "keep_voice", "genre_wrong", "other"}
# #81: claim-status enum for de-claim alternatives (design §02: none/scoped/kept/banned).
ALT_CLAIM_STATUS = {"none", "scoped", "kept", "banned"}

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")

_DECISIONS_TOP_KEYS = {"schema_version", "doc", "source_sha256", "decisions"}
_DECISION_KEYS = {"finding_id", "user_action", "replacement", "alternative", "reason"}
_FEEDBACK_KEYS = {
    "schema_version",  # optional; guarded when present
    "ts",
    "finding_id",
    "category",
    "metric",
    "genre",
    "recommendation",
    "user_action",
    "replacement",
    "alternative",  # optional (#81): provenance label of an alternative-seeded edit
    "reason",
    "doc_sha",
}
_ALTERNATIVE_KEYS = {"id", "text", "claim_status", "label"}


class DecisionsError(ValueError):
    """Structurally-unrecoverable review-decisions payload."""


class FeedbackError(ValueError):
    """Structurally-unrecoverable feedback-ledger line."""


def _is_nonempty_str(x) -> bool:
    return isinstance(x, str) and x != ""


def _is_int(x) -> bool:
    # bool is an int subclass in Python; an untrusted boundary must not accept True as 1.
    return isinstance(x, int) and not isinstance(x, bool)


def _in_enum(x, enum: Set[str]) -> bool:
    # membership must not raise on an unhashable JSON value (list/dict) — this is the
    # untrusted decisions.json boundary; a bad value is a problem, never a TypeError.
    return isinstance(x, str) and x in enum


def _b64_utf8_problem(s: str) -> Optional[str]:
    """None if ``s`` is valid base64 decoding to valid UTF-8, else a short reason.

    A replacement is the exact bytes an ``edit`` would splice into a document; the seam is
    UTF-8-text-only, so a payload that decodes to non-UTF-8 bytes is rejected HERE, not
    deep in apply.
    """
    try:
        raw = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        return "is not valid base64"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "base64 does not decode to UTF-8"
    return None


def _unknown_keys(obj: dict, allowed: Set[str], prefix: str) -> List[str]:
    return [f"{prefix}unknown key '{k}'" for k in sorted(set(obj) - allowed)]


def validate_decisions(
    obj,
    *,
    audit_finding_ids: Optional[Set[str]] = None,
    expected_source_sha256: Optional[str] = None,
    alternative_ids: Optional[dict] = None,
) -> List[str]:
    """Return problems (empty == valid) for a parsed ``decisions.json`` payload.

    ``audit_finding_ids`` — when given, every decision's ``finding_id`` must be a member (an id
    absent from the audit snapshot is a replay against a drifted audit). When ``None`` (P0: no
    findings-envelope producer exists yet), only structural validity is checked.
    ``expected_source_sha256`` — when given, ``source_sha256`` must equal it (the decisions-layer
    analogue of assemble.py's ``digest_mismatch`` replay guard).
    ``alternative_ids`` — when given, a ``{finding_id: set-of-offered-alternative-ids}`` map from
    the audit's findings; a decision's ``alternative`` must be one its finding actually offered
    (#81 — a stale/fabricated label would otherwise corrupt learning attribution). A finding
    absent from the map offered none, so any label on it is rejected.
    """
    problems: List[str] = []
    if not isinstance(obj, dict):
        return ["decisions payload must be a JSON object"]

    problems += _unknown_keys(obj, _DECISIONS_TOP_KEYS, "")

    sv = obj.get("schema_version")
    if not _is_int(sv):
        problems.append("schema_version must be an int")
    elif sv != DECISIONS_SCHEMA_VERSION:
        problems.append(f"schema_version {sv} != {DECISIONS_SCHEMA_VERSION}")

    if not _is_nonempty_str(obj.get("doc")):
        problems.append("doc must be a non-empty string")

    ssha = obj.get("source_sha256")
    if not isinstance(ssha, str) or not _HEX64.match(ssha):
        problems.append("source_sha256 must be a 64-char lowercase-hex string")
    elif expected_source_sha256 is not None and ssha != expected_source_sha256:
        problems.append("source_sha256 does not match expected (drifted file / replay)")

    decisions = obj.get("decisions")
    if not isinstance(decisions, list):
        problems.append("decisions must be a list")

    # a structural problem above makes the per-decision loop unsafe to index
    if problems:
        return problems

    seen_ids: Set[str] = set()
    for i, d in enumerate(decisions):
        at = f"decisions[{i}] "
        if not isinstance(d, dict):
            problems.append(at + "must be an object")
            continue
        problems += _unknown_keys(d, _DECISION_KEYS, at)

        fid = d.get("finding_id")
        if not _is_nonempty_str(fid):
            problems.append(at + "finding_id must be a non-empty string")
        else:
            if fid in seen_ids:
                problems.append(at + f"duplicate finding_id '{fid}'")
            seen_ids.add(fid)
            if audit_finding_ids is not None and fid not in audit_finding_ids:
                problems.append(at + f"unknown finding_id '{fid}' (not in audit snapshot)")

        action = d.get("user_action")
        if not _in_enum(action, USER_ACTIONS):
            problems.append(at + f"user_action must be one of {sorted(USER_ACTIONS)}")

        rep = d.get("replacement")
        if action == "edit":
            if not _is_nonempty_str(rep):
                problems.append(at + "user_action 'edit' requires a base64 replacement")
            else:
                b64_problem = _b64_utf8_problem(rep)
                if b64_problem:
                    problems.append(at + "replacement " + b64_problem)
        elif rep is not None:
            problems.append(at + "replacement is only allowed with user_action 'edit'")

        alt = d.get("alternative")
        if alt is not None:
            if not _is_nonempty_str(alt):
                problems.append(at + "alternative must be a non-empty string when present")
            elif action != "edit":
                # #81: an alternative pick IS an edit (its text seeds the replacement) — on any
                # other action the label has no referent, so it is rejected like `replacement`.
                problems.append(at + "alternative is only allowed with user_action 'edit'")
            elif alternative_ids is not None and _is_nonempty_str(fid) \
                    and alt not in (alternative_ids.get(fid) or set()):
                problems.append(at + f"unknown alternative '{alt}' for finding '{fid}'")

        reason = d.get("reason")
        if reason is not None and not _in_enum(reason, REASONS):
            problems.append(at + f"reason must be one of {sorted(REASONS)}")

    return problems


def validate_decisions_for_apply(
    obj,
    *,
    audit_finding_ids: Set[str],
    expected_source_sha256: str,
    alternative_ids: Optional[dict] = None,
) -> List[str]:
    """Apply-facing validation: BOTH replay bindings are REQUIRED (no keyword default).

    ``validate_decisions`` leaves the audit-snapshot match and the source-sha binding
    OPTIONAL so structural validity is exercisable at P0 (no findings-envelope producer
    exists yet). But the ``apply`` stage authorizes edits, so it must never run against a
    ``decisions.json`` whose finding-ids and file-binding were not both checked. This entry
    point makes that impossible to forget: a caller that omits either argument gets a
    ``TypeError`` at the call site, not a silently-relaxed "valid".
    """
    return validate_decisions(
        obj,
        audit_finding_ids=audit_finding_ids,
        expected_source_sha256=expected_source_sha256,
        alternative_ids=alternative_ids,
    )


def validate_feedback_line(obj) -> List[str]:
    """Return problems (empty == valid) for one parsed feedback-ledger JSONL line.

    Freezes the line SHAPE only; the ledger's storage properties (hashed spans, local,
    purgeable) belong to the writer (P5), not this schema.
    """
    problems: List[str] = []
    if not isinstance(obj, dict):
        return ["feedback line must be a JSON object"]

    problems += _unknown_keys(obj, _FEEDBACK_KEYS, "")

    sv = obj.get("schema_version")
    if sv is not None and (not _is_int(sv) or sv != FEEDBACK_SCHEMA_VERSION):
        problems.append(f"schema_version must be {FEEDBACK_SCHEMA_VERSION} when present")

    for field in ("ts", "finding_id", "category", "metric"):
        if not _is_nonempty_str(obj.get(field)):
            problems.append(f"{field} must be a non-empty string")

    ts = obj.get("ts")
    if isinstance(ts, str):
        # tolerate a trailing 'Z' (datetime.fromisoformat rejects it before 3.11)
        norm = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
        try:
            datetime.fromisoformat(norm)
        except ValueError:
            problems.append("ts must be an ISO-8601 timestamp")
        else:
            # a timestamp needs a time-of-day: reject a bare date / basic / week-date form
            if "T" not in ts and " " not in ts:
                problems.append("ts must be an ISO-8601 timestamp with a time component")

    if not _in_enum(obj.get("genre"), VALID_GENRES):
        problems.append(f"genre must be one of {sorted(VALID_GENRES)}")
    if not _in_enum(obj.get("recommendation"), RECOMMENDATIONS):
        problems.append(f"recommendation must be one of {sorted(RECOMMENDATIONS)}")
    action = obj.get("user_action")
    if not _in_enum(action, USER_ACTIONS):
        problems.append(f"user_action must be one of {sorted(USER_ACTIONS)}")

    dsha = obj.get("doc_sha")
    if not isinstance(dsha, str) or not _HEX64.match(dsha):
        problems.append("doc_sha must be a 64-char lowercase-hex string")

    rep = obj.get("replacement")
    if action == "edit":
        if not _is_nonempty_str(rep):
            problems.append("user_action 'edit' requires a base64 replacement")
        else:
            b64_problem = _b64_utf8_problem(rep)
            if b64_problem:
                problems.append("replacement " + b64_problem)
    elif rep is not None:
        problems.append("replacement is only allowed with user_action 'edit'")

    alt = obj.get("alternative")
    if alt is not None:
        if not _is_nonempty_str(alt):
            problems.append("alternative must be a non-empty string when present")
        elif action != "edit":
            problems.append("alternative is only allowed with user_action 'edit'")

    reason = obj.get("reason")
    if reason is not None and not _in_enum(reason, REASONS):
        problems.append(f"reason must be one of {sorted(REASONS)}")

    return problems


def validate_alternatives(alts) -> List[str]:
    """Return problems (empty == valid) for a finding's ``alternatives`` list (#81).

    Shape: ``[{id, text, claim_status, label?}]`` — ``id`` non-empty and unique within the list,
    ``text`` a string (may be empty for a delete-shaped alternative), ``claim_status`` in
    ``ALT_CLAIM_STATUS``, ``label`` optional non-empty string. Pure over a parsed object, same
    loader idiom as the other validators; producers (the model lane, #84) and the review UI
    (#83) share this as the single source of the shape.
    """
    problems: List[str] = []
    if not isinstance(alts, list):
        return ["alternatives must be a list"]
    seen: Set[str] = set()
    for i, a in enumerate(alts):
        at = f"alternatives[{i}] "
        if not isinstance(a, dict):
            problems.append(at + "must be an object")
            continue
        problems += _unknown_keys(a, _ALTERNATIVE_KEYS, at)
        aid = a.get("id")
        if not _is_nonempty_str(aid):
            problems.append(at + "id must be a non-empty string")
        else:
            if aid in seen:
                problems.append(at + f"duplicate id '{aid}'")
            seen.add(aid)
        if not isinstance(a.get("text"), str):
            problems.append(at + "text must be a string")
        if not _in_enum(a.get("claim_status"), ALT_CLAIM_STATUS):
            problems.append(at + f"claim_status must be one of {sorted(ALT_CLAIM_STATUS)}")
        label = a.get("label")
        if label is not None and not _is_nonempty_str(label):
            problems.append(at + "label must be a non-empty string when present")
    return problems
