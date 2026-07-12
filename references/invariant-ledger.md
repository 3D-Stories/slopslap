# Invariant ledger + 3-layer verification + decision rule

The ledger is the machine-readable contract shared by rewrite and verify: what a rewrite must
preserve. **A rewrite you do not verify is a rewrite you do not ship.** Layer 1 (deterministic
code) OWNS the hard accept/reject; no model output overrides a deterministic hard failure.
Implementation: `scripts/slopslap_verification/ledger.py` (reuses the increment-1 checkers).
Design + review trail: `docs/planning/increment-4-ledger-verify-design.md`.

## Envelope
```
{ "schema_version": 1,
  "source_sha256": "<sha256 of the exact original utf-8 bytes>",
  "entries": [ Entry, ... ],
  "protected_spans": [ {id, start_byte, end_byte, sha256}, ... ] }
```
`Entry = {id, kind, source:{start_byte,end_byte,text_hash}, extracted, preservation, confidence}`.
- **Coordinates are ORIGINAL-byte offsets, half-open [start,end)**; any line coords are display-only,
  never in canonical JSON.
- `confidence` is an **integer 0..1000** (no float ambiguity). Confidence controls AUTOMATION, not
  preservation strength: a high-confidence mismatch may REJECT; a low-confidence/ambiguous source → ASK.
- Closed `kind`: literal · number_or_quantity · normative_statement · condition · exception ·
  causal_claim · attribution · defined_term · cross_reference · unsupported_intent · missing_support ·
  intentional_repetition · protected_span.
- Closed `preservation`: byte_exact · lexically_exact · semantic_exact · relationship_exact · surface_only.

## Validation (`validate_ledger`)
Rejects: `source_sha256` inconsistent with the original bytes; a bad enum; a duplicate `id`
(entries or protected_spans); an out-of-bounds range; a `text_hash`/`sha256` inconsistent with the
original slice; a non-integer or out-of-range confidence; **protected_spans that pairwise overlap**.
**Ledger ENTRIES MAY overlap** — a number inside a condition inside a normative statement is normal;
only protected_spans must be disjoint (and disjoint from editable ranges).

## Canonical serialization (byte-exact; design R2)
`canonical_bytes = json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`
with **no trailing newline**. Arrays are pre-sorted: entries by `(start_byte, end_byte, id)`,
protected_spans by `(start_byte, end_byte, id)`. The hashed object EXCLUDES `ledger_sha256` (it is
derived and stored separately). `ledger_sha256 = sha256(canonical_bytes)`. A canonical hash vector is
pinned in `tests/test_ledger.py::test_canonical_serialization_vector`.

## The 3 layers (rewriter never verifies itself)
1. **Deterministic integrity (CODE, owns hard accept/reject):** protected-span hashes, no-new-claim
   atoms, Markdown structure, and (when authorized ranges are supplied) edit-locality — the increment-1
   gates. Any FAIL → REJECT; a gate FIXTURE_ERROR → REJECT.
2. **Per-entry survival / attachment:** for each entry, `map_region_status` its source region:
   `deleted` → dropped (REJECT); `ambiguous` → uncertain (ASK); `unchanged` → survives; `modified` →
   re-extract the entry's kind-shape and compare.

   | kind | extracted shape | equality/weakening test | on no rule |
   |---|---|---|---|
   | number_or_quantity | quantity multiset (value+unit) | exact multiset equality | — |
   | normative_statement | {modals: multiset, neg: multiset} | exact equality | — |
   | condition / exception | condition-marker multiset | exact equality | — |
   | literal / defined_term | whitespace-normalized text | exact equality | — |
   | *(any other kind)* | — | — | **ASK** (never guessed) |

   A modified region with no deterministic rule, or a non-unique fingerprint match, is **ASK**, never a
   guessed survival. (Fingerprint fallback for a shifted region: `kind + sorted atoms + left/right
   3-token neighborhood`, unique match required.)
3. **Adversarial semantic (optional, fresh context):** `semantic_fn(original, revision, ledger_view)`
   given ONLY those three — no edits, rationale, or chain-of-thought. Returns
   `{verdict:'real'|'ambiguous'|'clean', concerns:[{code,message,entry_ids?,original_ranges?,revision_ranges?}]}`.
   Output is schema+enum validated; an exception, malformed output, or unverifiable coordinates ⇒
   **ambiguous, never clean**. A `real` concern MUST carry `entry_ids` OR `original_ranges`; an
   unattributed `real` concern is GLOBAL → every hunk `revertable=false`. **The injector (eval-run) owns
   the timeout** — `verify` maps any exception to ambiguous but cannot force-interrupt a hanging callable.

## Decision rule (strict precedence REJECT > ASK > SURFACE > ACCEPT)
- any L1 hard failure → **REJECT**; any definite L2 dropped/weakened/added → **REJECT**; L3 real → **REJECT**.
- uncertain ledger source / non-unique L2 match → **ASK**.
- L3 ambiguous → **SURFACE**. Soft style never escalates (if safety can't be ordered → SURFACE, else keep
  the safer variant — usually the original).
- all preservation passing AND L3 `clean` → **ACCEPT**.
- **L3 omitted → SURFACE by default**, `semantic_status='not_run'`, `proposal_status='BLOCKED'` (never a
  silent two-layer ACCEPT). A caller may pass `allow_two_layer=True` to authorize a two-layer ACCEPT
  explicitly (deterministic tests / suggest preview); `semantic_status` still reads `not_run`.
- **suggest** maps every non-ACCEPT → `proposal_status='BLOCKED'`. **apply** (#apply-backup) reverts the
  union of failing dependency groups using the per-hunk `revertable` + `finding_ids`.

## `verify` return
`{decision, proposal_status, semantic_status, findings, hunks, ledger_sha256}`. Finding:
`{id, layer, severity, code, message, entry_ids, original_ranges, implicated_hunk_ids, disposition}`.
Hunk: `{hunk_id, original_range, decision, finding_ids, revertable}`.
