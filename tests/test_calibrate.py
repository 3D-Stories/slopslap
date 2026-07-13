"""#25 — scanner threshold calibration harness (fit on calibration, report on held-out, never tune held-out).

The reference corpus (#30) is metadata-only for its tunable items (0/8 carry verbatim text under their
licensing), so no thresholds can be fit from it yet and the scanner stays MEASURE-ONLY. These tests
prove the HARNESS mechanics against synthetic in-memory points so the fit/evaluate/never-tune-held-out
logic is real and verified, ready for when the corpus gains licensed calibration text.
"""
import pytest

from slopslap_corpus.calibrate import (
    calibrate_corpus,
    evaluate_points,
    fit_thresholds,
)


def _pt(metric, value, positive, genre="general", length="short", tell="t"):
    return {"metric": metric, "value": value, "positive": positive,
            "genre": genre, "length": length, "tell": tell}


# ---- fit: chooses a separating threshold on the calibration points ----
def test_fit_separates_positive_from_negative():
    pts = [_pt("rule_of_three", 0.9, True), _pt("rule_of_three", 0.8, True),
           _pt("rule_of_three", 0.1, False), _pt("rule_of_three", 0.2, False)]
    th = fit_thresholds(pts)
    assert "rule_of_three" in th
    # a value between the negative cluster (<=0.2) and positive cluster (>=0.8) separates them
    assert 0.2 < th["rule_of_three"]["threshold"] <= 0.8
    assert th["rule_of_three"]["f1"] == 1.0            # perfectly separable set -> F1 1.0


def test_fit_skips_metric_with_no_negatives():
    # a metric with only positives cannot be calibrated (no separation signal) -> abstain, not a bogus 0
    pts = [_pt("em_dash", 0.5, True), _pt("em_dash", 0.7, True)]
    th = fit_thresholds(pts)
    assert th["em_dash"]["threshold"] is None and th["em_dash"]["reason"] == "insufficient_labels"


# ---- evaluate: per-stratum precision/recall/abstention on held-out, NEVER mutates thresholds ----
def test_evaluate_reports_per_stratum_and_does_not_tune():
    thresholds = {"rule_of_three": {"threshold": 0.5, "f1": 1.0}}
    import copy
    frozen = copy.deepcopy(thresholds)
    held = [_pt("rule_of_three", 0.9, True, genre="spec"), _pt("rule_of_three", 0.1, False, genre="spec")]
    report = evaluate_points(held, thresholds)
    assert thresholds == frozen, "evaluate must NOT tune/mutate the thresholds on held-out data"
    strat = report["by_stratum"]
    assert any(k[0] == "genre" and k[1] == "spec" for k in strat) or "genre:spec" in strat
    overall = report["overall"]
    assert overall["precision"] == 1.0 and overall["recall"] == 1.0   # 0.9>=0.5 TP, 0.1<0.5 TN


def test_evaluate_abstains_on_uncalibrated_metric():
    # a held-out point whose metric has threshold=None is an ABSTENTION, not a false verdict
    thresholds = {"em_dash": {"threshold": None, "reason": "insufficient_labels"}}
    report = evaluate_points([_pt("em_dash", 0.9, True)], thresholds)
    assert report["overall"]["abstained"] == 1
    assert report["overall"]["precision"] is None      # nothing decided -> no precision claim


# ---- corpus orchestration: honest coverage when the corpus lacks verbatim text ----
def test_calibrate_corpus_reports_empty_data_measure_only():
    # a manifest whose tunable items have no verbatim text -> 0 usable points -> measure_only verdict
    manifest = [
        {"item_id": "a", "split": "calibration", "tells": ["rule_of_three"], "genre": "encyclopedic",
         "control": False, "source_family": "fam1", "verbatim_path": None},
        {"item_id": "b", "split": "held_out", "tells": ["genericness"], "genre": "technical",
         "control": False, "source_family": "fam2", "verbatim_path": None},
    ]

    def _never_called_scan(text):  # pragma: no cover - must not be reached with no text
        raise AssertionError("scan should not run on a text-less item")

    report = calibrate_corpus(manifest, scan_fn=_never_called_scan, load_text=lambda p: None)
    assert report["promoted"] is False
    assert report["verdict"] == "measure_only"
    assert report["calibration"]["usable_points"] == 0
    assert report["held_out"]["usable_points"] == 0
    assert "verbatim" in report["reason"].lower()


def test_calibrate_corpus_uses_text_when_available():
    # when text IS present, the harness fits on calibration + evaluates on held-out (mechanics live)
    manifest = [
        {"item_id": "p1", "split": "calibration", "tells": ["rule_of_three"], "genre": "general",
         "control": False, "source_family": "f1", "verbatim_path": "p1.md"},
        {"item_id": "n1", "split": "calibration", "tells": [], "genre": "general",
         "control": True, "source_family": "f2", "verbatim_path": "n1.md"},
        {"item_id": "h1", "split": "held_out", "tells": ["rule_of_three"], "genre": "general",
         "control": False, "source_family": "f3", "verbatim_path": "h1.md"},
    ]
    # scan_fn returns a metrics dict; rule_of_three rate high for positives, low for the control
    def _scan(text):
        rate = 0.9 if text == "POS" else 0.0
        return {"rule_of_three": {"rate": rate, "soft_flag": rate > 0.5}}
    def _load(path):
        return "POS" if path in ("p1.md", "h1.md") else "NEG"

    report = calibrate_corpus(manifest, scan_fn=_scan, load_text=_load)
    assert report["calibration"]["usable_points"] == 2
    assert report["held_out"]["usable_points"] == 1
    # measure-only stays the default until an explicit validation bar is met (n far too small here)
    assert report["promoted"] is False and report["verdict"] == "measure_only"
