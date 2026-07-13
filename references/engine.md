# Engine — model & effort guidance (ADVISORY, not enforceable)

**A plugin cannot choose or force the host model or reasoning effort — the Claude Code session owns
them.** Everything here is advisory guidance for whoever runs slopslap; it is not a runtime setting the
plugin can set, and slopslap makes no runtime guarantee about which engine executed. If execution
machinery later surfaces the selected model, report it in the output metadata; until then, do not claim
a specific engine ran.

## Recommended
- **Default: the best Claude tier the session provides (e.g. Opus 4.8, or Sonnet 5), at HIGH reasoning
  effort.** The entangled-constraint diagnosis + verify + minimal rewrite benefits from the strongest
  available reasoning; run slopslap on your best available tier.
- Rationale (research): Claude edits with a "light hand" (the minimal-edit rule) and low re-slop, which
  is exactly what the keystone + behavioral limits ask for.

## Fable 5 — a BONUS, never a requirement
- **Claude Fable 5** tops prose / low-slop boards and can be a strong REWRITE-pass engine — but Fable is
  going API-only, so it cannot be assumed present via the normal Claude Code path. Treating it as
  required would strand subscription users.
- Use Fable 5 for the rewrite pass **only if** API access actually exists. If it does not, proceed on
  the session's Claude tier and flag `OWNER-VERIFY (Fable API)` rather than blocking.

## Effort
Prefer high reasoning effort for the diagnosis and the verification passes; the rewrite is only as
trustworthy as the verify that follows it. The verifier (see `references/invariant-ledger.md`, wired into
the suggest flow via the `scripts/slopslap_assemble/` seam as of #27) is deterministic and owns the hard
accept/reject — no model output overrides a deterministic hard failure, whatever the engine.
