"""Findings-with-recommendations envelope (issue #59, de-slop pivot P1 / AC2).

build_findings(audit, doc) turns an AuditResult (+ its source bytes) into strip-ready Findings:
one per scanner metric location, each carrying its genre-gated recommendation, a candidate
proposed_rewrite (delete-span for strip, None for keep), and a verifier_precheck that runs the
candidate through verify() Layers 1+2 so a review UI can show safe-vs-blocked per finding.
"""

import hashlib

import pytest

from slopslap_assemble.assemble import audit_document
from slopslap_review.findings import Finding, FindingsError, build_findings


def _audit(tmp_path, text, *, genre=None, fmt="markdown", name="doc.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    stage = audit_document(str(p), fmt=fmt, declared_genre=genre)
    assert stage.status == "ok", f"audit failed: {stage}"
    return stage.data, p.read_bytes()


# a repetition-heavy paragraph (6 "X, not Y") -> negative_parallelism (a "cadence" class metric). The
# "not" in each clause is a NEGATION invariant, so deleting the unit is (correctly) verifier-REJECTED.
_REP_PARA = (". ".join(f"choose {w} thing, not other thing" for w in "abcdef") + ".")
_CLEAN_INTRO = "This is a short ordinary paragraph with nothing much to flag in it at all."
_CADENCE_DOC = f"{_CLEAN_INTRO}\n\n{_REP_PARA}\n"
# a transition-cluster paragraph (However/Furthermore/Moreover) with NO invariant / protected span:
# deleting the whole unit passes verifier Layers 1+2 -> a "safe" strip precheck.
_TRANSITION_PARA = ("However it works well. Furthermore it scales up. Moreover it helps a lot. "
                    "However it stays fast. Furthermore it feels clean.")
_TRANSITION_DOC = f"{_CLEAN_INTRO}\n\n{_TRANSITION_PARA}\n"


def test_build_findings_produces_findings_for_a_flagged_doc(tmp_path):
    audit, doc = _audit(tmp_path, _CADENCE_DOC)
    findings = build_findings(audit, doc)
    assert findings, "a flagged doc yields findings"
    assert all(isinstance(f, Finding) for f in findings)
    # every finding is well-formed
    for f in findings:
        assert f.id and isinstance(f.id, str)
        assert f.recommendation in ("strip", "keep")
        assert set(f.span) == {"start", "end"} and 0 <= f.span["start"] <= f.span["end"] <= len(doc)
        assert f.genre == audit.genre
        assert f.verifier_precheck["status"] in ("deterministic_pass", "blocked", "n/a")


def test_finding_ids_are_unique(tmp_path):
    # two same-metric tells on one line must NOT collide on f"{metric}:{start_byte}" (#58 dup-id guard)
    audit, doc = _audit(tmp_path, _CADENCE_DOC)
    ids = [f.id for f in build_findings(audit, doc)]
    assert len(ids) == len(set(ids)), f"duplicate finding ids: {ids}"


def test_keep_recommendation_proposes_no_rewrite(tmp_path):
    # under spec the cadence tell is KEPT: recommendation keep, no proposed rewrite, precheck n/a.
    audit, doc = _audit(tmp_path, _CADENCE_DOC, genre="spec")
    cadence = [f for f in build_findings(audit, doc) if f.category == "negative_parallelism"]
    assert cadence, "the repetition paragraph flags negative_parallelism"
    for f in cadence:
        assert f.recommendation == "keep"
        assert f.proposed_rewrite is None
        assert f.verifier_precheck["status"] == "n/a"


def test_strip_recommendation_on_clean_span_prechecks_deterministic_pass(tmp_path):
    # under general the transition-cluster tell is STRIPPED; the span has no protected span / invariant
    # so the candidate delete passes verifier Layers 1+2 -> status "deterministic_pass" (decision
    # ACCEPT). The label is NON-authorizing: proposal_status stays BLOCKED + semantic_status not_run,
    # so a P3 consumer cannot read it as "shippable".
    audit, doc = _audit(tmp_path, _TRANSITION_DOC, genre="general")
    tc = [f for f in build_findings(audit, doc) if f.category == "transition_clusters"]
    assert tc, "the However/Furthermore paragraph flags transition_clusters"
    f = tc[0]
    assert f.recommendation == "strip"
    assert f.proposed_rewrite is not None
    assert f.verifier_precheck["status"] == "deterministic_pass"
    assert f.verifier_precheck["decision"] == "ACCEPT"
    assert f.verifier_precheck["proposal_status"] == "BLOCKED"   # NOT shippable (semantic not run)
    assert f.verifier_precheck["semantic_status"] == "not_run"


def test_strip_that_would_drop_an_invariant_prechecks_blocked(tmp_path):
    # the cadence paragraph's "X, NOT Y" clauses are NEGATION invariants; deleting the whole unit would
    # drop them, so the verifier BLOCKS the strip candidate (decision != ACCEPT). This is the expected,
    # correct outcome the review UI surfaces per finding — a strip is a candidate, never asserted safe.
    audit, doc = _audit(tmp_path, _CADENCE_DOC, genre="general")
    cadence = [f for f in build_findings(audit, doc) if f.category == "negative_parallelism"]
    assert cadence
    f = cadence[0]
    assert f.recommendation == "strip"
    assert f.verifier_precheck["status"] == "blocked"
    assert f.verifier_precheck["decision"] != "ACCEPT"


def test_finding_span_covers_full_multiline_passage(tmp_path):
    # #59 T3 8a (correctness HIGH): a location on a multi-line/soft-wrapped paragraph must span the
    # whole passage (its containing Unit), not just the first physical line. Six metrics record only
    # line_start, so a naive line-based span would cover one line; resolving to the Unit fixes it and
    # makes the finding span byte-identical to the pipeline's authorized range.
    from slopslap_scan.diagnoses import authorized_ranges_from_diagnoses
    para = "\n".join(f"We choose {w} thing, not other thing here." for w in "abcdef")
    audit, doc = _audit(tmp_path, f"Clean intro line here.\n\n{para}\n", genre="general")
    fs = [f for f in build_findings(audit, doc) if f.category == "negative_parallelism"]
    # dedup: all 6 same-metric tells resolve to the same containing-unit span -> exactly ONE finding.
    assert len(fs) == 1, "same-(metric,span) tells collapse to one finding"
    f = fs[0]
    start, end = f.span["start"], f.span["end"]
    assert end - start > 100, "span must cover the whole multi-line paragraph, not just line 1"
    ranges = authorized_ranges_from_diagnoses(doc, "markdown", "general")
    assert {(r["start_byte"], r["end_byte"]) for r in ranges} == {(start, end)}


def test_same_span_tells_dedup_and_ids_unique(tmp_path):
    # a single paragraph with many same-metric tells -> one finding per (metric, span), ids unique.
    para = ". ".join(f"choose {w} thing, not other thing" for w in "abcdef") + "."
    audit, doc = _audit(tmp_path, para, genre="general", fmt="text", name="d.txt")
    fs = build_findings(audit, doc)
    ids = [f.id for f in fs]
    assert len(ids) == len(set(ids))
    # negative_parallelism (6 hits, one paragraph) collapses to a single finding
    npf = [f for f in fs if f.category == "negative_parallelism"]
    assert len(npf) == 1


def test_doc_bytes_must_match_audit_sha(tmp_path):
    audit, doc = _audit(tmp_path, _CADENCE_DOC)
    assert hashlib.sha256(doc).hexdigest() == audit.source_sha256  # sanity
    with pytest.raises(FindingsError):
        build_findings(audit, doc + b" tampered")
