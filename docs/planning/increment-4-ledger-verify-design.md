# Increment 4 design brief — #ledger-verify (invariant ledger + 3-layer verify + decision rule)

Context: slopslap's verifier decides whether a proposed rewrite may ship. **A rewrite you do not
verify is a rewrite you do not ship.** The deterministic layer-1 checkers already exist
(`scripts/slopslap_verification/` from #eval-fixtures: edit-script map, atom extractors, hard gates).
This increment formalizes the machine-readable **invariant ledger** shared by rewrite + verify, and the
**3-layer verification** + **decision rule** on top. Spec: `docs/planning/2026-07-12-slopslap-reconciled-spec.md`
(§Invariant ledger, §Verification). Reuse, don't re-implement, the increment-1 checkers.

## Deliverables
- `references/invariant-ledger.md` — the byte-canonical JSON schema + the 3-layer verify contract + the
  decision rule + canonical coordinates.
- `scripts/slopslap_verification/ledger.py` — a `Ledger` (entries + protected spans), `build_ledger`
  (from a fixture manifest + auto-extraction of atoms per region), and `verify(original, edits, ledger,
  semantic_fn=None)` returning a decision, reusing the existing gate checkers.

## Ledger schema (spec §Invariant ledger)
- Closed `kind` enum: literal · number_or_quantity · normative_statement · condition · exception ·
  causal_claim · attribution · defined_term · cross_reference · unsupported_intent · missing_support ·
  intentional_repetition · protected_span.
- Closed `preservation` enum: byte_exact · lexically_exact · semantic_exact · relationship_exact ·
  surface_only.
- Each entry: `id, kind, source{start_byte,end_byte,text_hash}, extracted{...}, preservation,
  confidence`. **byte offsets are canonical**; any start_line/end_line are DERIVED display-only.
- Plus `protected_spans[]` with byte offsets + sha256. All positions use ORIGINAL-byte offsets; the
  rewrite carries an original→revision edit map (the increment-1 `editscript.map_offset`).

## 3 layers (rewriter never verifies itself)
1. **Deterministic integrity (CODE, owns the hard accept/reject):** the increment-1 hard gates —
   protected-span hashes, region-scoped numbers/units/modality/negation, no new claim atoms,
   edit-locality, markdown structure. No model output overrides a deterministic hard failure.
2. **Extraction-then-compare:** re-extract each ledger entry's content from the revision (mapped
   region) into the same shape; match by id else source-neighborhood; a dropped/weakened/added entry is
   a reject.
3. **Adversarial semantic (separate pass, fresh context):** receives ONLY original + revision + ledger
   (never the rewriter's chain-of-thought); MAY use a different model. Shipped here as a callable
   INTERFACE (`semantic_fn`) the eval-run injects; not invoked in unit tests.

## Decision rule (spec §Verification)
- hard failure (protected-span mutation, changed number/unit/identifier/modality, invented claim,
  removed condition/exception) → **auto-reject**.
- ambiguous semantic → **surface** original + proposal + concern (don't apply).
- soft style → **keep the safer version**; never escalate an edit to satisfy style.
- ledger uncertainty (source ambiguous) → **ask**, don't resolve by rewriting.
- suggest mode: mark proposal `BLOCKED`. apply mode: revert only the failing hunk.

## Questions for the peer
1. In a DETERMINISTIC MVP with no model, what does layer 2 (extraction-compare) add over layer 1's
   region checks — or does it collapse? How to make proposition-level matching (by id else
   subject/predicate/object + neighborhood) add real value without an NLP model?
2. Layer-3 interface: the exact `semantic_fn(original, revision, ledger) -> verdict` contract (inputs
   ONLY those three; returns real/ambiguous/clean + concerns), and how the decision rule combines it
   (L1 hard reject always wins; L3 ambiguous → surface; L3 clean + L1 pass → accept).
3. `build_ledger` auto-extraction: which invariants to auto-derive (numbers, modals, negation,
   conditions, dates, defined terms, protected spans) and how to assign the `preservation` kind + a
   confidence to each.
4. How `verify`'s decision feeds the modes: suggest → BLOCKED; apply (next increment) → revert the
   failing hunk. What does `verify` return so #apply-backup can act per-hunk?
5. Edit-map: confirm `editscript.map_offset`/`map_region` are the canonical multi-hunk machinery, or
   name any gap (e.g. an entry whose source region was deleted entirely).

## Folded decisions — post peer-consult (gpt-5.6-sol, `docs/reviews/peer-increment-4-ledger-verify-design-2026-07-12.md`)

1. **Ledger envelope** `{schema_version, source_sha256, entries, protected_spans}`. Validation rejects
   unknown fields, bad enum values, duplicate ids, invalid/overlapping ranges, and hashes inconsistent
   with the original bytes. Entries sorted by `(start_byte, end_byte, id)`; **canonical serialization**
   (sorted keys + sorted entries) yields a stable `ledger_sha256`. Establish exact UTF-8 bytes +
   `source_sha256` BEFORE any extraction.
2. **Entry** `{id, kind, source{start_byte,end_byte,text_hash}, extracted, preservation, confidence}`.
   ids are stable (built once, never recomputed from revision). **confidence is an integer 0..1000** (no
   float ambiguity). Line coords only in a separate display projection, never canonical JSON.
3. **protected_spans** is the authoritative hard-gate table `{id,start_byte,end_byte,sha256}`; one
   internal record projected into both views so they cannot drift.
4. **Layer 2 ≠ Layer 1.** L1 = scoped atom inventories + structure (the existing gates). L2 = per-ENTRY
   **survival + attachment**: map the entry's source region (status contract below); a deleted mapping is
   a dropped-entry REJECT; else re-extract the entry's kind-shape and compare by inherited id else
   fingerprint+neighborhood — unique match compared, zero = dropped, multiple = **ASK** (uncertain,
   never a guessed match), unmatched high-confidence revision atoms = additions. Lexical entries need no
   parser; relationship kinds without a supported deterministic rule → uncertain (ASK).
5. **build_ledger auto-derivation:** numbers/quantities/units/dates/identifiers/cross-refs → byte_exact
   or lexically_exact (high conf); modals + negation → semantic_exact (high conf); conditions/exceptions
   → relationship_exact (med-high); defined terms → lexically_exact; manifest protected spans →
   byte_exact conf 1000. unsupported_intent / missing_support / intentional_repetition are
   manifest-supplied. Auto-derived per the fixture's `invariant_regions` + `expected_invariants`.
6. **Confidence controls AUTOMATION, not preservation strength.** A high-confidence mismatch may REJECT;
   a low-confidence/ambiguous source or extraction yields ASK. Confidence NEVER lets a hard gate pass or
   lets semantic review override a deterministic failure.
7. **semantic_fn (Layer 3) contract:** `semantic_fn(original, revision, ledger_view) ->
   {verdict:'real'|'ambiguous'|'clean', concerns:[{code,message,entry_ids?,original_ranges?,revision_ranges?}]}`.
   Given ONLY original + revision + ledger view — no edits, rationale, or chain-of-thought. Its output is
   schema+enum validated; an exception, malformed output, or unverifiable coordinates ⇒ **ambiguous,
   never clean**. Omitting it ⇒ `semantic_status='not_run'` (callers may require L3; ACCEPT-not_run ≠
   fully verified).
8. **Decision precedence (strict REJECT > ASK > SURFACE > ACCEPT):** any L1 hard failure → REJECT; any
   definite L2 dropped/weakened/added → REJECT; uncertain ledger source or non-unique L2 → ASK; L3 real →
   REJECT; L3 ambiguous → SURFACE; all preservation passing + (L3 clean OR semantic_fn omitted) → ACCEPT.
   Soft-style never escalates: if safety can't be deterministically ordered → SURFACE, else pick the
   safer variant (usually the original). suggest maps every non-ACCEPT → `proposal_status='BLOCKED'`.
9. **verify returns** `{decision, proposal_status, semantic_status, findings, hunks, ledger_sha256}`.
   Finding: `{layer, severity, code, message, entry_ids, original_ranges, revision_ranges,
   implicated_hunk_ids, disposition}`. Hunk: `{hunk_id, original_range, revision_range, decision,
   finding_ids, revertable}` — so #apply-backup reverts the union of failing dependency groups while
   keeping passing, non-dependent hunks.
10. **map_region status contract (the gap):** extend the edit-map to return `(interval_or_None, status)`
    where status ∈ `{unchanged, modified, deleted, ambiguous}`; a boundary strictly inside an edit is
    `ambiguous`, a fully-deleted source region is `deleted` (a tombstone, not an empty success). A ledger
    entry spanning several/adjacent hunks implicates ALL of them (one dependency group).

## Post-review resolutions — WF5 on the ledger-verify design (`docs/reviews/increment-4-ledger-verify-design-md-2026-07-12.md`, 1 Crit / 3 High / 3 Med, all confirmed)

- **R1 (C1) — no two-layer ACCEPT by default.** An otherwise-passing rewrite with `semantic_fn` OMITTED
  returns **`SURFACE`** (decision), `semantic_status='not_run'`, `proposal_status='BLOCKED'` — never
  ACCEPT. ACCEPT requires L3 `clean`. A caller may pass `allow_two_layer=True` (used by deterministic
  unit tests / a suggest preview) to authorize a two-layer ACCEPT explicitly; even then
  `semantic_status` stays `not_run` so the caller can tell it apart from a fully-verified ACCEPT.
- **R2 (H2) — exact byte-canonical serialization.** `references/invariant-ledger.md` pins:
  `json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`, NO
  trailing newline, integer-only `confidence`, arrays pre-sorted (entries by
  `(start_byte,end_byte,id)`, protected_spans by `(start_byte,end_byte,id)`), and the hashed object
  EXCLUDES `ledger_sha256` (it is derived + stored separately). A canonical hash vector is pinned in a test.
- **R3 (H3) — per-kind Layer-2 table.** `invariant-ledger.md` defines, per supported kind, the extracted
  shape + extractor + normalization + equality/weakening test + neighborhood window + id-assignment rule:
  `number_or_quantity`→quantity multiset (equality); `normative_statement`→modal multiset;
  `condition`/`exception`→marker multiset (relationship); `literal`/`defined_term`→normalized text;
  `protected_span`→byte hash. **Any other kind, or a modified region with no unique fingerprint match →
  ASK** (never a guessed survival). id is inherited by mapping the entry's region; a modified region
  falls back to `kind + sorted-atoms + left/right 3-token neighborhood hash`, unique match required.
- **R4 (H4) — mandatory attribution for `real` L3 concerns.** A `real` concern MUST carry `entry_ids` OR
  `original_ranges`; an unattributed `real` concern is treated as **GLOBAL** → every hunk
  `revertable=false` → apply mode blocks wholesale (no partial application). Validated during L3 output
  normalization.
- **R5 (M5) — overlap rules.** Ledger **entries MAY overlap** (containment / identical / partial — a
  number inside a condition inside a normative statement is normal). Only **protected_spans must be
  pairwise non-overlapping** and disjoint from editable ranges. Duplicate `id`s are rejected across the
  whole ledger.
- **R6 (M6) — map_region_status is a NEW backward-compatible function.** Current signature (increment-1,
  `scripts/slopslap_verification/editscript.py`): `map_region(edits, start, end) -> (int,int)` raising
  `MapError` when a boundary is strictly inside an edit — left UNCHANGED (increment-1 consumers intact).
  The new `map_region_status(edits, start, end) -> (interval_or_None, status)`:
  `unchanged` (no edit intersects), `modified` (an edit intersects but both boundaries map cleanly),
  `deleted` (an edit fully covers the region → tombstone at the insertion point, interval is the
  zero-width mapped point), `ambiguous` (a boundary strictly inside an edit, not fully covered). Under a
  non-overlapping ordered splice, a source interval maps to ONE contiguous revision interval, so
  `interval_or_None` suffices.
- **R7 (M7) — Layer-3 timeout is the injector's job.** `verify` wraps `semantic_fn` in try/except and
  maps ANY exception to `ambiguous` (never clean). Python can't force-interrupt an arbitrary callable, so
  the **eval-run injector owns the timeout/cancellation** (it controls the model client) — documented as
  the L3 contract; a well-behaved injector returns promptly or raises, and verify surfaces that as
  ambiguous. Named limitation, not hidden.

## Post-diff-review resolutions — WF5 on the built diff (`docs/reviews/increment-4-diff-2026-07-12.md`, 0 Crit / 5 High / 1 Med, all confirmed + fixed)

- **H1** — region-scoped number/unit/modality/negation preservation lives in **Layer 2 by design**
  (per-entry, stricter than L1's inventory), guaranteed complete by the H4 coverage fix — not omitted.
  edit-locality no longer silently vanishes: with edits present and `authorized_ranges is None`, verify
  now emits a `locality_unverified` **ASK** (fail-closed, never a silent skip).
- **H2** — L2 region-multiset equality is a NECESSARY deterministic check; a multiset-preserving
  reattachment is **Layer 3's** job and ACCEPT requires L3 clean, so the composition is sound (documented
  ceiling + `ponytail:` comment; attachment-level determinism is a v2 refinement).
- **H3** (bug) — `normalize_semantic` now validates EVERY concern to a closed dict shape (types,
  entry_ids, bounded ranges); a stray string/int concern maps to `ambiguous` instead of crashing verify.
- **H4** — `build_ledger` **raises `LedgerBuildError`** on a missing range, empty checks, or an unknown
  check — a malformed manifest can't silently yield a vacuous ledger that reaches ACCEPT.
- **H5** — a two-layer ACCEPT is no longer shippable: `proposal_status='ACCEPT'` ONLY when
  `semantic_status=='clean'`; `allow_two_layer` yields decision ACCEPT but `proposal_status='BLOCKED'`.
- **M6** — hunk decisions fold EVERY intersecting finding by the full `REJECT>ASK>SURFACE>ACCEPT`
  precedence (an ASK finding now marks its hunk ASK), so a per-hunk apply consumer can't retain an
  uncertain hunk.

## Out of scope
The rewriter itself (model), apply/backup (#apply-backup — consumes this verifier), the live semantic
model call (eval-run). Layer 1 owns the hard accept/reject; nothing here weakens it.
