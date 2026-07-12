"""LLM-judge A/B scaffold (design R7). Live Claude judging is injected in #eval-run.

Each dimension is scored 0/1/2 against a baseline:
  0 = harmful (worse than baseline), 1 = neutral (equal), 2 = better-than-baseline.
Per dimension the median over >=3 blinded trials damps judge variance. A candidate BEATS a
baseline iff (all hard gates already pass AND) median dimension-sum >= baseline's AND it
strictly wins >=1 dimension AND none worse by >1. A tie (equal sums) resolves to the more
preservation-heavy output — enforced upstream by the deterministic gates, not here.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# dimension -> human-readable 0/1/2 anchors (also documented in references/eval-cases.md)
DIMENSIONS: Dict[str, Dict[int, str]] = {
    "meaning_preservation": {0: "meaning altered/lost", 1: "meaning intact, equal to baseline", 2: "meaning intact and clearer"},
    "unsupported_claim_introduction": {0: "introduces an unsupported claim", 1: "no new unsupported claim (equal)", 2: "removes an unsupported claim"},
    "actor_responsibility_preservation": {0: "reassigns/hides the actor", 1: "actor unchanged", 2: "clarifies the actor without inventing one"},
    "unresolved_intent_visibility": {0: "asserts a resolution of an unresolved point", 1: "keeps it unresolved (equal)", 2: "surfaces the unresolved point as a question"},
    "editorial_cost_reduction": {0: "increases editorial cost", 1: "no change", 2: "reduces editorial cost"},
    "voice_distance_from_samples": {0: "flattens/normalizes distinctive voice", 1: "voice preserved (equal)", 2: "voice preserved while removing only true harm"},
    "genre_fitness": {0: "violates the genre's function", 1: "genre function intact", 2: "improves genre fit"},
    "edit_locality_and_justification": {0: "edits sprawl beyond justified harm", 1: "local, justified (equal)", 2: "minimal, each edit justified"},
    "seeded_defect_fixed_without_normalizing": {0: "normalizes surrounding distinctive prose", 1: "no collateral normalization (equal)", 2: "fixes the seeded defect cleanly"},
}


@dataclass
class Trial:
    """One blinded trial: 0/1/2 per dimension for the candidate vs the baseline."""

    candidate: Dict[str, int]
    baseline: Dict[str, int]

    def validate(self) -> None:
        for label, scores in (("candidate", self.candidate), ("baseline", self.baseline)):
            # the COMPLETE dimension set is required — a partial trial that omits every
            # unfavorable dimension must not be able to satisfy the beat criterion (WF5-diff F5).
            missing = set(DIMENSIONS) - set(scores)
            if missing:
                raise ValueError(f"{label} trial missing dimensions: {sorted(missing)}")
            extra = set(scores) - set(DIMENSIONS)
            if extra:
                raise ValueError(f"{label} trial has unknown dimensions: {sorted(extra)}")
            for dim, val in scores.items():
                if val not in (0, 1, 2):
                    raise ValueError(f"{label}.{dim} score {val} not in 0/1/2")


@dataclass
class JudgeVerdict:
    present: bool
    errored: bool
    beat: bool
    candidate_median: Dict[str, float] = field(default_factory=dict)
    baseline_median: Dict[str, float] = field(default_factory=dict)
    detail: str = ""


def _median_by_dim(trials: List[Trial], pick) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for dim in DIMENSIONS:
        vals = [pick(t).get(dim) for t in trials if dim in pick(t)]
        if vals:
            out[dim] = statistics.median(vals)
    return out


def beat_criterion(cand: Dict[str, float], base: Dict[str, float]) -> bool:
    # require the COMPLETE dimension set on both sides (WF5-diff F5) — an incomplete median
    # map can never win.
    if set(cand) != set(DIMENSIONS) or set(base) != set(DIMENSIONS):
        return False
    dims = list(DIMENSIONS)
    if sum(cand[d] for d in dims) < sum(base[d] for d in dims):
        return False
    if any(cand[d] < base[d] - 1 for d in dims):  # none worse by more than 1
        return False
    return any(cand[d] > base[d] for d in dims)  # strictly wins >=1


def evaluate(trials: List[Trial]) -> JudgeVerdict:
    if not trials:
        return JudgeVerdict(present=False, errored=False, beat=False, detail="no trials")
    if len(trials) < 3:
        return JudgeVerdict(
            present=True, errored=True, beat=False,
            detail=f"only {len(trials)} trial(s); >=3 required",
        )
    try:
        for t in trials:
            t.validate()
    except ValueError as err:
        return JudgeVerdict(present=True, errored=True, beat=False, detail=str(err))
    cand = _median_by_dim(trials, lambda t: t.candidate)
    base = _median_by_dim(trials, lambda t: t.baseline)
    return JudgeVerdict(
        present=True,
        errored=False,
        beat=beat_criterion(cand, base),
        candidate_median=cand,
        baseline_median=base,
    )


# Live judging injects a judge_fn(fixture, original, revision, baseline_revision) -> Trial.
JudgeFn = Callable[[dict, bytes, bytes, bytes], Trial]


def run_trials(
    judge_fn: JudgeFn,
    fixture: dict,
    original: bytes,
    revision: bytes,
    baseline_revision: bytes,
    n: int = 3,
) -> JudgeVerdict:
    trials: List[Trial] = []
    for _ in range(n):
        try:
            trials.append(judge_fn(fixture, original, revision, baseline_revision))
        except Exception as err:  # noqa: BLE001 - judge errors must not crash the run
            return JudgeVerdict(present=True, errored=True, beat=False, detail=str(err))
    return evaluate(trials)
