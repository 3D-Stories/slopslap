"""#25 — scanner threshold calibration harness.

The scanner ships 11 metrics whose soft-flag thresholds are un-calibrated guesses
(`purpose="candidate_selection_only"`). This harness fits a per-metric threshold on the corpus
CALIBRATION partition ONLY, then reports precision / recall / abstention per stratum (tell / genre /
length) on the HELD-OUT partition — and NEVER tunes against held-out (the disjoint #30 split is what
keeps that honest). Thresholds stay MEASURE-ONLY until an explicit validation bar is met; this harness
does not promote them into the scanner.

Reality as of #25: the committed reference corpus is metadata-only for its tunable items (0 carry
verbatim text under their licensing), so `calibrate_corpus` reports 0 usable points and a
`measure_only` verdict — the honest state, not a fabricated calibration. The mechanics
(`fit_thresholds` / `evaluate_points`) are unit-tested against synthetic points and fire for real the
moment the corpus gains licensed calibration text. The eval FIXTURES are deliberately NOT used as a
calibration source — that is the train/test leak the #30 split exists to prevent.
"""
from __future__ import annotations

from typing import Callable, List, Optional

# Promotion bar: a metric needs at least this many usable calibration points (positives AND negatives)
# before a fitted threshold could even be considered — and promotion still requires human sign-off.
# Set deliberately high relative to the current corpus so nothing auto-promotes on thin data.
_MIN_POINTS_PER_METRIC = 20

# Provisional scanner-metric -> corpus-tell map (which tell each metric is evidence FOR). Used to
# label a scanned item positive/negative for a metric. Judgment-y and provisional — revisit when the
# corpus gains verbatim text and real per-stratum numbers can validate each mapping. A scanned metric
# NOT in this map is SKIPPED (never identity-mislabeled against a mismatched tell name).
DEFAULT_METRIC_TELL_MAP = {
    "rule_of_three": "rule_of_three",
    "negative_parallelism": "synthetic_cadence",
    "sentence_length_distribution": "synthetic_cadence",
    "sentence_length_dispersion": "synthetic_cadence",
    "paragraph_sentence_count_runs": "synthetic_cadence",
    "repeated_openers": "synthetic_cadence",
    "transition_clusters": "synthetic_cadence",
    "punctuation_rates": "em_dash_overuse",
    "vague_attribution": "genericness",
    "stock_lexical_clusters": "lexical_structural",
    "bold_label_density": "lexical_structural",
    "generic_diction": "genericness",
}


def _f1(tp: int, fp: int, fn: int) -> float:
    denom = 2 * tp + fp + fn
    return (2 * tp) / denom if denom else 0.0


def fit_thresholds(points: List[dict]) -> dict:
    """Fit one threshold per metric on labeled calibration points.

    ``points``: ``[{"metric","value","positive"(bool), ...}]``. For each metric, pick the threshold
    (a candidate midpoint between sorted values) that maximizes F1 separating positives (value should
    be >= threshold) from negatives. A metric lacking BOTH a positive and a negative example cannot be
    calibrated → ``threshold=None, reason="insufficient_labels"`` (abstain, never a bogus 0).
    """
    by_metric: dict[str, list[dict]] = {}
    for p in points:
        by_metric.setdefault(p["metric"], []).append(p)

    out: dict[str, dict] = {}
    for metric, pts in by_metric.items():
        pos = [p["value"] for p in pts if p["positive"]]
        neg = [p["value"] for p in pts if not p["positive"]]
        if not pos or not neg:
            out[metric] = {"threshold": None, "f1": None, "reason": "insufficient_labels",
                           "n_pos": len(pos), "n_neg": len(neg)}
            continue
        # candidate thresholds: midpoints between adjacent sorted unique values (+ the extremes)
        vals = sorted({p["value"] for p in pts})
        cands = [vals[0] - 1e-9] + [(a + b) / 2 for a, b in zip(vals, vals[1:])] + [vals[-1] + 1e-9]
        best_t, best_f1 = None, -1.0
        for t in cands:
            tp = sum(1 for v in pos if v >= t)
            fp = sum(1 for v in neg if v >= t)
            fn = sum(1 for v in pos if v < t)
            f1 = _f1(tp, fp, fn)
            if f1 > best_f1:
                best_t, best_f1 = t, f1
        out[metric] = {"threshold": round(best_t, 6), "f1": round(best_f1, 6),
                       "n_pos": len(pos), "n_neg": len(neg)}
    return out


def _stratum_keys(p: dict) -> list:
    return [("tell", p.get("tell", "?")), ("genre", p.get("genre", "?")),
            ("length", p.get("length", "?"))]


def _bucket() -> dict:
    return {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "abstained": 0, "n": 0}


def _score(bucket: dict) -> dict:
    tp, fp, fn, ab, n = bucket["tp"], bucket["fp"], bucket["fn"], bucket["abstained"], bucket["n"]
    # precision/recall are None (undefined) when the denominator is empty — a classifier that
    # flagged nothing (tp+fp==0) or a stratum with no positives (tp+fn==0) makes no precision/recall
    # CLAIM, rather than a misleading 1.0 (L3).
    return {
        "n": n, "abstained": ab,
        "abstention_rate": round(ab / n, 4) if n else None,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
    }


def evaluate_points(held_out: List[dict], thresholds: dict) -> dict:
    """Report precision/recall/abstention overall + per stratum on held-out points, using the fitted
    thresholds AS GIVEN — it reads them, never writes them (the never-tune-on-held-out guarantee).
    A point whose metric has ``threshold=None`` is an ABSTENTION, never a decided verdict.
    """
    overall = _bucket()
    strata: dict[str, dict] = {}
    for p in held_out:
        overall["n"] += 1
        th = thresholds.get(p["metric"], {}).get("threshold")
        keys = _stratum_keys(p)
        for axis, val in keys:
            strata.setdefault(f"{axis}:{val}", _bucket())["n"] += 1
        if th is None:
            overall["abstained"] += 1
            for axis, val in keys:
                strata[f"{axis}:{val}"]["abstained"] += 1
            continue
        flagged = p["value"] >= th
        pos = bool(p["positive"])
        cell = "tp" if (flagged and pos) else "fp" if (flagged and not pos) else "fn" if (not flagged and pos) else "tn"
        overall[cell] += 1
        for axis, val in keys:
            strata[f"{axis}:{val}"][cell] += 1
    return {"overall": _score(overall), "by_stratum": {k: _score(v) for k, v in strata.items()}}


def _points_from_items(items: List[dict], scan_fn: Callable, load_text: Callable,
                       metric_tell_map: Optional[dict] = None) -> List[dict]:
    """Scan each item that has verbatim text; emit one labeled point per (metric, item).

    Labeling per (metric, item), where the metric maps to tell T:
      - control item OR item with NO tells    -> NEGATIVE (a genuinely clean sample for every metric)
      - non-control item whose tells include T -> POSITIVE
      - non-control item flagged for OTHER tells only -> SKIP (cross-tell noise: AI slop co-occurs
        across tells, so such an item is neither a clean negative nor a positive for T — mislabeling
        it as a negative would bias the fitted threshold).
    A metric with no entry in the tell map is SKIPPED (never identity-mislabeled). Text-less items
    yield nothing.
    """
    tmap = metric_tell_map if metric_tell_map is not None else DEFAULT_METRIC_TELL_MAP
    pts: List[dict] = []
    for it in items:
        path = it.get("verbatim_path")
        text = load_text(path) if path else None
        if not text:
            continue
        metrics = scan_fn(text)
        tells = set(it.get("tells", []))
        control = bool(it.get("control"))
        length = _length_bucket(text)
        for metric, res in metrics.items():
            if metric not in tmap:
                continue  # unmapped scanner metric -> skip, never mislabel against a mismatched tell
            tell = tmap[metric]
            if control or not tells:
                positive = False              # clean/control sample: a negative for every metric
            elif tell in tells:
                positive = True               # this metric's tell is present
            else:
                continue                      # flagged for other tells only -> cross-tell, skip
            pts.append({"metric": metric, "value": float(res.get("rate") or 0.0),
                        "positive": positive, "genre": it.get("genre", "?"),
                        "length": length, "tell": tell, "item_id": it.get("item_id")})
    return pts


def _length_bucket(text: str) -> str:
    n = len(text.split())
    return "short" if n < 150 else "medium" if n < 600 else "long"


def calibrate_corpus(manifest: List[dict], scan_fn: Callable, load_text: Callable,
                     metric_tell_map: Optional[dict] = None) -> dict:
    """Orchestrate: fit on the calibration partition, evaluate on held-out, and return an honest
    report. NEVER promotes thresholds into the scanner — the verdict is always ``measure_only`` unless
    every fitted metric clears ``_MIN_POINTS_PER_METRIC`` AND a human promotes it (not automated here).
    """
    cal = [it for it in manifest if it.get("split") == "calibration"]
    held = [it for it in manifest if it.get("split") == "held_out"]
    cal_pts = _points_from_items(cal, scan_fn, load_text, metric_tell_map)
    held_pts = _points_from_items(held, scan_fn, load_text, metric_tell_map)

    thresholds = fit_thresholds(cal_pts) if cal_pts else {}
    evaluation = evaluate_points(held_pts, thresholds) if held_pts else {"overall": _score(_bucket()),
                                                                         "by_stratum": {}}

    well_calibrated = [m for m, t in thresholds.items()
                       if t.get("threshold") is not None and (t.get("n_pos", 0) + t.get("n_neg", 0)) >= _MIN_POINTS_PER_METRIC]
    if not cal_pts:
        reason = ("0 usable calibration points — the reference corpus tunable items carry no verbatim "
                  "text (metadata/inspiration-only under their licensing); eval fixtures are NOT used "
                  "(train/test leak the #30 split prevents)")
    elif not well_calibrated:
        reason = (f"no metric reached the {_MIN_POINTS_PER_METRIC}-point calibration bar; thresholds "
                  f"are illustrative only on this thin corpus")
    else:
        reason = "metrics met the point bar; promotion still requires explicit human sign-off"

    return {
        "promoted": False,   # #25 never auto-promotes; scanner stays measure-only
        "verdict": "measure_only",
        "reason": reason,
        "min_points_bar": _MIN_POINTS_PER_METRIC,
        "calibration": {"items": len(cal), "usable_points": len(cal_pts), "thresholds": thresholds},
        "held_out": {"items": len(held), "usable_points": len(held_pts), "evaluation": evaluation},
    }
