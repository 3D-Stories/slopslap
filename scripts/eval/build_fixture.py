#!/usr/bin/env python3
"""Fixture-authoring utility (design R5/R9).

Authors annotate ranges by hand; this tool computes protected-span sha256 hashes from the
IMMUTABLE original.md bytes so offsets/hashes are never hand-maintained (a common source of
corruption). ``validate`` re-checks a manifest against the runner's rules.

Usage:
  build_fixture.py build    --dir tests/fixtures/eval/<name>   # fill protected_spans[].sha256
  build_fixture.py validate --dir tests/fixtures/eval/<name>   # report manifest problems
  build_fixture.py show     --dir tests/fixtures/eval/<name> --start N --end M  # print span bytes
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from slopslap_verification.editscript import sha256_hex  # noqa: E402

from loader import load_fixture, validate_manifest  # noqa: E402  (run as script)


def _write_manifest(fixture_dir: str, manifest: dict) -> None:
    with open(os.path.join(fixture_dir, "fixture.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def cmd_build(args) -> int:
    original, manifest = load_fixture(args.dir)
    for sp in manifest.get("protected_spans", []):
        s, e = sp["start_byte"], sp["end_byte"]
        sp["sha256"] = sha256_hex(original[s:e])
    _write_manifest(args.dir, manifest)
    problems = validate_manifest(original, manifest)
    if problems:
        print("built, but manifest still has problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"built {args.dir}/fixture.json ({len(manifest.get('protected_spans', []))} spans)")
    return 0


def cmd_validate(args) -> int:
    original, manifest = load_fixture(args.dir)
    problems = validate_manifest(original, manifest)
    if problems:
        for p in problems:
            print(f"  - {p}")
        print(f"FIXTURE_ERROR: {len(problems)} problem(s)")
        return 1
    print("OK")
    return 0


def cmd_show(args) -> int:
    original, _ = load_fixture(args.dir)
    span = original[args.start : args.end]
    print(f"[{args.start},{args.end}) len={len(span)} sha256={sha256_hex(span)}")
    print("---")
    sys.stdout.buffer.write(span)
    print("\n---")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="slopslap fixture authoring utility")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True)
    ps = sub.add_parser("show")
    ps.add_argument("--dir", required=True)
    ps.add_argument("--start", type=int, required=True)
    ps.add_argument("--end", type=int, required=True)
    args = ap.parse_args(argv)
    return {"build": cmd_build, "validate": cmd_validate, "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
