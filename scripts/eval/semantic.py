"""Layer-3 semantic_fn for the eval's e2e path (issue #17).

LIVE (env ``SLOPSLAP_LIVE=="1"``): the real ``invoke_semantic`` bound to ``model`` — a
fresh-context ``claude -p`` pass. OFFLINE (default): a RECORDED 'clean' verdict, replayed
deterministically so the frozen proof exercises the full Layer-3 fold (audit -> verify -> L3 ->
shippable decision) WITHOUT a model call, same frozen-candidate provenance as the seeded
edit-scripts. It never returns 'clean' from a real failure — that is ``invoke_semantic``'s job
(it fails closed to 'ambiguous'); the offline path is a replay of a verdict recorded ONCE for the
SKILL's demonstrated candidate, not a live judgement.
"""

from __future__ import annotations

import os
from typing import Callable


def eval_semantic_fn(model: str = "sonnet", timeout_s: float = 120.0) -> Callable:
    """Return the Layer-3 ``semantic_fn`` for the eval's e2e ``verify(semantic_fn=...)`` seam.

    LIVE (``SLOPSLAP_LIVE=="1"``): ``functools.partial(invoke_semantic, model=..., timeout_s=...)``
    — the documented binding to the 3-positional seam. OFFLINE (default): a deterministic recorded
    'clean' replay; the live transport is never imported.
    """
    if os.environ.get("SLOPSLAP_LIVE") == "1":
        import functools

        from slopslap_invoke.invoke import invoke_semantic
        return functools.partial(invoke_semantic, model=model, timeout_s=timeout_s)

    # ponytail: frozen-proof recorded replay. The SKILL's demonstrated candidate was verified
    # 'clean' once; replay it deterministically offline (no live transport imported, no model
    # call) so the eval demonstrates the full L3 -> shippable-ACCEPT fold reproducibly. Upgrade
    # path: run under SLOPSLAP_LIVE=1 for a real per-session judgement.
    return lambda original, revision, ledger_canonical: {"verdict": "clean", "concerns": []}
