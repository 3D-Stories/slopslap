"""P5 (#63) STRUCTURAL INVARIANT: "recommendations may learn; authorization never does."

These are the tests the issue demands ("Tests pin this"). They prove the learned overlay can only
tune the RECOMMENDATION the user reviews, keep-only, and can never reach authorization or the verifier.
"""

import base64
import json
import os

from slopslap_apply.backup import BackupConfig
from slopslap_assemble.assemble import apply_from_decisions, audit_document
from slopslap_corpus.learn import Overlay, apply_overlay, learn_from_feedback
from slopslap_review.findings import build_findings
from slopslap_review.review import build_review_payload, decisions_from_actions
from slopslap_scan.metrics import METRIC_CLASS
from eval.loader import VALID_GENRES

_CLEAN_STRIP = ("Intro line here.\n\n"
                "However it works well. Furthermore it scales up. Moreover it helps a lot. "
                "However it stays fast. Furthermore it feels clean.\n")


def _stub(o, r, l):
    return {"verdict": "clean", "concerns": []}


def _all_keep_overlay():
    classes = frozenset(METRIC_CLASS.values())
    return Overlay(keep_classes={g: classes for g in VALID_GENRES})


def test_apply_overlay_is_keep_only_over_the_whole_table():
    """No (genre, metric), even with EVERY class force-kept, ever turns keep->strip; and strip only
    ever becomes keep, never the reverse."""
    ov = _all_keep_overlay()
    for metric in METRIC_CLASS:
        for genre in VALID_GENRES:
            assert apply_overlay("keep", genre, metric, ov) == "keep"     # keep stays keep, always
            assert apply_overlay("strip", genre, metric, ov) == "keep"    # flip is strip->keep only
    # an empty overlay is a strict no-op
    empty = Overlay(keep_classes={})
    for metric in METRIC_CLASS:
        assert apply_overlay("strip", "general", metric, empty) == "strip"


def test_learned_keep_does_not_block_a_user_authorized_apply(tmp_path):
    """The load-bearing demonstration: learning flips a finding's recommendation to keep, yet a user
    who authorizes 'apply' STILL gets the edit applied — authorization is the user's decision, never
    the (learned) recommendation."""
    p = tmp_path / "doc.md"
    p.write_text(_CLEAN_STRIP, encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data

    # a ledger that flips the filler class (transition_clusters) to keep in 'general'
    lines = [{"ts": "2026-07-14T16:00:00Z", "finding_id": "transition_clusters:x",
              "category": "filler", "metric": "transition_clusters", "genre": "general",
              "recommendation": "strip", "user_action": "discard", "doc_sha": "0" * 64}
             for _ in range(3)]
    overlay = learn_from_feedback(lines, min_evidence=3)

    learned = build_findings(audit, p.read_bytes(), overlay=overlay)
    tc = next(f for f in learned if f.category == "transition_clusters")
    assert tc.recommendation == "keep"                     # learning flipped the RECOMMENDATION

    # the user OVERRIDES with an explicit apply → the edit is authorized + applied regardless
    payload = build_review_payload(audit, p.read_bytes(), build_findings(audit, p.read_bytes()))
    actions = {f["id"]: {"action": "apply"} for f in payload["findings"] if f["category"] == "transition_clusters"}
    dj = tmp_path / "d.json"
    dj.write_text(json.dumps(decisions_from_actions(payload, actions)), encoding="utf-8")
    before = p.read_bytes()
    run = apply_from_decisions(str(p), str(dj), declared_genre="general", semantic_fn=_stub, write=True,
                               apply_config=BackupConfig(root=str(tmp_path / "b")))
    assert run.status == "ok" and p.read_bytes() != before  # authorization won over the learned keep


def test_learning_seam_not_imported_by_authorization_or_verifier():
    """Structural: the recommendation-tuning seam (apply_overlay) appears ONLY in the review layer,
    never in the authorization (assemble) or verifier (verification) modules."""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # glob the WHOLE authorization + verifier packages (+ the diagnosis seam) so a future importer in
    # ANY file there is caught, not just the three that exist today (Step-8a reviewer note).
    targets = (glob.glob(os.path.join(root, "scripts/slopslap_assemble/*.py"))
               + glob.glob(os.path.join(root, "scripts/slopslap_verification/*.py"))
               + [os.path.join(root, "scripts/slopslap_scan/diagnoses.py")])
    assert len(targets) >= 5
    for path in targets:
        src = open(path, encoding="utf-8").read()
        rel = os.path.relpath(path, root)
        assert "apply_overlay" not in src, f"{rel} must not touch the learned recommendation overlay"
        assert "slopslap_corpus.learn" not in src and "import learn" not in src, rel


def test_verify_signature_has_no_overlay_or_feedback():
    """The verifier can never consume learning: its signature carries no overlay/feedback parameter."""
    import inspect

    from slopslap_verification.ledger import verify
    params = set(inspect.signature(verify).parameters)
    assert not (params & {"overlay", "feedback", "learned", "learn"})


def test_voice_floor_flips_voice_class_but_never_reaches_verifier():
    """Voice-floor: repeated personal voice_punctuation keeps flip that class to keep in the review
    recommendation (protecting a demonstrated voice), and that flip lives only in the recommendation —
    the verifier (checked above) can't see it."""
    lines = [{"ts": "2026-07-14T16:00:00Z", "finding_id": "punctuation_rates:x", "category": "voice_punctuation",
              "metric": "punctuation_rates", "genre": "personal", "recommendation": "strip",
              "user_action": "discard", "reason": "keep_voice", "doc_sha": "0" * 64} for _ in range(3)]
    ov = learn_from_feedback(lines, min_evidence=3)
    assert apply_overlay("strip", "personal", "punctuation_rates", ov) == "keep"   # voice protected
    assert apply_overlay("strip", "general", "punctuation_rates", ov) == "strip"   # only in personal
