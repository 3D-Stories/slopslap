"""Frozen-schema contract tests for the review-decisions + feedback-ledger formats (#58, P0).

These pin the two schemas the de-slop pivot's REVIEW and LEARN stages round-trip:
- ``decisions.json`` — UNTRUSTED input to apply (user's per-finding apply/edit/discard).
- ``feedback.jsonl`` — one local, purgeable feedback-ledger line per decision.

"Frozen" means the validators ARE the contract: a canonical payload validates clean, and each
single-field corruption is rejected with a problem. If a future change loosens the shape, one of
these red-before-green cases flips.
"""

import base64
import copy

import pytest

from slopslap_review.schema import (
    DECISIONS_SCHEMA_VERSION,
    FEEDBACK_SCHEMA_VERSION,
    DecisionsError,
    FeedbackError,
    validate_decisions,
    validate_decisions_for_apply,
    validate_feedback_line,
)

# valid base64 whose decoded bytes are NOT valid UTF-8 (0xff 0xfe is not a UTF-8 sequence)
NON_UTF8_B64 = base64.b64encode(b"\xff\xfe").decode()

SHA_A = "a" * 64
SHA_B = "b" * 64
REPLACEMENT_B64 = base64.b64encode("innovative distributed".encode()).decode()


def _canonical_decisions():
    return {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "doc": "docs/whitepaper.md",
        "source_sha256": SHA_A,
        "decisions": [
            {"finding_id": "generic_diction:12", "user_action": "apply"},
            {
                "finding_id": "adjective_pile:40",
                "user_action": "edit",
                "replacement": REPLACEMENT_B64,
                "alternative": "subjectivize",
            },
            {
                "finding_id": "simulation:88",
                "user_action": "discard",
                "reason": "keep_voice",
            },
        ],
    }


def _canonical_feedback():
    return {
        "ts": "2026-07-14T06:30:00Z",
        "finding_id": "adjective_pile:40",
        "category": "diction",
        "metric": "corporate_adjective_pile",
        "genre": "marketing",
        "recommendation": "strip",
        "user_action": "edit",
        "replacement": REPLACEMENT_B64,
        "reason": "keep_voice",
        "doc_sha": SHA_A,
    }


# --- decisions.json ---------------------------------------------------------


def test_canonical_decisions_valid():
    assert validate_decisions(_canonical_decisions()) == []


def test_decisions_finding_id_matched_against_snapshot():
    obj = _canonical_decisions()
    ids = {"generic_diction:12", "adjective_pile:40", "simulation:88"}
    assert validate_decisions(obj, audit_finding_ids=ids) == []
    # an id absent from the snapshot is rejected (replay against a drifted audit)
    problems = validate_decisions(obj, audit_finding_ids={"generic_diction:12"})
    assert any("unknown finding_id" in p for p in problems)


def test_decisions_sha_binding():
    obj = _canonical_decisions()
    assert validate_decisions(obj, expected_source_sha256=SHA_A) == []
    problems = validate_decisions(obj, expected_source_sha256=SHA_B)
    assert any("source_sha256" in p for p in problems)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update(schema_version=2),
        lambda o: o.update(schema_version=True),  # bool is not an accepted int here
        lambda o: o.update(schema_version="1"),
        lambda o: o.pop("doc"),
        lambda o: o.update(doc=""),
        lambda o: o.update(source_sha256="a" * 63),  # wrong length
        lambda o: o.update(source_sha256="A" * 64),  # uppercase not lowercase-hex
        lambda o: o.update(source_sha256="g" * 64),  # non-hex char
        lambda o: o.pop("source_sha256"),
        lambda o: o.update(decisions="notalist"),
        lambda o: o.update(surprise="x"),  # unknown top-level key
    ],
)
def test_decisions_structural_corruptions_rejected(mutate):
    obj = _canonical_decisions()
    mutate(obj)
    assert validate_decisions(obj) != []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(user_action="reject"),  # bad enum
        lambda d: d.pop("finding_id"),
        lambda d: d.update(finding_id=""),
        lambda d: d.update(surprise="x"),  # unknown decision key
    ],
)
def test_decisions_per_item_corruptions_rejected(mutate):
    obj = _canonical_decisions()
    mutate(obj["decisions"][0])
    assert validate_decisions(obj) != []


def test_decisions_edit_requires_replacement():
    obj = _canonical_decisions()
    del obj["decisions"][1]["replacement"]
    assert any("replacement" in p for p in validate_decisions(obj))


def test_decisions_apply_forbids_replacement():
    obj = _canonical_decisions()
    obj["decisions"][0]["replacement"] = REPLACEMENT_B64
    assert any("replacement" in p for p in validate_decisions(obj))


def test_decisions_edit_replacement_must_be_base64():
    obj = _canonical_decisions()
    obj["decisions"][1]["replacement"] = "not valid base64!!"
    assert any("base64" in p for p in validate_decisions(obj))


def test_decisions_edit_replacement_must_decode_to_utf8():
    obj = _canonical_decisions()
    obj["decisions"][1]["replacement"] = NON_UTF8_B64  # valid base64, non-UTF-8 bytes
    assert any("UTF-8" in p or "utf-8" in p for p in validate_decisions(obj))


def test_validate_decisions_for_apply_requires_bindings_and_enforces_them():
    ids = {"generic_diction:12", "adjective_pile:40", "simulation:88"}
    # correct bindings → valid
    assert validate_decisions_for_apply(
        _canonical_decisions(), audit_finding_ids=ids, expected_source_sha256=SHA_A
    ) == []
    # wrong sha → rejected (the structural-only validate_decisions would have passed without it)
    assert validate_decisions_for_apply(
        _canonical_decisions(), audit_finding_ids=ids, expected_source_sha256=SHA_B
    ) != []
    # unknown finding id vs snapshot → rejected
    assert validate_decisions_for_apply(
        _canonical_decisions(),
        audit_finding_ids={"generic_diction:12"},
        expected_source_sha256=SHA_A,
    ) != []
    # bindings are NOT optional on the apply-facing entry point
    with pytest.raises(TypeError):
        validate_decisions_for_apply(_canonical_decisions())


def test_decisions_duplicate_finding_id_rejected():
    obj = _canonical_decisions()
    obj["decisions"][1]["finding_id"] = obj["decisions"][0]["finding_id"]
    assert any("duplicate" in p for p in validate_decisions(obj))


def test_decisions_bad_reason_enum_rejected():
    obj = _canonical_decisions()
    obj["decisions"][2]["reason"] = "dont_like_it"
    assert any("reason" in p for p in validate_decisions(obj))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(user_action=["apply"]),  # unhashable list where an enum str is expected
        lambda d: d.update(user_action={"a": 1}),  # unhashable dict
        lambda d: d.update(reason=["keep_voice"]),  # unhashable in the reason enum check
    ],
)
def test_decisions_unhashable_enum_values_rejected_not_raised(mutate):
    # untrusted boundary must return a problem, never raise (8a R2 Finding 1)
    obj = _canonical_decisions()
    mutate(obj["decisions"][0])
    assert validate_decisions(obj) != []


def test_decisions_non_dict_payload():
    assert validate_decisions(["not", "a", "dict"]) != []


def test_decisions_empty_decisions_list_valid():
    obj = _canonical_decisions()
    obj["decisions"] = []
    assert validate_decisions(obj) == []


# --- feedback.jsonl ---------------------------------------------------------


def test_canonical_feedback_valid():
    assert validate_feedback_line(_canonical_feedback()) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update(genre="aviation"),  # not in VALID_GENRES
        lambda o: o.update(recommendation="delete"),  # bad enum
        lambda o: o.update(user_action="reject"),  # bad enum
        lambda o: o.update(ts="14 July 2026"),  # not ISO-8601
        lambda o: o.pop("ts"),
        lambda o: o.pop("finding_id"),
        lambda o: o.pop("metric"),
        lambda o: o.update(doc_sha="z" * 64),  # non-hex
        lambda o: o.update(doc_sha="a" * 10),  # wrong length
        lambda o: o.update(reason="whatever"),  # bad reason enum
        lambda o: o.update(surprise="x"),  # unknown key
    ],
)
def test_feedback_corruptions_rejected(mutate):
    obj = _canonical_feedback()
    mutate(obj)
    assert validate_feedback_line(obj) != []


def test_feedback_edit_requires_replacement():
    obj = _canonical_feedback()
    del obj["replacement"]
    assert any("replacement" in p for p in validate_feedback_line(obj))


def test_feedback_apply_forbids_replacement():
    obj = _canonical_feedback()
    obj["user_action"] = "apply"
    # replacement still present -> rejected for a non-edit action
    assert any("replacement" in p for p in validate_feedback_line(obj))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update(genre=["marketing"]),  # unhashable list in enum check
        lambda o: o.update(recommendation={"x": 1}),
        lambda o: o.update(user_action=["apply"]),
        lambda o: o.update(reason=["keep_voice"]),
    ],
)
def test_feedback_unhashable_enum_values_rejected_not_raised(mutate):
    obj = _canonical_feedback()
    mutate(obj)
    assert validate_feedback_line(obj) != []


@pytest.mark.parametrize("ts", ["2026-07-14", "20260714", "2026-W27-1"])
def test_feedback_ts_requires_time_component(ts):
    obj = _canonical_feedback()
    obj["ts"] = ts
    assert any("ts" in p for p in validate_feedback_line(obj))


def test_feedback_schema_version_optional_but_guarded():
    obj = _canonical_feedback()
    assert validate_feedback_line(obj) == []  # absent is fine (line-versionless by default)
    obj["schema_version"] = FEEDBACK_SCHEMA_VERSION
    assert validate_feedback_line(obj) == []  # present-and-correct is fine
    obj["schema_version"] = 2
    assert any("schema_version" in p for p in validate_feedback_line(obj))  # present-and-wrong rejected


def test_feedback_edit_replacement_must_decode_to_utf8():
    obj = _canonical_feedback()
    obj["replacement"] = NON_UTF8_B64
    assert any("UTF-8" in p or "utf-8" in p for p in validate_feedback_line(obj))


def test_feedback_reason_optional():
    obj = _canonical_feedback()
    obj["user_action"] = "apply"
    del obj["replacement"]
    del obj["reason"]
    assert validate_feedback_line(obj) == []


def test_feedback_non_dict_payload():
    assert validate_feedback_line("nope") != []


# --- error classes are exported and are ValueError subclasses ---------------


def test_error_classes_are_value_errors():
    assert issubclass(DecisionsError, ValueError)
    assert issubclass(FeedbackError, ValueError)


def test_schema_versions_frozen_at_1():
    assert DECISIONS_SCHEMA_VERSION == 1
    assert FEEDBACK_SCHEMA_VERSION == 1


# --------------------------------------------------------------------------- #81 alternatives


def _canonical_alternatives():
    return [
        {"id": "subjectivize", "text": "delivers results we stand behind", "claim_status": "none"},
        {"id": "scope-verifiable", "text": "passes the full 3-layer suite",
         "claim_status": "scoped", "label": "claims what the doc supports"},
    ]


def test_decisions_alternative_only_allowed_with_edit():
    # #81 AC2: alternative labels an edit's provenance; on apply/discard it is rejected.
    payload = _canonical_decisions()
    payload["decisions"][0]["alternative"] = "subjectivize"  # user_action: apply
    problems = validate_decisions(payload)
    assert any("alternative is only allowed with user_action 'edit'" in p for p in problems)


def test_decisions_alternative_with_edit_still_valid():
    assert validate_decisions(_canonical_decisions()) == []


def test_feedback_alternative_optional_and_edit_only():
    from slopslap_review.schema import validate_feedback_line as v
    line = _canonical_feedback()
    line["user_action"] = "edit"
    line["replacement"] = REPLACEMENT_B64
    line["alternative"] = "subjectivize"
    assert v(line) == []
    bad = _canonical_feedback()
    bad["user_action"] = "discard"
    del bad["replacement"]
    bad["alternative"] = "subjectivize"
    assert any("alternative is only allowed with user_action 'edit'" in p for p in v(bad))
    nonstr = _canonical_feedback()
    nonstr["user_action"] = "edit"
    nonstr["replacement"] = REPLACEMENT_B64
    nonstr["alternative"] = 7
    assert any("alternative" in p for p in v(nonstr))


def test_validate_alternatives_canonical_clean():
    from slopslap_review.schema import validate_alternatives
    assert validate_alternatives(_canonical_alternatives()) == []


def test_validate_alternatives_rejects_bad_shapes():
    from slopslap_review.schema import validate_alternatives
    assert validate_alternatives("nope") == ["alternatives must be a list"]
    assert any("must be an object" in p for p in validate_alternatives(["x"]))
    bad_enum = _canonical_alternatives()
    bad_enum[0]["claim_status"] = "amazing"
    assert any("claim_status" in p for p in validate_alternatives(bad_enum))
    unhashable = _canonical_alternatives()
    unhashable[0]["claim_status"] = ["none"]  # must be a problem, never a TypeError
    assert any("claim_status" in p for p in validate_alternatives(unhashable))
    dup = _canonical_alternatives()
    dup[1]["id"] = dup[0]["id"]
    assert any("duplicate" in p for p in validate_alternatives(dup))
    unknown = _canonical_alternatives()
    unknown[0]["surprise"] = True
    assert any("unknown key" in p for p in validate_alternatives(unknown))
    nolabel = _canonical_alternatives()
    nolabel[1]["label"] = ""
    assert any("label" in p for p in validate_alternatives(nolabel))
