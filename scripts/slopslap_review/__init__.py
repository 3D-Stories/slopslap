"""slopslap review-stage data contracts.

Frozen schemas for the de-slop pivot's REVIEW → LEARN loop:
- ``decisions.json`` — the user's per-finding apply/edit/discard decision set, UNTRUSTED
  input to ``apply``.
- ``feedback.jsonl`` — one local feedback-ledger line per decision, consumed by
  calibration.

The validators in :mod:`slopslap_review.schema` ARE the contract.
"""
