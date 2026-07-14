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
    CORPORATE_BUZZWORDS,
    DUALITY_TEMPLATES,
    EMPTY_INTENSIFIERS,
    GENERIC_DICTION_FLAG_AT,
    NEGATIVE_PARALLELISM_FLAG_AT,
    NEGATIVE_PARALLELISM_PATTERNS,
    PUNCT_FLAG_PER_1K,
    RULE_OF_THREE_PATTERN,
    STOCK_CLUSTERS,
    TABLES_VERSION,
    TRANSITION_OPENERS,
    VAGUE_ATTRIBUTION,
)

_NEGPAR = re.compile("|".join(NEGATIVE_PARALLELISM_PATTERNS), re.IGNORECASE)
_TRICOLON = re.compile(RULE_OF_THREE_PATTERN)

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
    em_r, semi_r = per1k(em), per1k(semi)
    # candidate soft-flag when the appositive-punctuation density is high (issue #14)
    soft = (em_r > PUNCT_FLAG_PER_1K["em_dash_per_1k"]
            or semi_r > PUNCT_FLAG_PER_1K["semicolon_per_1k"])
    return _result(
        wc, em + semi, None, [], soft, "normal", "punct-v2",
        rates={"em_dash_per_1k": em_r, "semicolon_per_1k": semi_r, "em_dash": em, "semicolon": semi},
        thresholds=PUNCT_FLAG_PER_1K,
    )


def negative_parallelism(units, sw) -> Dict:
    """'X, not Y' / 'not X, but Y' cadence tic — medium confidence (issue #14)."""
    wc = sum(len(words(u.text)) for u in units)
    hits = []
    for u in units:
        for m in _NEGPAR.finditer(u.text):
            hits.append({"match": re.sub(r"\s+", " ", m.group(0))[:48], "line_start": u.line_start})
    rate = round(1000.0 * len(hits) / wc, 3) if wc else 0.0
    return _result(wc, len(hits), rate, hits[:25], len(hits) >= NEGATIVE_PARALLELISM_FLAG_AT,
                   "medium", "negparallel-v1", thresholds={"flag_at_count": NEGATIVE_PARALLELISM_FLAG_AT})


def rule_of_three(units, sw) -> Dict:
    """'A, B, and C' tricolon heuristic — low confidence, soft_flag null (issue #14)."""
    hits = []
    for u in units:
        for m in _TRICOLON.finditer(u.text):
            hits.append({"match": re.sub(r"\s+", " ", m.group(0))[:48], "line_start": u.line_start})
    return _result(len(units), len(hits), None, hits[:25], None, "low", "tricolon-v1")


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


def generic_diction(units, sw) -> Dict:
    """Corporate-slop buzzwords + empty intensifiers — the generic-diction / filler payload (#60,
    pivot P2; the "finds more" surface v0.2 missed). Measure-only: each match is a candidate for the
    genre recommendation layer, never a verdict, and the user's review decision authorizes any strip.
    Patterns are escaped word-boundary literals over lowercased unit text (no ReDoS)."""
    hits = []
    for u in units:
        low = u.text.lower()
        for word in CORPORATE_BUZZWORDS:
            for _m in re.finditer(r"\b" + re.escape(word) + r"\b", low):
                hits.append({"word": word, "kind": "buzzword", "line_start": u.line_start})
        for word in EMPTY_INTENSIFIERS:
            for _m in re.finditer(r"\b" + re.escape(word) + r"\b", low):
                hits.append({"word": word, "kind": "intensifier", "line_start": u.line_start})
    return _result(len(units), len(hits), None, hits, len(hits) >= GENERIC_DICTION_FLAG_AT,
                   "medium", "generic-diction-" + TABLES_VERSION)


ALL_METRICS = [
    ("sentence_length_distribution", sentence_length_distribution),
    ("sentence_length_dispersion", sentence_length_dispersion),
    ("punctuation_rates", punctuation_rates),
    ("negative_parallelism", negative_parallelism),
    ("rule_of_three", rule_of_three),
    ("paragraph_sentence_count_runs", paragraph_sentence_count_runs),
    ("bold_label_density", bold_label_density),
    ("repeated_openers", repeated_openers),
    ("transition_clusters", transition_clusters),
    ("vague_attribution", vague_attribution),
    ("stock_lexical_clusters", stock_lexical_clusters),
    ("generic_diction", generic_diction),
]


# ---- genre recommendation layer (issue #59, keystone v2) ------------------
# Keystone v2 FLIP: genre NEVER zeroes a metric's ``locations``/``soft_flag`` anymore. Detection is
# universal — the scanner emits every tell as measured. Genre (and, later, learned feedback) only
# SET each finding's advisory ``recommend``ation (strip|keep); the user's review decision authorizes
# and the byte-exact verifier hard-gates. Genre never authorizes an edit. (This replaces the pre-#59
# ``GENRE_SUPPRESS`` mechanic, which zeroed a genre-preserved metric's locations in place.)
#
# Option C (owner 2026-07-14): the recommendation is keyed by (genre, metric-CLASS) so a future
# detector (#60 generic-diction/filler) plugs into a named class without a re-do. The keep-CLASS sets
# are SEEDED from the prior per-metric suppress profiles — what a genre used to suppress (preserve) it
# now recommends keep; everything else strips — so behavior is byte-identical to pre-#59 for the
# 4 genres the classifier emits.

# every scanner metric (+ the prd-only ``adjective_requirements``) maps to exactly one class. A drift
# guard (test_genre) asserts full coverage; the runtime default for an unmapped metric is the
# asymmetric-failure-safe ``keep``.
METRIC_CLASS = {
    "negative_parallelism": "cadence",
    "rule_of_three": "cadence",
    "repeated_openers": "cadence",
    "punctuation_rates": "voice_punctuation",
    "sentence_length_distribution": "distribution",
    "sentence_length_dispersion": "distribution",
    "paragraph_sentence_count_runs": "distribution",
    "transition_clusters": "filler",
    "stock_lexical_clusters": "filler",
    "generic_diction": "filler",
    "vague_attribution": "epistemic",
    "bold_label_density": "structural",
    "adjective_requirements": "laundering",  # prd-only; added dynamically by _apply_genre
}

# per-genre KEEP classes; a metric-class NOT listed for a genre strips. Keyed over the feedback
# schema's VALID_GENRES (6). ``marketing``/``technical`` are forward-compat — the 4-genre classifier
# (genre.GENRE_ENUM) cannot emit them yet; when a keep-identifier class exists, extend ``technical``.
# ``spec`` keeps its correctness cadence; ``personal`` also keeps voice punctuation — seeded from the
# old suppress sets, so the recommendation is byte-identical to pre-#59 for the classifier's 4 genres.
_GENRE_KEEP_CLASSES = {
    "general": frozenset(),
    "prd": frozenset(),
    "marketing": frozenset(),
    "technical": frozenset(),
    "spec": frozenset({"cadence"}),
    "personal": frozenset({"cadence", "voice_punctuation"}),
}

# genres the SCANNER (compute_all/_apply_genre) accepts — exactly what classify_genre emits
# (genre.GENRE_ENUM). An unknown scanner genre is a caller error (fail loud).
_SCANNER_GENRES = ("general", "spec", "prd", "personal")


def recommend(genre, metric_name: str) -> str:
    """Advisory per-finding recommendation — ``"strip"`` or ``"keep"`` — for ``metric_name`` under
    ``genre`` (issue #59, keystone v2). Genre NEVER authorizes an edit; this only SETS the
    recommendation the user reviews, and the byte-exact verifier still hard-gates every applied edit.

    ``genre`` None or empty threads as ``"general"`` (the scanner treats genre=None/"" == general, via
    ``compute_all``'s ``if genre:`` guard — kept consistent here). A non-empty genre string outside the
    forward-compat table is a caller error (``ValueError``): ``classify_genre`` only ever emits the
    4-genre enum, so such a value is a bug, not untrusted input. An unmapped (new/unknown) metric
    preserves (``"keep"``) — the asymmetric-failure-safe direction — until it is deliberately
    classified in ``METRIC_CLASS``.
    """
    g = genre or "general"
    keep_classes = _GENRE_KEEP_CLASSES.get(g)
    if keep_classes is None:
        raise ValueError(f"unknown genre {g!r}; expected one of {sorted(_GENRE_KEEP_CLASSES)}")
    cls = METRIC_CLASS.get(metric_name)
    if cls is None:
        return "keep"
    return "keep" if cls in keep_classes else "strip"

# Evaluative adjectives that, asserted as a requirement ("the UI must be fast"), are laundering
# candidates in a PRD (genre-profiles.md: "adjectives-as-requirements"). Closed list = precise;
# a normative modal is REQUIRED so bare aspiration/vision language is never flagged (do not
# vision-police). This is the smallest honest PRD mechanic the current scanner supports — the
# "do not vision-police" side needs no code because the scanner never soft-flags aspiration.
_PRD_REQ_ADJ = (
    "fast", "quick", "snappy", "simple", "intuitive", "easy", "seamless", "smooth", "robust",
    "scalable", "flexible", "powerful", "efficient", "reliable", "secure", "performant",
    "responsive", "modern", "clean", "elegant", "lightweight", "delightful", "user-friendly",
)
_ADJ_REQ_RE = re.compile(
    r"\b(?:must|shall|should)\s+(?:be|feel|look|remain|stay)\s+"
    r"(?:very\s+|highly\s+|extremely\s+|really\s+|super\s+|more\s+|most\s+|quite\s+|truly\s+|incredibly\s+)?"
    r"(" + "|".join(_PRD_REQ_ADJ) + r")\b",
    re.IGNORECASE,
)


def adjective_requirements(units, sw) -> Dict:
    """PRD-only: an evaluative adjective asserted as a requirement ('the UI must be fast') — a
    laundering candidate (genre-profiles.md). Aspirational/vision language WITHOUT a normative
    modal ('our vision is to delight users') is never flagged (do not vision-police)."""
    hits = []
    for u in units:
        for m in _ADJ_REQ_RE.finditer(u.text):
            hits.append({"match": re.sub(r"\s+", " ", m.group(0))[:48],
                         "adjective": m.group(1).lower(), "line_start": u.line_start})
    return _result(len(units), len(hits), None, hits[:25], len(hits) >= 1, "medium", "adj-req-v1")


def _apply_genre(out: Dict, genre: str, units, sw, extraction_profile: str) -> None:
    """Genre is the recommendation seam ONLY (issue #59, keystone v2): it NEVER zeroes a metric's
    ``locations``/``soft_flag`` and never stamps ``suppressed_by_genre``. Suppression moved entirely
    into the advisory ``recommend`` layer; the one in-place effect left is prd's ADDITIVE
    adjective-as-requirement candidate. An unknown (non-classifier) genre is a caller error."""
    if genre not in _SCANNER_GENRES:
        raise ValueError(f"unknown genre {genre!r}; expected one of {_SCANNER_GENRES}")
    if genre == "prd":
        res = adjective_requirements(units, sw)
        res["extraction_profile"] = extraction_profile
        out["adjective_requirements"] = res


def compute_all(units: List[Unit], extraction_profile: str, source: str = "",
                genre: str = None) -> Dict:
    sw = _sentences(units)
    out = {}
    for name, fn in ALL_METRICS:
        res = fn(units, sw)
        res["extraction_profile"] = extraction_profile
        out[name] = res
    if genre:  # None or "general" both leave the default output untouched (general suppresses nothing)
        _apply_genre(out, genre, units, sw, extraction_profile)
    return out
