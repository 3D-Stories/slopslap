"""slopslap evaluation harness — fixture loading, the two-stage runner, and the judge scaffold.

Deterministic gate logic lives in the shared ``slopslap_verification`` package (imported by
this harness and, later, the ledger-verify layer-1 verifier). This package owns fixture
manifest validation, edit-script reconstruction, the deterministic->acceptance two-stage
state model, and the pluggable LLM-judge A/B scaffold (live judging arrives in #eval-run).
"""
