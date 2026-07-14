# #59 (P1) — universal detection + findings-with-recommendations + keystone v2

WF2 Step 3 design. The committed authority is the ratified pivot design
(`docs/planning/2026-07-13-deslop-pivot-design.md`, owner-ratified 2026-07-13). A build handoff
(workspace-level session context at `<workspace>/claude_docs/slopslap-59-p1-design-handoff.md`, NOT
committed to this repo) seeded the analysis; its module paths were approximate and are corrected here
against the real tree at origin/main @ `6049e0f`.

## Scope (3 ACs, from issue #59 + ratified design §1)
- **AC1** — GENRE_SUPPRESS polarity flip: genre NEVER zeroes a metric's locations; suppression
  survives only as a per-finding *recommendation*.
- **AC2** — findings-with-recommendations envelope: one strip-ready `Finding` per tell, its
  `proposed_rewrite` pre-cleared through verifier Layers 1+2 so the review UI shows safe-vs-blocked.
- **AC3** — keystone v2 rewrite, verbatim across 6 surfaces + the `tests/test_scaffold.py` pin, one PR.

## Corrected architecture map (real paths)
- `scripts/slopslap_scan/metrics.py:282 GENRE_SUPPRESS`, `:322 _apply_genre`, `:340 compute_all`.
- `scripts/slopslap_scan/genre.py:40 GENRE_ENUM=("general","spec","prd","personal")` (4; classifier
  never emits marketing/technical/legal — inert labels), low-conf fallback → `spec`.
- `scripts/slopslap_scan/diagnoses.py:103 authorized_ranges_from_diagnoses` — derives verify()'s
  locality ranges from metric locations.
- `scripts/slopslap_verification/ledger.py:256 verify(...)` → `{decision, proposal_status,
  semantic_status, findings, hunks, ledger_sha256}`. With `semantic_fn=None, allow_two_layer=True`,
  clean L1+L2 ⇒ `decision=="ACCEPT"` (proposal_status stays BLOCKED — read **decision**).
- `scripts/slopslap_assemble/assemble.py:76 AuditResult` (metrics + genre + genre_confidence +
  authorization.ranges + protected_spans + invariant_regions + ledger) — the findings producer's input.
- `scripts/slopslap_review/schema.py` (#58 frozen): `RECOMMENDATIONS={"strip","keep"}`,
  `validate_decisions(audit_finding_ids=...)` treats finding_id as opaque non-empty str;
  `VALID_GENRES` (6, from `eval.loader`) ⊃ classifier's 4 (forward-compat for marketing/technical).

## Design

### AC3 — keystone v2 (T1, HIGH blast, mechanical)
v1 (current pin) = `"Edit authorization comes only from demonstrated editorial harm; the scanner,
genre, ratings, and voiceprint never authorize an edit."` Replace with v2 (VERBATIM from ratified
design §36-40, em-dashes `—` literal):

> Every tell is detected and prepared for removal; genre and learned feedback set each finding's
> recommendation; the user's review decision — not the scanner, not the genre, not the learning —
> authorizes the edit; and the byte-exact verifier guarantees no applied edit changes a number,
> requirement, negation, condition, defined term, or protected span. Recommendations may learn;
> authorization never does.

Surfaces (all one PR or `test_scaffold` goes red): `tests/test_scaffold.py:17-20` KEYSTONE constant;
`skills/slopslap/SKILL.md:18-19` keystone block + realign the follow-on prose ("Diagnosis authorizes
the SCOPE…" states the OLD harm-model); `commands/{audit,suggest,apply,voiceprint}.md`; `README.md:11-12`
(not test-pinned, updated for consistency). Bold `**…**` wrappers are fine — they sit outside the
pinned sentence, so `KEYSTONE in _norm(text)` (substring) still matches. The pinned anti-slap phrase
`"do not punish prose for matching a stylistic tell"` (test line 110) MUST survive — anti-slap becomes
"detect every tell, but a matched tell is a finding, not an automatic strip."

### AC1 — polarity flip (T2, behavioral, security-adjacent)
`_apply_genre` stops zeroing `locations`/`soft_flag`/`suppressed_by_genre` — the only genre effect left
in `compute_all` is prd's additive `adjective_requirements`. So `compute_all(genre="spec")` becomes
byte-identical to `genre=None` for the cadence metrics (satisfies AC1: genre never empties locations).
Suppression moves to a pure `recommend(genre, metric_name) -> "strip"|"keep"` (new, in metrics.py
alongside the genre data). `authorized_ranges_from_diagnoses` gates each metric's locations on
`recommend(genre, name)=="strip"` — **THE subtle keystone-preservation point**: after the flip locations
survive for keep-genres too, so gating on strip is what stops genre-preserved passages leaking into
verify()'s authorized (editable) ranges. Genre still does not *authorize* — it only sets the
recommendation; the user's decision authorizes; the verifier hard-gates.

### AC2 — findings envelope (T3) — AMENDED per Step-4 review H1 (spec-tighten, loopback spec_tighten=1)
New `scripts/slopslap_review/findings.py`: **`build_findings(audit: AuditResult, doc: bytes) -> list[Finding]`.**
The doc bytes are an EXPLICIT parameter — `AuditResult` deliberately carries no bytes (assemble.py:76-94)
and metric `locations` are LINE-based only (no byte offsets), so the producer cannot derive spans or
call `verify()` from `audit` alone (Step-4 H1). Guard: assert `sha256(doc) == audit.source_sha256`
(TOCTOU) — mismatch raises.
- Per metric location → `Finding{id, category, span{start,end}, evidence, genre, recommendation,
  rationale, confidence, proposed_rewrite, verifier_precheck}`.
- **Span** derived line→byte via the `diagnoses._line_starts(doc)` table (the established pattern):
  `start=line_starts[line_start-1]`, `end=line_starts[min(line_end, last)]` — line/unit-granular,
  matching how `authorized_ranges_from_diagnoses` derives ranges (P3 may refine to sub-line).
- **Span** is resolved to the CONTAINING Unit(s): a location spanning multiple units yields one finding
  PER unit (disjoint), each span byte-identical to a `authorized_ranges_from_diagnoses` component
  (Step-11 bug/logic L1) — never one gap-spanning range.
- **`id`** = `f"{metric}:{start}:{end}"` — content-keyed on the (metric, span), which is unique after
  the span-dedup below; colon-safe (metric names are snake_case), so it never collides on the #58
  duplicate-id guard. Stable across re-scans of the same bytes. (Superseded the earlier
  `{metric}:{start_byte}:{ordinal}` sketch once same-span dedup made the ordinal unnecessary.)
- **Dedup**: locations that resolve to the SAME (metric, span) collapse to ONE finding (distinct
  evidence joined) — N byte-identical whole-unit delete candidates would otherwise be N redundant
  findings + N verify() calls that also could not be jointly applied (overlap) (Step-11 T3-adversarial).
- **`proposed_rewrite`**: for `strip`, a CANDIDATE delete `Edit(start,end,b"")` of the unit span (coarse
  in P1 — whole unit; P2/P3 add tell-exact de-claim rewrites); for `keep`, `null`. A candidate to be
  pre-checked, never asserted safe; the user reviews it, the verifier hard-gates it.
- **`verifier_precheck`**: reuse `audit.ledger` (built once per doc), run `verify(doc, [candidate-delete],
  audit.ledger, authorized_ranges=[span], semantic_fn=None, allow_two_layer=True)`, read `decision`.
  Status is the NON-authorizing label `deterministic_pass` (ACCEPT: Layers 1+2 clear — semantic NOT
  run, so NOT shippable; proposal_status/semantic_status carried alongside) or `blocked`
  (REJECT/ASK/SURFACE + reason — a NORMAL outcome for a delete that would break an invariant/protected
  span). A P3 consumer expresses accepting a strip as a decisions `user_action:"apply"` (the empty
  replacement cannot be an `"edit"` payload).

## Follow-ups surfaced by review (out of #59 scope)
- **#62 (P4, apply) — authorization source (Step-11 arch MEDIUM + Codex High):** when decisions→apply
  is wired, `authorized_ranges` for `verify()` MUST derive from the user's accepted/edited finding IDs,
  NOT the genre strip-gate in `authorized_ranges_from_diagnoses` — else a user overriding a keep→strip
  would be silently genre-vetoed, inverting keystone v2. In P1 the genre strip-gate only RESTRICTS
  locality (never authorizes — confirmed by the monotonicity proof: genre-keep only shrinks the set
  below the general ceiling), so it is correct here; the concern is strictly forward.
- **#62/P5 — apply-time L3 gate:** `assemble.live_semantic_fn` offline default returns a vacuous
  "clean" verdict (`SLOPSLAP_LIVE!=1`), so the apply-time semantic gate is a rubber stamp offline.
  Pre-existing; relevant when apply is wired (the P1 findings precheck is deterministic-L1+2-only and
  honestly labeled, so it is not affected).
- **Doc-level slop (Codex High):** a doc flagged only by a doc-level strip metric (e.g.
  `punctuation_rates`) produces no passage-local finding (mirroring the pipeline's no-passage-local
  range). Whether whole-doc slop gets its own rewrite lane is the documented open seam (diagnoses.py
  module docstring), not a P1 deliverable.
P1 envelope is a standalone producer consumed by P3's review UI (#61); wiring into the assemble
pipeline (T4) is deferred to P3 (AC2 requires the producer + precheck to EXIST, not to be wired —
Step-4 confirmed).

## Task decomposition
- **T1 [high]** keystone v2 ×6 surfaces + KEYSTONE constant + version 0.3.0→**0.4.0** (feat) on the
  2 slopslap surfaces (plugin.json + test_scaffold assert) + README Changelog + README Version line.
  TDD: change the constant → red → update all surfaces → green.
- **T2 [high]** `recommend()` + `_apply_genre` no-zero + `authorized_ranges_from_diagnoses` strip-gate;
  rewrite the ~6 pinning test_genre.py assertions (locations preserved + recommendation asserted, not
  zeroing). Verify no test pins old `_audit_status` "clean" on a genre-suppressed doc.
- **T3 [high]** `findings.py` envelope `build_findings(audit, doc)` + precheck; tests: keep-finding→
  keep+null rewrite; strip-finding→ACCEPT ("safe") precheck; strip breaking an invariant→REJECT
  ("blocked") precheck; id-uniqueness for two same-metric same-line tells; AND an end-to-end test
  feeding a real `audit_document(...).data` + its doc bytes through `build_findings` (Step-4 L3).
- **T4 [standard, likely deferred to P3]** wire findings into AuditResult/assemble producer.

## Platform / external dependencies
platform_apis: none

Pure Python stdlib + existing in-repo modules (metrics/diagnoses/ledger/assemble/schema); no
OS/framework/network/external API. The markdown-it parser is already version-pinned and proven
in-repo (diagnoses._markdown_it_cls / protected._markdown_it_cls).

## Design fork — RESOLVED (owner, 2026-07-14): Option C + class-seeding
Recommendation polarity granularity. Owner chose **C — full per-(genre, metric-class) table** over
A (minimal flip) and B (flat): "more personalization and flexibility in the long run" (C is the
substrate #60's filler detector and #63's per-genre learning extend without a re-do).

**Final contract (D3 refinement — seed classes from today's keep-sets, NOT literal keep-all):**
- recommend(genre, metric_class) with a per-(genre, class) table.
- **cadence/voice class** = {negative_parallelism, rule_of_three, repeated_openers} (+ punctuation_rates
  for personal) → KEEP under spec/personal, STRIP under general/prd.
- **all other P1 metrics** (transition_clusters, vague_attribution, stock_lexical_clusters, bold_label,
  sentence_length_*, adjective_requirements) → STRIP under the genre default unless a genre's keep-set
  names them. So spec keeps its correctness cadence but still strips genuine fluff (vague attribution,
  stock clusters) — on-thesis, and == current behavior (zero regression; all current test semantics hold).
- forward-compat rows encoded now: marketing→strip, technical→strip(filler)/keep(identifier), legal→keep
  (the classifier can't emit these yet — the point of C).
- unknown genre STRING → ValueError (fail-loud house discipline; the 4-genre classifier can't emit one,
  so it's a caller bug). low classifier confidence → keep (naturally, via the spec fallback).
- Genre never *authorizes* — recommend() is advisory; the user's per-finding decision authorizes; the
  byte-exact verifier hard-gates every applied edit.
The metric→class map is finalized at T2 against the real metric list.

## Non-goals (P1)
De-claim alternative menus (P2/P3), the generic-diction/filler detector (#60 P2), the interactive
review UI (#61 P3), apply-from-decisions (#62 P4), the feedback ledger (#63 P5).
