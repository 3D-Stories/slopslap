"""Pinned lexical tables + parameters for the scanner metrics (design R7 / peer consult).

These are versioned separately from the metric code; changing a table is a metric_version
bump. Every table is candidate-selection-only — a match is a triage aid, never a verdict.
"""

TABLES_VERSION = "tables-v1"

# stock lexical clusters — phrase-only, exact normalized token sequences (never isolated
# common words). The two duality templates are handled as bounded regexes in metrics.
STOCK_CLUSTERS = {
    "conclusion_framing": ["in conclusion", "to sum up", "all things considered"],
    "significance_framing": [
        "it is important to note",
        "it is worth noting",
        "serves as a reminder",
        "stands as a testament",
    ],
    "broad_change_framing": [
        "in today's rapidly changing",
        "in an ever-evolving",
        "rapidly evolving landscape",
        "in today's fast-paced world",
    ],
    "essence_framing": ["at its core", "at the heart of"],
    "generic_navigation": ["delve into", "sheds light on", "paves the way for"],
}

# bounded duality templates (regex over normalized text): "not only X but also", "not just X but"
DUALITY_TEMPLATES = [
    r"\bnot only\b.{1,80}?\bbut also\b",
    r"\bnot just\b.{1,80}?\bbut\b",
]

# transition clusters: counted only when SENTENCE-INITIAL (peer: avoid isolated conjunctions).
TRANSITION_OPENERS = [
    "furthermore", "moreover", "however", "therefore", "additionally",
    "consequently", "nevertheless", "nonetheless", "in addition",
    "on the other hand", "as a result", "that said", "in other words",
    "importantly", "notably",
]

# vague-attribution clusters — phrase-only (low confidence).
VAGUE_ATTRIBUTION = [
    "studies show", "studies have shown", "research shows", "research suggests",
    "experts say", "experts agree", "it is widely known", "it is well known",
    "many believe", "some argue", "it is said", "critics say", "scientists say",
    "sources say", "it is often said",
]

# pinned ASCII TLD allowlist for bare-domain detection (RFC 2606 reserved + common real).
TLD_ALLOWLIST = {
    "com", "org", "net", "edu", "gov", "mil", "int", "io", "co", "ai", "dev",
    "app", "xyz", "info", "biz", "me", "us", "uk", "ca", "de", "fr", "jp",
    "cn", "au", "eu", "nl", "se", "no", "es", "it", "ru", "br", "in",
    "example", "test", "invalid", "localhost",
}

# sentence-segmentation abbreviation table (a trailing period here does NOT end a sentence).
ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "eg", "ie", "cf", "al", "fig", "no", "vol", "pp", "inc", "ltd", "co", "corp",
    "dept", "univ", "approx", "min", "max", "a.m", "p.m", "u.s", "u.k",
}

# leading negators that count as lexical tokens for repeated-opener normalization.
NEGATORS = {"no", "not", "never", "neither", "nor"}

# --- cadence tells (issue #14) ---
# negative parallelism: "X, not Y" and "not X, but Y" — the dominant synthetic-cadence tic.
NEGATIVE_PARALLELISM_PATTERNS = [
    r"\b[a-z]{2,},\s+not\s+[a-z]{2,}",          # "quality, not expediency"
    r"\bnot\s+[a-z][\w -]{0,50}?,\s+but\s+[a-z]",  # "not X, but Y"
]
# candidate soft-flag threshold (versioned; candidate_selection_only, no cross-doc percentiles).
NEGATIVE_PARALLELISM_FLAG_AT = 5

# rule-of-three tricolon heuristic: "A, B, and C" parallel triple (low confidence).
RULE_OF_THREE_PATTERN = r"\b[\w-]+,\s+[\w-]+,\s+and\s+[\w-]+"

# em-dash / semicolon appositive-density soft-flag thresholds (per 1k eligible words).
PUNCT_FLAG_PER_1K = {"em_dash_per_1k": 12.0, "semicolon_per_1k": 8.0}

# --- generic-diction / filler (issue #60, pivot P2) ---
# corporate-slop buzzwords: the "finds more" payload. Matched as escaped word-boundary literals
# (no ReDoS). Closed, versioned list — a match is a candidate for the recommendation layer, never a
# verdict; the user's review decision (keystone v2) authorizes any strip.
CORPORATE_BUZZWORDS = (
    "robust", "scalable", "innovative", "best-in-class", "seamless", "leverage",
    "empower", "unlock", "cutting-edge", "world-class", "game-changing", "next-generation",
    "state-of-the-art", "synergy", "holistic", "disruptive", "revolutionary", "turnkey",
    "frictionless", "bespoke", "paradigm", "streamline", "supercharge", "elevate",
    "unparalleled", "best-of-breed", "mission-critical", "value-add",
)
# empty intensifiers: adverbs that inflate without adding a claim. Deliberately EXCLUDES the very
# common "very"/"really"/"quite" (too load-bearing / high false-positive) — only the emptiest.
EMPTY_INTENSIFIERS = (
    "incredibly", "extremely", "truly", "remarkably", "immensely", "exceptionally",
    "tremendously", "wildly", "insanely", "vastly",
)
# soft-flag when this many generic-diction hits accumulate in a doc (calibratable via calibrate.py;
# candidate_selection_only, no cross-doc percentiles).
GENERIC_DICTION_FLAG_AT = 3
