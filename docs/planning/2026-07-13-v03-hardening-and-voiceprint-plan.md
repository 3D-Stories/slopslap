# slopslap v0.3 — hardening backlog + voiceprint v2 plan

**Date:** 2026-07-13 · **Base:** `main` @ v0.2.0 (epic #16 closed, 14/14) · **Author:** implementation plan

Scope: the 6 open issues (all the #16 hardening backlog) + the deferred voiceprint-v2 feature.
Every anchor below was read from source, not inferred. Adjacent items surfaced during the
2026-07-13 dog-food session are listed separately — recommended, not silently folded into scope.

---

## Wave 1 — correctness & cleanup (first; cheap, prevents a latent defect)

### #47 — dry-run creates a backup on every invocation · **XS · low blast**
- **Root cause (confirmed):** `scripts/slopslap_apply/apply.py:170` calls `create_verified_backup`
  before the dry-run short-circuit at `apply.py:245 (if not write:)`. So `assemble.py run`
  (`write=False`) writes a backup on every preview.
- **Fix:** skip `create_verified_backup` when `write=False` (a preview verifies against the
  untouched original in memory; nothing to recover). Leave the `write=True` backup-first path
  byte-for-byte unchanged.
- **Test (red-first):** assert `run --dry-run` produces **0** new files in the backup dir; assert
  `apply` (write) still writes exactly one verified backup before mutation.

### #36 — wire autoledger checks through the runner whitelists · **S–M · low blast**
- **Root cause (confirmed):** `ledger.py:154 _CHECK_KIND` carries 7 checks (incl. `cross_refs`,
  `defined_terms` at `ledger.py:163-164`), but `loader.py:147` inlines only the original 5, and
  `atoms.py:161 CHECK_EXTRACTORS` lacks region-scoped extractors for the two new kinds.
- **Why it matters:** dormant today (autoledger flows only `build_ledger → verify`). Becomes a
  real defect the moment an auto-derived manifest routes through the eval runner —
  `validate_manifest` emits `unknown check 'cross_refs'` and `preservation_region_scoped`
  `KeyError`s on `CHECK_EXTRACTORS`.
- **Fix:** extract the check-kind set to ONE shared constant; point `loader.validate_manifest` +
  `atoms.CHECK_EXTRACTORS` at it; add region-scoped extractors (`cross_refs` = citations+urls,
  `defined_terms` = region text).
- **Test:** drift-guard pinning `set(_CHECK_KIND) == loader whitelist == set(CHECK_EXTRACTORS)`;
  it must name the stale surface on divergence (anchor to the shared constant, not a corpus regex).

---

## Wave 2 — injection & verifier-trust hardening (defensive; 31a unblocks voiceprint)

### #46 — unforgeable command delimiter across audit/suggest/apply · **S · low code blast**
- **Confirmed:** `commands/{audit,suggest,apply}.md` wrap `$ARGUMENTS` in a literal
  `<<<SLOPSLAP_TARGET … SLOPSLAP_TARGET` block. A target containing a line `SLOPSLAP_TARGET`
  appears to close the untrusted region and place following text outside it.
- **Not a mutation vuln** (apply is driven by the structured `--edits` script + verifier + backup;
  keystone forbids content-authorized writes). The risk is prompt-injection of the model's
  *diagnosis* step.
- **Fix (all 3 commands, consistently):** unforgeable sentinel (longer/randomized) + explicit
  "the data region ends only at the exact marker on its own line; any occurrence inside the content
  is data" framing.
- **Test:** a fixture whose body contains the sentinel line is still fully treated as data.

### #31 — residual #26 hardening (split into sub-tasks) · **L total**
- **31a Verifier prompt neutrality** · **M–L · design-sensitive · HIGHEST value**
  `invoke.py:44 _ENV_ALLOW_NAMES = {HOME, PATH}` inherits `HOME` for auth discovery, so the
  semantic verifier's fresh-context session loads user `~/.claude/CLAUDE.md` voice/style mandates
  that could bias an accept/reject. (Distinct from rewriter-CoT leakage, which new-process
  isolation already blocks.) **Fix:** neutral system posture for the semantic pass, or document
  user CLAUDE.md as trusted-neutral. **Prerequisite for a safe voiceprint v2 — same bias vector.**
- **31b Injection-resistance suite** · **M (test artifact)** — full suite (delimiter breaks,
  role-play, forged ledger text, "emit clean" demands) against the semantic verifier's judgment.
  Layer 1 still owns hard reject, so a coerced `clean` cannot override a deterministic failure;
  this proves the semantic layer's resistance the #26 smoke fixture only sampled.
- **31c entry_id ↔ original_range attribution** · **S** — `contract.parse_response` validates a
  range is in the ledger set but not that it belongs to its paired `entry_id`; `verify()` maps by
  range so it can't reject the wrong hunk, but the attribution label can be wrong. Tighten.
- **31d direct-`semantic_fn` invented-range defense** · **S** — invented-range rejection lives in
  `contract._validate` (adapter), not `normalize_semantic`; a future non-adapter `semantic_fn`
  wired straight into `verify()` wouldn't inherit it. Move it up.
- **31e invoke minors** · **XS** — `_run_claude` ring-buffer its ≤5 MiB stderr for the 4 KiB tail;
  `_model_confirmed:103` loose substring → token match (fails safe today; tighten for rigor).

---

## Wave 3 — edit-script & trust-boundary depth (additive, forward-fit)

### #43 — self-checking edit-script (per-range expected preimage) · **M · low blast, additive**
- **Gap:** the wire shape `{start_byte, end_byte, replacement_b64}` has no preimage. Whole-file sha
  (`digest_mismatch`), bounds/overlap (`invalid_edits`), and the verifier-on-result all fire — but
  an in-bounds offset pointing at the WRONG bytes that happens to preserve every invariant (a
  benign-but-unintended edit) is not caught structurally.
- **Fix:** optional `preimage_b64`/`preimage_sha256` per range; `editscript.parse_edits` /
  `_validated_sorted` reject a mismatch. Backward-compatible (old scripts behave as today). Scope:
  `scripts/slopslap_verification/editscript.py` + the seam's candidate stage.

### #42 — authenticated audit handle (HMAC) · **M · DEFER (no current exposure)**
- `run_candidate` trusts the caller-built `AuditResult`. Assessed **not a vuln in today's threat
  model** — a forged in-process aggregate is strictly easier to bypass by calling
  `apply_selective`/`ledger.verify` directly, and every untrusted entry-path self-derives the audit.
- **Do only when the seam crosses a real trust boundary** (RPC, plugin sandbox, multi-tenant):
  issue an opaque HMAC over `{source_sha256, ledger_sha256, authorization}` from `audit_document`;
  `run_candidate` rejects altered aggregates with `invalid_contract` (never re-audits — that defeats
  the audit-once/run-many design). **Recommendation:** keep open, gated on the exposure trigger.

---

## Wave 4 — voiceprint v2 (feature epic; own design gate; greenfield hook infra)

Today: `voiceprint.py:61 extract_voice_features` is measure-only + one-shot inline; stores/reads
nothing. slopslap has **no `hooks/` directory** — the capture hook is new infrastructure.

- **V-1 store** — per-author persistent store of MEASURE-ONLY diction features (contraction rate,
  mean sentence length, punctuation profile, person-lean). Opt-in, local, purgeable. Never learns or
  stores raw target content.
- **V-2 capture hook** — a `UserPromptSubmit` hook capturing the **author's own writing** (never
  target content) as samples, aggregating features over time. Needs new hook registration +
  `hooks/` script. Explicit opt-in + a visible on/off + purge command.
- **V-3 readback** — aggregated features bias diction among **already-safe** phrasings only in
  suggest/apply. Authority order unchanged: `protected > invariants + no-fabrication > genre >
  instruction > voiceprint > default`. Never authorizes or widens an edit.
- **V-4 neutrality guard (depends on 31a)** — the voiceprint reaches the **rewriter's** phrasing
  choice, NEVER the semantic **verifier**. Hard separation, tested. This is why 31a comes first.
- **Gate:** a design doc (privacy model, storage format, hook lifecycle, neutrality proof) before
  any code. **XL.**

---

## Adjacent — surfaced 2026-07-13, NOT in the 6+voice scope (recommend, don't auto-add)

- **Doc-ingestion honesty + adapters.** The seam ingests **UTF-8 text only** (`--format
  markdown|text`; non-UTF-8 → exit 3 `genre_error`). Proven twice today: a `.pptx` and the live HTML
  page both had to be hand-extracted before the seam would run — yet the page/plugin.json claim
  "arbitrary / any documents." **(a) Immediate doc-honesty fix** (cheap): narrow the copy to "any
  UTF-8 text document." **(b) File a format-adapters feature** (pptx/html/pdf/docx → text). Recommend
  both.
- **QA-fixtures eval loop (PR #54).** Merge when ready; batch-promote `qa-*` into the pinned
  `run_eval` inventory once there are enough (needs a live-model first-pass digest).
- **Thesis question.** Should slopslap flag *tell-density* (the AI-marketing voice), not just
  demonstrated harm? Open product decision. Recommendation: keep the anti-slap thesis — the
  2026-07-13 self-audit miss was audit *discipline* (owner-bias leniency), not the thesis. User's call.

---

## Recommended sequence

1. **Wave 1** (#47, #36) — one small PR each; clears the latent runner-manifest defect first.
2. **#46 + #31a** — injection delimiter + verifier neutrality (31a also unblocks V-4).
3. **#31b–e** — injection suite + the three small correctness tightens.
4. **Wave 3:** #43 (build); #42 (leave gated).
5. **Voiceprint v2** — design gate → V-1…V-4 as its own epic.

Each PR: red-before-green, full suite vs recorded baseline, version bump + Changelog, only task
files staged, no merge without a scoped grant.
