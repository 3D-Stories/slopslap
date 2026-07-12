# slopslap · v0.2 Epic Dashboard (#16)

Live status surface for epic #16 — "live model-in-the-loop integration". Updated inside each
child's own PR. Visual twin: `2026-07-12-16-v02-epic-dashboard.html` (committed HTML is the
source of truth; the hosted Artifact is a copy).

- **Repo:** 3D-Stories/slopslap · **Epic:** #16 · **Run:** autonomous, session 001b8b2c, started 2026-07-12
- **Baseline:** 214 passed / 0 failed on main @ 0bdbfa9
- **Version path:** patch bump per child (0.1.1, 0.1.2, …); final Tier-4 child sets **0.2.0**

## Progress

**3 / 14 children merged** · current: Tier 1 — #17 shipped (PR #34); #18 next

| Tier | Child | Title | Depth | Deps | Status | PR | Version | Gate delta |
|---|---|---|---|---|---|---|---|---|
| 0 | #26 | platform-feasibility spike | full WF2 | — | ✅ merged | #32 | 0.1.1 | 214→267 (+53), 0 reg |
| 0 | #30 | corpus integration (manifest + split + fixtures + anchors) | full WF2 | — | ✅ merged | #33 | 0.1.2 | 267→304 (+37), 0 reg |
| 1 | #17 | semantic verify (real Layer-3 semantic_fn) | lite | #26 | ✅ merged | #34 | 0.1.3 | 304→308 (+4), 0 reg |
| 1 | #18 | protected-span auto-extractor | lite | — | queued | — | — | — |
| 1 | #19 | invariant-ledger auto-build | lite | — | queued | — | — | — |
| 1 | #20 | live passage-local locality | lite | — | queued | — | — | — |
| 1 | #22 | genre classifier constrains diagnosis/verify | lite | — | queued | — | — | — |
| 2 | #27 | live-orchestration seam (the assembler) | full WF2 | #26, #17–#20 | queued | — | — | — |
| 3 | #23 | suggest → deterministic verifier wiring | full WF2 | — | queued | — | — | — |
| 3 | #21 | apply write-strategy hardening | full WF2 | — | queued | — | — | — |
| 3 | #29 | apply-command enablement | lite | #21, #27 | queued | — | — | — |
| 3 | #24 | manual voice sample (one-shot) | lite | — | queued | — | — | — |
| 4 | #28 | live e2e validation golden (safety verdicts) | lite | #27, #23, #17–#20, #30 | queued | — | — | — |
| 4 | #25 | scanner threshold calibration (held-out split) | lite | #30 | queued | — | — | — |

## Dependency spine

```
Tier 0: #26 feasibility ──► #17 semantic ─┐
        #30 corpus ──────► #25, #28       │
Tier 1: #18 #19 #20 #22 (independent) ────┤
Tier 2: #27 assembler (dep #26, #17–#20) ─┼─► #29 (dep #21, #27)
Tier 3: #23 wiring · #21 hardening · #24 ─┘
Tier 4: #28 e2e golden (dep #27,#23,#17–#20,#30) · #25 calibration (dep #30)
```

## Exit gate (DONE definition)

- [ ] All 14 children merged + closed (or blocker-commented, epic left open)
- [ ] Epic #16 checkboxes ticked, closed with children→PRs→versions summary
- [ ] Version 0.2.0 on both surfaces (plugin.json + tests/test_scaffold.py pinned assert)
- [ ] Suite green, counts stated vs 214/0 baseline
- [ ] Dashboard current as of last merged child

## Deviations / blockers

- **D7 (owner-confirmed):** GitHub Actions is billing-blocked org-wide; the `test` CI lane can't
  run. Owner: "continue local testing and skip the CI on GitHub" (runner being set up). Every
  child merges on the **green local `pytest`** gate (exit 0). GitHub CI polling skipped.
- Full decision log: `claude_docs/session_notes/epic-16-autorun-log.md`.
