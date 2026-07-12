"""Layer-3 semantic_fn for the eval's e2e path (issue #17).

LIVE (env ``SLOPSLAP_LIVE=="1"``): the real ``invoke_semantic`` bound to ``model`` — a
fresh-context ``claude -p`` pass, a genuine per-session semantic judgement. OFFLINE (default):
a HARDCODED ``clean`` verdict. There is NO recording artifact — the offline verdict is not a
replay of a real judgement; it asserts that the SKILL's frozen, demonstrated candidate is a
faithful (0-violation) repair and therefore clean. That lets the frozen proof drive the FULL
Layer-3 fold (verify -> L3 -> shippable decision) deterministically without a model call, but
offline it exercises only the fold PLUMBING, not a semantic decision. It never fabricates
``clean`` from a real failure — that is ``invoke_semantic``'s job (it fails closed to
``ambiguous``); a real per-session judgement requires ``SLOPSLAP_LIVE=1``.
"""

from __future__ import annotations

import os
from typing import Callable


def eval_semantic_fn(model: str = "sonnet", timeout_s: float = 120.0) -> Callable:
    """Return the Layer-3 ``semantic_fn`` for the eval's e2e ``verify(semantic_fn=...)`` seam.

    LIVE (``SLOPSLAP_LIVE=="1"``): ``functools.partial(invoke_semantic, model=..., timeout_s=...)``
    — the documented binding to the 3-positional seam, a real ``claude -p`` pass. OFFLINE
    (default): a hardcoded ``clean`` stub (the frozen faithful candidate is asserted clean);
    exercises the full fold without a model call, and the live transport is never imported.
    """
    if os.environ.get("SLOPSLAP_LIVE") == "1":
        import functools

        from slopslap_invoke.invoke import invoke_semantic
        return functools.partial(invoke_semantic, model=model, timeout_s=timeout_s)

    # ponytail: frozen-proof clean stub, NOT a recording. The SKILL's demonstrated candidate is a
    # faithful 0-violation repair, so offline we hardcode its L3 verdict as "clean" to drive the
    # full fold (verify -> L3 -> shippable ACCEPT) deterministically without a model call. This is
    # not a real semantic judgement and is not keyed to the input. Upgrade path: SLOPSLAP_LIVE=1.
    return lambda original, revision, ledger_canonical: {"verdict": "clean", "concerns": []}
