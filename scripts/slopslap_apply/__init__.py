"""slopslap apply engine — backup-gated in-place mutation + per-hunk selective rollback.

apply mode mutates a source file ONLY after a mandatory, verified pre-mutation backup (the
universal safety net — git-independent, works on dirty files). Per-hunk selective rollback
layers on top: only ACCEPT dependency groups are applied. The backup is never deleted on
success and remains the recovery boundary even if apply logic is defective.
"""
