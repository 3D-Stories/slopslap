"""slopslap fresh-context model invocation (#26 platform-feasibility spike).

Proves ONE thing: the plugin can call a model in a FRESH context (new OS process, new
session, no rewriter chain-of-thought) from synchronous Python — the exact shape the
Layer-3 semantic seam (``slopslap_verification.ledger.verify(..., semantic_fn=...)``)
needs. The public surface is CLOSED (see ``invoke.invoke_semantic``); the versioned
request/response ``contract`` is the trust boundary against model-authored JSON.
"""

from .contract import (
    CONTRACT_VERSION,
    InvalidRequestError,
    build_request,
    parse_response,
)

__all__ = [
    "CONTRACT_VERSION",
    "InvalidRequestError",
    "build_request",
    "parse_response",
]
