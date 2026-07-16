# #98 — marketing prose misclassifies as `spec` and under-strips its cadence slop

**Workflow:** WF3 (fix-bug) · **Branch:** `fix/98-marketing-genre` · **Version:** 0.14.1 · **Date:** 2026-07-16

## Problem

Both `marketing-heavy` UAT candidates classified as genre `spec` in the v0.14.0 UAT run. `spec` is
the most-preservation-heavy profile and keeps the whole cadence class, so a marketing doc's
corporate-cadence slop (rule-of-three, repeated openers, transition clusters) was recommended
**keep** instead of **strip** — the tool blunted on exactly the genre the candidate set labels
"heavy". Recommendation-quality gap only; no safety/keystone impact (the failure direction is
under-stripping).

## Root cause (confirmed)

The issue's premise that "the spec heuristic trips on the structure" was **refuted**: both docs
carry **zero** RFC-2119 normative modals. The actual mechanism is the no-signal **asymmetric
fallback** — marketing prose emits no first-person / PRD / modal / path signal, so
`classify_genre` falls through to `MOST_PRESERVING_GENRE = "spec"` (`genre.py`), whose keep-set
retains the cadence class (`metrics.py` `_GENRE_KEEP_CLASSES`).

## Fix

A fifth genre, **`marketing`** (empty keep-set = strip-cadence, like `general`), detected by a
marketing/GTM **lexicon-density tier** placed LAST among the structural markers — any stronger
signal (declaration, path, personal, PRD, modals) still wins, and a genuinely ambiguous doc still
falls back to `spec`.

Three gates must all pass: **count ≥ 8**, **density ≥ 0.8 %**, **≥ 4 distinct surface forms**
(blocks a single repeated term such as a data-"retention" spec). Measured margin on the candidate
set: marketing-heavy docs run 22–37 hits/1k words (17 distinct forms); every other candidate is
≤ 2.3/1k (≤ 2 distinct).

Threaded through `GENRE_ENUM`, `_SCANNER_GENRES`, `_DECL_ALIASES`; the feedback schema's
`VALID_GENRES` and `_GENRE_KEEP_CLASSES` already carried forward-compat `marketing` entries. The
honest label also gives marketing prose its own `(genre, metric-class)` learning bucket — the
reason routing to `general` was rejected.

## Acceptance criteria

| AC | Result |
|----|--------|
| 1 — both marketing-heavy candidates land on a strip-cadence profile | PASS — `marketing`, cadence recommends strip (test + live `assemble.py audit`: densities 38/1022, 27/1210) |
| 2 — other 9 candidates unchanged vs the v0.14.0 UAT map | PASS — pinned by `test_uat_candidate_genre_map_no_regression` |
| 3 — asymmetric failure preserved | PASS — ambiguous/no-signal docs still → `spec`; single-lexeme + stronger-signal guards added |
| 4 — genre threaded consistently | PASS — enum/scanner/aliases updated; keep-set + `VALID_GENRES` pre-seeded; sync guard test green |

## Test evidence

- RED before GREEN: reproduction test failed `spec != marketing` before the fix.
- Suite: baseline **657 passed / 2 skipped** → **665 / 2**, exit 0 (+8 tests, 0 regressions).
- Candidate-file tests are `skipif`-guarded: the UAT candidates are internal briefings,
  deliberately untracked in this public repo (now gitignored). A fresh clone runs the always-on
  synthetic marketing fixture instead; the real-corpus assertions execute on the UAT host.

## Review

2-agent opus review (silent-failure-hunter + code-reviewer): 0 Critical/High/Medium, 4 Low — all
applied (stale 4-genre comments, distinct-surface-form comment honesty, `.gitignore` hardening)
or named here (real-corpus tests green-by-skip off-machine). Keystone verified intact: detection
universal, genre gates recommendation only, verifier still hard-gates every edit.
