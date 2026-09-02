"""#102 — the machine-prose guards, and the funnel-first results layout.

Both cross-model review rounds missed that every shipped `pair-102-*` fixture was a paragraph of a
deepseek-authored adversarial review under design-doc-publish `docs/reviews/`, so the published
percentage measured slopslap on machine prose. Two things changed in response, and both are pinned
here rather than in a reader's head:

- `load_eval_pairs` refuses a fixture whose structured provenance names a path under `docs/reviews/`,
  whose free-text provenance does, or whose `original.md` opens with a machine-authored review header.
- The results document leads with the abstention funnel (sampled → authorized → repaired → paired),
  so no preference percentage is read without its denominator.
"""
import json

import pytest

from eval import preference as P
from test_preference import ALPHA_A, ALPHA_O, _write_pair, fixtures  # noqa: F401  (fixture re-export)


def _patch_manifest(d, fn):
    p = d / "fixture.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    fn(m)
    p.write_text(json.dumps(m, indent=1), encoding="utf-8")


def _root(tmp_path):
    root = tmp_path / "eval"
    root.mkdir()
    return root


# ------------------------------------------------------------------ the loader guards
def test_loader_refuses_a_source_path_under_docs_reviews(tmp_path):
    root = _root(tmp_path)
    d = _write_pair(root, "pair-102-01-rev", ALPHA_O, ALPHA_A)
    _patch_manifest(d, lambda m: m["eval_pair"].__setitem__("source", {
        "repo": "3D-Stories/design-doc-publish", "path": "docs/reviews/2026-08-23-x.md",
        "lines": "19-19", "commit": "0" * 40, "license": "MIT"}))
    with pytest.raises(P.PairError, match="docs/reviews/"):
        P.load_eval_pairs(str(root))


def test_loader_refuses_a_free_text_provenance_naming_docs_reviews(tmp_path):
    root = _root(tmp_path)
    d = _write_pair(root, "pair-102-01-rev", ALPHA_O, ALPHA_A)
    _patch_manifest(d, lambda m: m.__setitem__(
        "provenance", "verbatim paragraph from 3D-Stories/design-doc-publish (MIT), docs/reviews/2026-08-23-x.md lines 19-19"))
    with pytest.raises(P.PairError, match="docs/reviews/"):
        P.load_eval_pairs(str(root))


MACHINE_O = (b"# Adversarial Review\n- Reviewer: Codex (model deepseek-v4-pro)\n\n"
             b"In today's fast-paced world, the alpha service handles 100 requests per second.\n")
MACHINE_A = (b"# Adversarial Review\n- Reviewer: Codex (model deepseek-v4-pro)\n\n"
             b"The alpha service handles 100 requests per second.\n")


def test_loader_refuses_an_original_that_opens_with_a_machine_review_header(tmp_path):
    root = _root(tmp_path)
    _write_pair(root, "pair-102-01-mach", MACHINE_O, MACHINE_A)
    with pytest.raises(P.PairError, match="machine-authored"):
        P.load_eval_pairs(str(root))


def test_loader_accepts_owner_supplied_anonymized_provenance(tmp_path):
    root = _root(tmp_path)
    d = _write_pair(root, "pair-102-p008-x", ALPHA_O, ALPHA_A)
    _patch_manifest(d, lambda m: m["eval_pair"].__setitem__("source", {
        "kind": "owner-supplied", "document": "an internal handbook", "anonymized": True,
        "license": "owner-granted"}))
    assert [p.dir_name for p in P.load_eval_pairs(str(root))] == ["pair-102-p008-x"]


# ------------------------------------------------------------------ funnel-first results
def test_report_leads_with_the_abstention_funnel(fixtures, tmp_path):
    ledger = tmp_path / "sampled.json"
    ledger.write_text(json.dumps({
        "schema_version": 1, "sampled": 101, "count": 2, "selection": "owner-supplied human prose",
        "funnel": [{"stage": "sampled", "count": 101, "meaning": "m1"},
                   {"stage": "authorized", "count": 15, "meaning": "m2"},
                   {"stage": "repaired", "count": 9, "meaning": "m3"},
                   {"stage": "paired", "count": 2, "meaning": "m4"}],
        "breakdown": {"shipped": 2, "not_authorized": 86, "excluded_third_party": 2}, "items": []}))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(ledger), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert text.index("## Abstention funnel") < text.index("## Method") < text.index("## Human raters") < text.index("## LLM judge")
    assert "101 paragraphs sampled, 2 shipped as pairs" in text and "owner-supplied human prose" in text
    for row in ("| sampled | 101 |", "| authorized | 15 |", "| repaired | 9 |", "| paired | 2 |",
                "| excluded_third_party | 2 |"):
        assert row in text, row
    assert "real design-doc paragraph" not in text and "public design docs" not in text
    assert "AI %" not in text and "sloppiness score" not in text


def test_report_derives_a_funnel_from_an_older_ledger(fixtures, tmp_path):
    ledger = tmp_path / "sampled.json"
    ledger.write_text(json.dumps({
        "schema_version": 1, "sampled": 31, "count": 28,
        "breakdown": {"not_authorized": 13, "abstained": 11, "shipped": 3, "verifier_blocked": 3,
                      "excluded_circular": 1}, "items": []}))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(ledger), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    for row in ("| sampled | 31 |", "| authorized | 17 |", "| repaired | 3 |", "| paired | 2 |"):
        assert row in text, row


def test_report_without_a_ledger_still_opens_with_the_funnel_heading(fixtures, tmp_path):
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert text.index("## Abstention funnel") < text.index("## Method")
    assert "Sampling: not recorded for this run" in text
