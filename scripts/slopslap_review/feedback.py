"""P5 (#63) — the local feedback ledger: WRITER / reader / purge.

Every review decision is appended as ONE JSONL line to ``$XDG_STATE_HOME/slopslap/feedback.jsonl``
(default ``~/.local/state/…``). The line SHAPE is frozen by ``schema.validate_feedback_line`` (#58);
the storage PROPERTIES are this writer's job (the schema docstring says so):

- **hashed span** — the ledger ``finding_id`` is ``"{metric}:{sha256('start:end')[:16]}"``. The review
  layer's id carries raw byte offsets; the ledger hashes them, so it holds nothing reconstructable
  about *where* in the doc. Learning keys on ``(genre, metric)`` only; ``doc_sha`` identifies the doc.
- **local + purgeable** — one file under the user's state dir; ``reset_feedback`` unlinks it
  (``slopslap feedback reset``).

The writer NEVER authorizes anything — it only records what the user decided. Learning
(``slopslap_corpus.learn``) consumes these lines to tune the *recommendation* the next review shows;
authorization stays the user's, the verifier stays the hard gate (keystone v2).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Iterator, List, Optional

# self-locate: when run AS A SCRIPT (`python3 scripts/slopslap_review/feedback.py …`, the documented
# invocation), sys.path[0] is this file's dir, not scripts/ — put scripts/ on the path so the absolute
# slopslap_* imports below resolve. Matches every sibling CLI (assemble.py / review.py / apply.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slopslap_review.schema import FeedbackError, validate_feedback_line  # noqa: E402
from slopslap_scan.metrics import METRIC_CLASS  # noqa: E402


def feedback_path() -> str:
    """The ledger path: ``$XDG_STATE_HOME/slopslap/feedback.jsonl`` (default ``~/.local/state``)."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "slopslap", "feedback.jsonl")


def _get(f, name):
    """Read ``name`` from a Finding dataclass OR a payload dict."""
    return getattr(f, name) if hasattr(f, name) else f[name]


def _now_iso(now: Optional[str]) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_feedback(decisions: dict, findings, genre: str, *, path: Optional[str] = None,
                    now: Optional[str] = None) -> int:
    """Append one schema-valid, span-hashed line per decision in ``decisions`` (a decisions.json dict).

    ``findings`` is the built findings (Finding objects or payload dicts) used to attribute each
    decision's metric/class/recommendation. A decision whose ``finding_id`` is not among ``findings``
    is skipped (unattributable). Returns the number of lines written. Raises ``FeedbackError`` if the
    writer ever assembles a line the frozen schema rejects (a writer bug — fail loud)."""
    path = path or feedback_path()
    ts = _now_iso(now)
    doc_sha = decisions["source_sha256"]
    by_id = {_get(f, "id"): f for f in findings}

    lines: List[dict] = []
    for d in decisions.get("decisions", []):
        f = by_id.get(d.get("finding_id"))
        if f is None:
            continue
        metric = _get(f, "category")               # findings set category == the scanner metric name
        span = _get(f, "span")
        hspan = hashlib.sha256(f"{span['start']}:{span['end']}".encode("utf-8")).hexdigest()[:16]
        line = {
            "schema_version": 1,
            "ts": ts,
            "finding_id": f"{metric}:{hspan}",
            "category": METRIC_CLASS.get(metric, "unclassified"),  # the metric's CLASS (learning key)
            "metric": metric,
            "genre": _get(f, "genre") or genre,
            "recommendation": _get(f, "recommendation"),
            "user_action": d["user_action"],
            "doc_sha": doc_sha,
        }
        if d.get("reason"):
            line["reason"] = d["reason"]
        if d["user_action"] == "edit" and d.get("replacement"):
            line["replacement"] = d["replacement"]
        problems = validate_feedback_line(line)
        if problems:
            raise FeedbackError(f"writer produced an invalid feedback line: {problems}")
        lines.append(line)

    if lines:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(json.dumps(line, sort_keys=True) + "\n")
    return len(lines)


def read_feedback(path: Optional[str] = None) -> Iterator[dict]:
    """Yield each VALID feedback line; malformed / schema-invalid lines are skipped (never crash
    learning). A missing file yields nothing."""
    path = path or feedback_path()
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if validate_feedback_line(obj) == []:
                yield obj


def reset_feedback(path: Optional[str] = None) -> None:
    """Purge the ledger (``slopslap feedback reset``) — local, purgeable by design."""
    path = path or feedback_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def main(argv=None) -> int:
    """``slopslap feedback {path|show|reset}`` — inspect or purge the local learning ledger."""
    import argparse

    ap = argparse.ArgumentParser(prog="slopslap feedback",
                                 description="Inspect or purge the local de-slop feedback ledger (#63/P5).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("path", help="print the ledger path")
    sub.add_parser("show", help="print the learned keep-only recommendation overlay derived from the ledger")
    sub.add_parser("reset", help="PURGE the ledger (local, irreversible)")
    args = ap.parse_args(argv)

    if args.cmd == "path":
        print(feedback_path())
        return 0
    if args.cmd == "reset":
        reset_feedback()
        print(f"purged {feedback_path()}")
        return 0
    # show: derive + print the overlay (recommendations only — never authorization)
    from slopslap_corpus.learn import learn_from_feedback
    lines = list(read_feedback())
    overlay = learn_from_feedback(lines)
    print(json.dumps({
        "ledger": feedback_path(), "lines": len(lines),
        "learned_keep_classes": {g: sorted(cs) for g, cs in overlay.keep_classes.items()},
        "note": "recommendations only — the user's decision authorizes; the verifier stays the gate",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
