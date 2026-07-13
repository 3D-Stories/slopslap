"""slopslap_assemble — the live-orchestration seam (the assembler, #27).

Chains audit -> candidate -> verify -> apply end-to-end for an ARBITRARY document. It owns the
arbitrary-doc manifest builder, the ``AuditResult`` stage-boundary aggregate, the uniform
``StageResult``/``RunResult`` envelope, the top-level ``run_candidate``/``assemble`` drivers, the
``SLOPSLAP_LIVE``-gated ``live_semantic_fn`` factory, and a thin JSON CLI. It IMPORTS the
lower-level subsystems (``slopslap_scan``, ``slopslap_verification``, ``slopslap_apply``,
``slopslap_invoke``); the eval harness stays a frozen proof, untouched.
"""
