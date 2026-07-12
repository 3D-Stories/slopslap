# Peer Consult — increment-4-ledger-verify-design.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Define a versioned, byte-canonical ledger and a verifier that produces both a document-level disposition and hunk-addressable findings. Canonical JSON uses UTF-8 plus RFC 8785 serialization; original-text coordinates are zero-based, half-open byte ranges [start_byte,end_byte), with SHA-256 over the exact original byte slice and no Unicode normalization. Layer 1 invokes the existing increment-1 hard gates unchanged. Layer 2 is a deterministic, ledger-directed re-extraction pass: it checks not merely that a region contains the same atom inventory, but that each atom remains attached to the same proposition or relationship. Layer 3 is an optional fresh-context semantic callable. Precedence is L1 hard failure, L2 preservation failure, ledger uncertainty, L3 real concern, L3 ambiguity, then acceptance. Every finding is attributed to original coordinates and intersecting edit hunks so suggest mode can block the proposal and apply mode can later revert only implicated hunks.

## Key decisions

- Ledger envelope: {schema_version, source_sha256, entries, protected_spans}. Reject unknown fields, enum values, duplicate IDs, invalid ranges, overlapping IDs, hashes inconsistent with original bytes, or non-canonical extracted shapes. Sort entries by (source.start_byte, source.end_byte, id) and protected spans by (start_byte,end_byte,id) before canonical serialization.
- Each entry is {id,kind,source:{start_byte,end_byte,text_hash},extracted,preservation,confidence}. IDs are stable ledger identities derived during build, not recomputed from revision text. confidence is an integer 0..1000 to avoid canonical floating-point ambiguity. Optional line coordinates may be emitted only in a separate display projection, never in canonical ledger JSON.
- protected_spans is the authoritative hard-gate table: {id,start_byte,end_byte,sha256}. A protected_span entry may reference the same id, but validation requires exact coordinate/hash agreement so two representations cannot diverge.
- Layer 2 does not collapse into Layer 1. Layer 1 compares scoped atom inventories and structural constraints; Layer 2 evaluates ledger-entry survival and attachment. Its deterministic MVP uses conservative rule-derived shapes such as {subject_anchor,predicate_anchor,object_atoms,qualifiers,polarity,modality,condition_ids,exception_ids,attribution_anchor,neighborhood_hashes}. It rejects only when a rule-supported relationship is demonstrably dropped, weakened, added, or reassigned; unresolved pairing becomes ledger uncertainty rather than a guessed match.
- Layer-2 matching first assigns the existing ledger id to candidates extracted inside the entry's mapped region. If that region was modified or widened, fallback matching uses kind-compatible fingerprints plus unchanged left/right token neighborhoods and proposition anchors. A unique match is compared; zero matches is dropped, multiple plausible matches is uncertain, and unmatched high-confidence revision atoms are additions. Purely lexical entries need no proposition parser; relationship_exact entries require a supported deterministic attachment rule or remain uncertain.
- build_ledger auto-derives: numbers, quantities, units, dates, identifiers, and explicit cross-references as byte_exact or lexically_exact at high confidence; normative modals and negation as semantic_exact at high confidence; rule-signaled conditions and exceptions as relationship_exact at medium-to-high confidence; quoted or glossary-pattern defined terms as lexically_exact; manifest-declared protected spans as byte_exact with confidence 1000. Attribution and causal claims are emitted only for explicit deterministic patterns. unsupported_intent, missing_support, and intentional_repetition are manifest-supplied unless an existing extractor has an unambiguous rule.
- Confidence controls automation, not preservation strength: high-confidence mismatches may reject; low-confidence or ambiguous source/extraction yields ASK. Confidence never permits a hard gate to pass or allows semantic review to override deterministic failure.
- semantic_fn has the exact call shape semantic_fn(original: str|bytes, revision: str|bytes, ledger: canonical-ledger-view) -> {verdict:'real'|'ambiguous'|'clean', concerns:[{code,message,entry_ids?:[id],original_ranges?:[{start_byte,end_byte}],revision_ranges?:[{start_byte,end_byte}]}]}. No edits, rewrite rationale, earlier verifier commentary, or chain-of-thought are supplied. Validate the returned shape and enum; exceptions, malformed output, or unverifiable coordinates become ambiguous, never clean.
- Decision precedence: any L1 hard failure is REJECT; any definite L2 dropped/weakened/added invariant is REJECT; uncertain ledger source or non-unique L2 match is ASK; L3 real concern is REJECT; L3 ambiguous is SURFACE; all preservation checks passing with L3 clean or semantic_fn omitted is ACCEPT. Omitting semantic_fn must be recorded as semantic_status='not_run', so callers can enforce a policy requiring Layer 3 without pretending it ran.
- Soft-style findings never cause a riskier rewrite or escalation. If safety cannot be deterministically ordered, return SURFACE; otherwise identify the safer variant, normally original. Suggest mode maps every non-ACCEPT disposition to proposal_status='BLOCKED'.
- verify returns {decision,proposal_status,semantic_status,findings,hunks,ledger_sha256}. Each finding includes layer, severity, code, message, entry_ids, original_ranges, revision_ranges, implicated_hunk_ids, and disposition. Each hunk result includes hunk_id, original_range, revision_range, decision, finding_ids, and revertable. This lets #apply-backup revert the union of failing hunks while preserving passing, non-dependent hunks.
- editscript.map_offset/map_region remain canonical for multi-hunk mapping. The required gap contract is explicit deletion handling: map_region must return a mapped interval plus status unchanged|modified|deleted|ambiguous, with boundary bias defined for insertions. deleted is a tombstone, not an empty successful mapping. A ledger entry spanning multiple or adjacent hunks implicates all contributing hunks; apply-backup must revert them as one dependency group.

## Risks

- Rule-based proposition attachment has limited linguistic coverage. Treating unsupported parses as successful comparison would create false assurance; they must become ASK or require Layer 3.
- Fallback neighborhood matching can mispair repeated language. Unique-match requirements and intentional_repetition annotations reduce this, but repeated boilerplate may still block safe rewrites.
- Per-hunk rollback can be unsafe when one invariant spans several hunks or when later hunks depend on earlier text. Dependency-group attribution is necessary; otherwise revert the whole proposal.
- Accepting when semantic_fn is absent may be inappropriate in production even though it is useful for deterministic unit tests. The caller must distinguish ACCEPT with semantic_status='not_run' from a fully verified acceptance.
- String inputs can obscure byte coordinates if decoded or normalized inconsistently. Verification should establish exact UTF-8 bytes and source_sha256 before any extraction or mapping.
- Duplicating protected-span information across entries and protected_spans can drift unless validation enforces identity or the implementation uses one internal record projected into both views.
- A semantic callable may return persuasive but invalid findings. Its result must remain advisory beneath deterministic failures, undergo schema validation, and never mutate ledger evidence.

## Sketch

build_ledger(original, manifest): validate UTF-8 bytes and manifest regions; call existing atom extractors per region; create conservative typed entries and explicit relationship links; add manifest protected spans; validate ranges/hashes/enums; sort; canonicalize; return Ledger.

verify(original, edits, ledger, semantic_fn=None):
1. Reconstruct revision and canonical hunk IDs from the edit script; verify ledger source_sha256.
2. Run existing protected-span, scoped atom, new-claim, locality, and Markdown gates. Convert failures to L1 findings with original/revision ranges and hunk IDs.
3. For every ledger entry, map its half-open source region with map_region. A deleted mapping is a dropped-entry finding. Otherwise re-extract the same kind/shape from the mapped region, match uniquely by inherited id or fingerprint plus neighborhood, and compare according to preservation. Re-extract revision regions for unmatched additions.
4. If enabled, call semantic_fn with only original, revision, and the canonical ledger view; validate and normalize its verdict and concerns.
5. Fold findings using strict precedence REJECT > ASK > SURFACE > ACCEPT. Compute each hunk's decision from intersecting findings and group cross-hunk invariants.
6. Return the structured VerifyResult. In suggest mode, only ACCEPT is shippable; all other outcomes are BLOCKED. A future apply consumer reverts every failing dependency group, then reruns verification on the resulting revision.

---
_Peer proposal (report-only). Synthesize at your discretion._
