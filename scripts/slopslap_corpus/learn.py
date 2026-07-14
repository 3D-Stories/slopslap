"""P5 (#63) — consume the feedback ledger to tune RECOMMENDATIONS only (never authorization).

This is the ``learn`` arrow of detect→recommend→review→apply→**learn**. It reads the local feedback
ledger (``slopslap_review.feedback``) as labeled points and produces a KEEP-ONLY ``Overlay`` that the
findings builder applies to the recommendation the *next* review shows.

The keystone invariant — "recommendations may learn; authorization never does" — is enforced
structurally, not by convention:

- ``metrics.recommend()`` is left PURE (genre-only). All three of its call sites keep calling the
  identical pure function; learning is NOT threaded into it.
- ``apply_overlay`` is the only learning seam, imported ONLY by ``slopslap_review.findings`` (the
  review-recommendation path) — never by ``slopslap_assemble`` (apply/authorization) or
  ``slopslap_verification`` (the verifier).
- ``apply_overlay`` is KEEP-ONLY: it can flip ``strip -> keep``, never ``keep -> strip``. So learning
  can only make the tool MORE conservative (shrink the strip set); it can never authorize an edit that
  was not already generally authorized. This is the same monotonic direction #59's genre-keep proof
  established.

P0-schema note: the AC asks a false-positive to "raise that metric's threshold." The frozen P0 feedback
schema (#58) carries no per-finding rate, and the ledger stores no doc text to re-scan — so a *numeric*
per-rate threshold is not derivable here. We realize the threshold-raise as its conservative LIMIT: a
class-keep flip (stop recommending strip for that class+genre). A numeric threshold needs a ``rate``
field the P0 schema froze without; recorded as a v2 refinement, not silently faked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable

from slopslap_scan.metrics import METRIC_CLASS

# keep-evidence weights (per decision on a STRIP-recommended finding):
_STRIP_DISCARD = 1.0    # the user overrode the strip and kept the text
_STRIP_EDIT = 0.5       # partial-accept: they rewrote it — kept tokens are real claims
_STRIP_APPLY = -1.0     # the user endorsed the strip — evidence AGAINST a keep-flip
_DEFAULT_MIN_EVIDENCE = 3.0


@dataclass(frozen=True)
class Overlay:
    """A learned, keep-only recommendation overlay: per genre, the metric-CLASSES to force to keep."""
    keep_classes: Dict[str, FrozenSet[str]] = field(default_factory=dict)


def learn_from_feedback(lines: Iterable[dict], *, min_evidence: float = _DEFAULT_MIN_EVIDENCE) -> Overlay:
    """Aggregate per ``(genre, metric-class)`` net keep-evidence from the ledger; flip a class to keep
    for a genre when its net score reaches ``min_evidence``. Only STRIP-recommended decisions carry a
    signal (a keep rec already keeps). Unclassified metrics are ignored."""
    scores: Dict[tuple, float] = {}
    for ln in lines:
        if ln.get("recommendation") != "strip":
            continue
        cls = METRIC_CLASS.get(ln.get("metric"))
        if cls is None:
            continue
        action = ln.get("user_action")
        weight = {"discard": _STRIP_DISCARD, "edit": _STRIP_EDIT, "apply": _STRIP_APPLY}.get(action, 0.0)
        if weight:
            scores[(ln.get("genre"), cls)] = scores.get((ln.get("genre"), cls), 0.0) + weight

    keep: Dict[str, set] = {}
    for (genre, cls), score in scores.items():
        if score >= min_evidence:
            keep.setdefault(genre, set()).add(cls)
    return Overlay(keep_classes={g: frozenset(cs) for g, cs in keep.items()})


def apply_overlay(base_recommendation: str, genre, metric_name: str, overlay) -> str:
    """KEEP-ONLY: return ``"keep"`` iff the base recommendation is ``"strip"`` AND ``metric_name``'s
    class was learned-flipped to keep for ``genre``; otherwise return ``base_recommendation`` unchanged.
    Never turns a ``keep`` into a ``strip`` — learning can only shrink the strip set."""
    if overlay is None or base_recommendation != "strip":
        return base_recommendation
    g = genre or "general"
    cls = METRIC_CLASS.get(metric_name)
    if cls is not None and cls in overlay.keep_classes.get(g, frozenset()):
        return "keep"
    return base_recommendation
