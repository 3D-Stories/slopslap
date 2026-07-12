"""slopslap_scan — the measure-only prose scanner adapter.

Two strictly separated pipelines behind one JSON-emitting CLI (scripts/scan_prose.py):
a stdlib-only text path and a capability-gated Markdown path over a plugin-private VENDORED
CommonMark parser. The scanner MEASURES; it never verdicts and never authorizes an edit
(keystone rule). All metric results are candidate-selection aids only.
"""

EXTRACTION_PROFILE = "commonmark-3.0.0-v1"
TEXT_PROFILE = "text-v1"
THRESHOLD_PROFILE = "scanner-mvp-v1"
SCANNER_SCHEMA_VERSION = 1
