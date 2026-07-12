#!/usr/bin/env python3
"""slopslap scanner — MEASURES prose, never verdicts.

Emits a stable JSON envelope on stdout for EVERY path (design R3). A plain-text path is
stdlib-only and always available; the Markdown path is capability-gated over the plugin's
VENDORED CommonMark parser (never an environment copy, never runtime-pip). The scanner never
authorizes an edit (keystone rule).

Usage:
  scan_prose.py --format text|markdown [FILE]     # FILE or stdin
Exit codes: 0 ok · 1 error · 2 format_required · 10 capability_unavailable
"""

from __future__ import annotations

import json
import os
import sys

# self-locate so `import slopslap_scan` works even under `python -I -S` (PYTHONPATH ignored).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slopslap_scan import (  # noqa: E402
    EXTRACTION_PROFILE,
    SCANNER_SCHEMA_VERSION,
    TEXT_PROFILE,
    THRESHOLD_PROFILE,
)
from slopslap_scan import capability as cap_mod  # noqa: E402
from slopslap_scan import extract as ext  # noqa: E402
from slopslap_scan import metrics as met  # noqa: E402

OK, ERROR, FORMAT_REQUIRED, CAP_UNAVAILABLE = 0, 1, 2, 10
VALID_FORMATS = ("text", "markdown")


class ArgError(Exception):
    def __init__(self, kind, detail):
        self.kind = kind
        self.detail = detail


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")


def parse_args(argv):
    fmt = None
    fmt_seen = 0
    files = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--format":
            i += 1
            if i >= len(argv):
                raise ArgError("bad_arguments", "--format requires a value")
            fmt, fmt_seen = argv[i], fmt_seen + 1
        elif a.startswith("--format="):
            fmt, fmt_seen = a.split("=", 1)[1], fmt_seen + 1
        elif a.startswith("-"):
            raise ArgError("bad_arguments", f"unknown option {a!r}")
        else:
            files.append(a)
        i += 1
    if len(files) > 1:
        raise ArgError("bad_arguments", "at most one FILE argument")
    return fmt, fmt_seen, files


def _read_source(files):
    if files:
        path = files[0]
        if not os.path.exists(path):
            raise ArgError("file_not_found", f"no such file: {path}")
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as err:
            raise ArgError("file_unreadable", str(err))
    else:
        try:
            raw = sys.stdin.buffer.read()
        except Exception as err:  # noqa: BLE001
            raise ArgError("stdin_error", str(err))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise ArgError("decode_error", str(err))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        fmt, fmt_seen, files = parse_args(argv)
    except ArgError as err:
        _emit({"status": "error", "error_kind": err.kind, "detail": err.detail, "metrics": None})
        return ERROR

    if fmt is None or fmt not in VALID_FORMATS or fmt_seen > 1:
        _emit({
            "status": "format_required",
            "detail": "a single --format text|markdown is required (no content sniffing)",
            "metrics": None,
        })
        return FORMAT_REQUIRED

    try:
        source = _read_source(files)
    except ArgError as err:
        _emit({"status": "error", "error_kind": err.kind, "detail": err.detail, "metrics": None})
        return ERROR

    try:
        if fmt == "text":
            units = ext.extract_text(source)
            metrics = met.compute_all(units, TEXT_PROFILE, source=source)
            _emit({
                "status": "ok", "schema_version": SCANNER_SCHEMA_VERSION, "format": "text",
                "extraction_profile": TEXT_PROFILE, "threshold_profile": THRESHOLD_PROFILE,
                "units": len(units), "metrics": metrics,
            })
            return OK

        # markdown
        cap = cap_mod.gate()
        if not cap.available:
            sys.stderr.write(
                f"slopslap-scan: markdown parser unavailable ({cap.reason}: {cap.detail}); "
                f"skip markdown metrics.\n"
            )
            _emit({
                "status": "capability_unavailable", "format": "markdown",
                "capability": "markdown_commonmark", "metrics": None,
                "reason": cap.reason, "detail": cap.detail,
            })
            return CAP_UNAVAILABLE
        units = ext.extract_markdown(source, cap.markdown_it)
        drift = cap_mod.recheck_origins()
        if drift:
            sys.stderr.write(f"slopslap-scan: parser origin drift after parse ({drift}).\n")
            _emit({
                "status": "capability_unavailable", "format": "markdown",
                "capability": "markdown_commonmark", "metrics": None,
                "reason": "origin_mismatch", "detail": drift,
            })
            return CAP_UNAVAILABLE
        metrics = met.compute_all(units, EXTRACTION_PROFILE, source=source)
        _emit({
            "status": "ok", "schema_version": SCANNER_SCHEMA_VERSION, "format": "markdown",
            "extraction_profile": EXTRACTION_PROFILE, "threshold_profile": THRESHOLD_PROFILE,
            "units": len(units), "metrics": metrics,
            "capabilities": {"markdown_commonmark": {"available": True, "modules": cap.modules}},
        })
        return OK
    except Exception as err:  # noqa: BLE001 - top-level boundary must still emit JSON
        _emit({"status": "error", "error_kind": "internal", "detail": repr(err), "metrics": None})
        return ERROR


if __name__ == "__main__":
    raise SystemExit(main())
