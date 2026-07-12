"""MVP scanner metrics. Each returns a flat result (design R5):
{eligible_units, count, rate, locations, soft_flag, metric_version, extraction_profile,
 confidence, purpose} (+ optional distribution/dispersion for the distribution metric).

Confidence tiers (peer consult): normal (distribution/dispersion, punctuation, paragraph
runs, bold-label), medium (repeated openers, transition clusters), low (vague attribution,
stock clusters — soft_flag may be null until corpus evidence). All are candidate-selection
aids; the scanner NEVER verdicts.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Dict, List

from .extract import Unit, split_sentences, unit_sentences, words
from .tables import (
    DUALITY_TEMPLATES,
    STOCK_CLUSTERS,
    TABLES_VERSION,
    TRANSITION_OPENERS,
    VAGUE_ATTRIBUTION,
)

PURPOSE = "candidate_selection_only"


def _result(eligible, count, rate, locations, soft_flag, confidence, version, **extra):
    r = {
        "eligible_units": eligible,
        "count": count,
        "rate": rate,
        "locations": locations,
        "soft_flag": soft_flag,
        "metric_version": version,
        "confidence": confidence,
        "purpose": PURPOSE,
    }
    r.update(extra)
    return r


def _pct(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])
    return float(sorted_vals[lo])


def _sentences(units: List[Unit]):
    return unit_sentences(units)


def sentence_length_distribution(units, sw) -> Dict:
    lengths = sorted(len(words(s)) for s, _ in sw)
    n = len(lengths)
    dist = None
    if n:
        dist = {
            "min": lengths[0], "p10": _pct(lengths, 0.10), "p25": _pct(lengths, 0.25),
            "median": _pct(lengths, 0.50), "p75": _pct(lengths, 0.75),
            "p90": _pct(lengths, 0.90), "max": lengths[-1],
            "mean": round(statistics.mean(lengths), 3),
            "sd": round(statistics.pstdev(lengths), 3) if n > 1 else 0.0,
        }
    return _result(n, n, None, [], None, "normal", "sent-dist-v1", distribution=dist)


def sentence_length_dispersion(units, sw) -> Dict:
    lengths = [len(words(s)) for s, _ in sw]
    n = len(lengths)
    disp = None
    if n >= 2:
        srt = sorted(lengths)
        iqr = _pct(srt, 0.75) - _pct(srt, 0.25)
        med = _pct(srt, 0.50)
        mean = statistics.mean(lengths)
        adj = [abs(lengths[i] - lengths[i - 1]) for i in range(1, n)]
        disp = {
            "iqr_over_median": round(iqr / med, 3) if med else None,
            "cov": round(statistics.pstdev(lengths) / mean, 3) if mean else None,
            "median_adjacent_diff": statistics.median(adj) if adj else 0,
        }
    return _result(n, n, None, [], None, "normal", "sent-disp-v1", dispersion=disp)


def punctuation_rates(units, sw) -> Dict:
    text = " ".join(u.text for u in units)
    wc = len(words(text))
    em = text.count("—") + len(re.findall(r"(?<!-)--(?!-)", text))
    semi = text.count(";")
    per1k = lambda c: round(1000.0 * c / wc, 3) if wc else 0.0
    return _result(
        wc, em + semi, None, [], None, "normal", "punct-v1",
        rates={"em_dash_per_1k": per1k(em), "semicolon_per_1k": per1k(semi),
               "em_dash": em, "semicolon": semi},
    )


def paragraph_sentence_count_runs(units, sw) -> Dict:
    paras = [u for u in units if u.structural_type == "paragraph"]
    counts = [(u, len(split_sentences(u.text))) for u in paras]
    runs, locations = 0, []
    i = 0
    while i < len(counts):
        j = i
        while j + 1 < len(counts) and counts[j + 1][1] == counts[i][1] and counts[i][1] >= 1:
            j += 1
        if j - i + 1 >= 3:
            runs += 1
            locations.append({
                "line_start": counts[i][0].line_start,
                "line_end": counts[j][0].line_end,
                "sentences_each": counts[i][1],
                "paragraphs": j - i + 1,
            })
        i = j + 1
    return _result(len(paras), runs, None, locations, runs > 0, "normal", "para-runs-v1")


def bold_label_density(units, sw) -> Dict:
    # counted from EXTRACTED eligible units (a **label**: opener detected via tokens), so labels
    # inside excluded code/blockquote/HTML never count (WF5-diff H1). Text-path units are never
    # labels (bold-label is a Markdown structural concept).
    blocks = [u for u in units if u.structural_type in ("paragraph", "list_item")]
    labels = [u for u in blocks if u.is_label]
    denom = max(1, len(blocks))
    locs = [{"line_start": u.line_start, "line_end": u.line_end} for u in labels]
    return _result(len(blocks), len(labels), round(len(labels) / denom, 3), locs,
                   None, "normal", "bold-label-v2")


def _opener_tokens(sentence):
    return [t.lower().replace("’", "'") for t in words(sentence)]


def repeated_openers(units, sw) -> Dict:
    """Deterministic gap<=7 cluster events over normalized 1/2/3-token openers (design R2)."""
    prefixes_per = []
    for s, _ in sw:
        toks = _opener_tokens(s)
        prefs = set()
        if len(toks) >= 2:
            for L in (1, 2, 3):
                if len(toks) >= L:
                    prefs.add((L, " ".join(toks[:L])))
        prefixes_per.append(prefs)
    occ = defaultdict(list)
    for i, prefs in enumerate(prefixes_per):
        for p in prefs:
            occ[p].append(i)
    events = []
    for p, idxs in occ.items():
        idxs.sort()
        cluster = [idxs[0]]
        for a in idxs[1:]:
            if a - cluster[-1] <= 7:
                cluster.append(a)
            else:
                if len(cluster) >= 3:
                    events.append((p, cluster))
                cluster = [a]
        if len(cluster) >= 3:
            events.append((p, cluster))
    locations = [{
        "prefix": p[1], "prefix_len": p[0],
        "line_start": sw[g[0]][1].line_start, "line_end": sw[g[-1]][1].line_end,
        "sentences": len(g),
    } for p, g in events]
    return _result(len(sw), len(events), None, locations, len(events) > 0, "medium", "openers-v1")


def transition_clusters(units, sw) -> Dict:
    total_words = sum(len(words(u.text)) for u in units)
    hits = []
    for s, u in sw:
        low = s.strip().lower()
        for opener in TRANSITION_OPENERS:
            if low.startswith(opener):
                nxt = low[len(opener) : len(opener) + 1]
                if nxt == "" or not nxt.isalpha():
                    hits.append({"opener": opener, "line_start": u.line_start})
                    break
    rate = round(1000.0 * len(hits) / total_words, 3) if total_words else 0.0
    return _result(total_words, len(hits), rate, hits, len(hits) > 0, "medium", "transition-v1")


def _phrase_scan(units, phrases):
    hits = []
    for u in units:
        low = u.text.lower()
        for ph in phrases:
            for _m in re.finditer(r"\b" + re.escape(ph) + r"\b", low):
                hits.append({"phrase": ph, "line_start": u.line_start})
    return hits


def vague_attribution(units, sw) -> Dict:
    hits = _phrase_scan(units, VAGUE_ATTRIBUTION)
    # low confidence: soft_flag stays null until corpus evidence
    return _result(len(units), len(hits), None, hits, None, "low", "vague-attr-" + TABLES_VERSION)


def stock_lexical_clusters(units, sw) -> Dict:
    hits = []
    for u in units:
        low = u.text.lower()
        for cluster, phrases in STOCK_CLUSTERS.items():
            for ph in phrases:
                for _m in re.finditer(r"\b" + re.escape(ph) + r"\b", low):
                    hits.append({"cluster": cluster, "phrase": ph, "line_start": u.line_start})
        for tmpl in DUALITY_TEMPLATES:
            for _m in re.finditer(tmpl, low):
                hits.append({"cluster": "duality_framing", "phrase": _m.group(0)[:60],
                             "line_start": u.line_start})
    return _result(len(units), len(hits), None, hits, None, "low", "stock-" + TABLES_VERSION)


ALL_METRICS = [
    ("sentence_length_distribution", sentence_length_distribution),
    ("sentence_length_dispersion", sentence_length_dispersion),
    ("punctuation_rates", punctuation_rates),
    ("paragraph_sentence_count_runs", paragraph_sentence_count_runs),
    ("bold_label_density", bold_label_density),
    ("repeated_openers", repeated_openers),
    ("transition_clusters", transition_clusters),
    ("vague_attribution", vague_attribution),
    ("stock_lexical_clusters", stock_lexical_clusters),
]


def compute_all(units: List[Unit], extraction_profile: str, source: str = "") -> Dict:
    sw = _sentences(units)
    out = {}
    for name, fn in ALL_METRICS:
        res = fn(units, sw)
        res["extraction_profile"] = extraction_profile
        out[name] = res
    return out
