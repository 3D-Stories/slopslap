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
        "breakdown": {"shipped": 2, "not_authorized": 86, "excluded_third_party": 2, "abstained": 7,
                      "dropped_on_anonymization": 4}, "items": []}))
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
    """The old 31-item ledger: 18 authorized (the circular exclusion was authorized first), not 17."""
    ledger = tmp_path / "sampled.json"
    ledger.write_text(json.dumps({
        "schema_version": 1, "sampled": 31, "count": 28,
        "breakdown": {"not_authorized": 13, "abstained": 11, "shipped": 3, "verifier_blocked": 3,
                      "excluded_circular": 1}, "items": []}))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(ledger), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    for row in ("| sampled | 31 |", "| authorized | 18 |", "| repaired | 3 |", "| paired | 2 |"):
        assert row in text, row


def test_report_without_a_ledger_still_opens_with_the_funnel_heading(fixtures, tmp_path):
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert text.index("## Abstention funnel") < text.index("## Method")
    assert "Sampling: not recorded for this run" in text


# ------------------------------------------------------------------ Step 11 re-run findings (F0, F3, F5)
def test_loader_refuses_a_fixture_with_no_source_contract(tmp_path):
    """F3: the provenance boundary must fail CLOSED. A manifest with no `eval_pair.source`, or one of an
    unknown shape, is not admissible — path and header detection stay as an extra deny-list only."""
    root = _root(tmp_path)
    d = _write_pair(root, "pair-102-01-nosrc", ALPHA_O, ALPHA_A)
    _patch_manifest(d, lambda m: m["eval_pair"].pop("source", None))
    with pytest.raises(P.PairError, match="source"):
        P.load_eval_pairs(str(root))
    _patch_manifest(d, lambda m: m["eval_pair"].__setitem__("source", {"kind": "scraped", "document": "x"}))
    with pytest.raises(P.PairError, match="source"):
        P.load_eval_pairs(str(root))
    _patch_manifest(d, lambda m: m["eval_pair"].__setitem__("source", {
        "kind": "owner-supplied", "document": "an internal handbook", "anonymized": False,
        "license": "owner-granted", "extract_id": "p001"}))
    with pytest.raises(P.PairError, match="anonymized"):
        P.load_eval_pairs(str(root))


def test_report_refuses_to_publish_a_percentage_without_a_ledger(fixtures, tmp_path, monkeypatch):
    """F0: a preference percentage with no funnel has no denominator, so `report` refuses --judge or
    --picks unless --abstentions supplies a ledger. A fixture-only render (no percentage) still works."""
    monkeypatch.delenv("SLOPSLAP_LIVE", raising=False)
    from test_preference import _Transport
    jf = tmp_path / "judge.json"
    P.main(["judge", "--fixtures", str(fixtures), "--model", "m", "--out", str(jf)], judge_transport=_Transport([]))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--judge", str(jf), "--out", str(md)]) == 2
    assert not md.exists()
    ledger = tmp_path / "sampled.json"
    ledger.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3, "breakdown": {"shipped": 2, "not_authorized": 3},
                                  "funnel": [{"stage": "sampled", "count": 5}, {"stage": "authorized", "count": 2},
                                             {"stage": "repaired", "count": 2}, {"stage": "paired", "count": 2}], "items": []}))
    assert P.main(["report", "--fixtures", str(fixtures), "--judge", str(jf), "--abstentions", str(ledger), "--out", str(md)]) == 0


def test_report_refuses_a_ledger_whose_numbers_do_not_add_up(fixtures, tmp_path):
    md = tmp_path / "r.md"
    bad = tmp_path / "bad.json"
    # breakdown does not sum to sampled
    bad.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3, "breakdown": {"shipped": 2, "not_authorized": 2}, "items": []}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(bad), "--out", str(md)]) == 2
    # funnel's last row is not this fixture set's pair count
    bad.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3, "breakdown": {"shipped": 2, "not_authorized": 3},
                               "funnel": [{"stage": "sampled", "count": 5}, {"stage": "paired", "count": 3}], "items": []}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(bad), "--out", str(md)]) == 2
    # funnel not monotonic
    bad.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3, "breakdown": {"shipped": 2, "not_authorized": 3},
                               "funnel": [{"stage": "sampled", "count": 5}, {"stage": "authorized", "count": 6}, {"stage": "paired", "count": 2}], "items": []}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(bad), "--out", str(md)]) == 2


def test_derived_funnel_counts_authorized_from_items_when_present(fixtures, tmp_path):
    """F5: an excluded paragraph may still have been AUTHORIZED (the old ledger's circular one was), so
    the derived authorized row comes from item-level authorization when items exist."""
    ledger = tmp_path / "sampled.json"
    items = ([{"authorization": "authorized", "disposition": "shipped"}] * 2
             + [{"authorization": "authorized", "disposition": "excluded_circular"}]
             + [{"authorization": "reject_all", "disposition": "not_authorized"}] * 2)
    ledger.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3,
                                  "breakdown": {"shipped": 2, "excluded_circular": 1, "not_authorized": 2}, "items": items}))
    md = tmp_path / "r.md"
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(ledger), "--out", str(md)]) == 0
    text = md.read_text(encoding="utf-8")
    assert "| authorized | 3 |" in text


def test_report_refuses_a_ledger_whose_items_disagree_with_its_summary(fixtures, tmp_path):
    """D4: with items present, `breakdown` and the explicit funnel are assertions about them."""
    md = tmp_path / "r.md"
    bad = tmp_path / "bad.json"
    items = ([{"authorization": "authorized", "disposition": "shipped"}] * 2
             + [{"authorization": "reject_all", "disposition": "not_authorized"}] * 3)
    # breakdown sums to sampled but names a disposition the items do not have
    bad.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3,
                               "breakdown": {"shipped": 2, "abstained": 3}, "items": items}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(bad), "--out", str(md)]) == 2
    # funnel says 4 authorized; the items say 2
    bad.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3,
                               "breakdown": {"shipped": 2, "not_authorized": 3},
                               "funnel": [{"stage": "sampled", "count": 5}, {"stage": "authorized", "count": 4},
                                          {"stage": "repaired", "count": 2}, {"stage": "paired", "count": 2}],
                               "items": items}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(bad), "--out", str(md)]) == 2
    # consistent: accepted
    bad.write_text(json.dumps({"schema_version": 1, "sampled": 5, "count": 3,
                               "breakdown": {"shipped": 2, "not_authorized": 3},
                               "funnel": [{"stage": "sampled", "count": 5}, {"stage": "authorized", "count": 2},
                                          {"stage": "repaired", "count": 2}, {"stage": "paired", "count": 2}],
                               "items": items}))
    assert P.main(["report", "--fixtures", str(fixtures), "--abstentions", str(bad), "--out", str(md)]) == 0
