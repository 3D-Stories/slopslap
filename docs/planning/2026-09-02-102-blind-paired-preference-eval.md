# #102 — Blind paired-preference eval of slopslap's own output

Issue: https://github.com/3D-Stories/slopslap/issues/102 · Filed 2026-09-02 · Type: feature · Complexity: M · Task class: production

```callout
info | Owner decision 2026-09-02
Build this eval first. Rule borrowing (Kobak's 379 corpus-proven excess words, a public-domain known-human baseline for calibrate.py) and the design-doc-publish integration wait for a measured result to stand on.
```

## Problem

slopslap has strong safety machinery — a byte-exact verifier and per-finding authorization bound to `source_sha256` — and no measurement that its edits read better.

- `README.md:203-205` lists the cross-model LLM-judge A/B as "currently secondary/not-run".
- `scripts/eval/run_eval.py:218` reports `judge: not_run`.
- `scripts/eval/judge.py` is a complete scoring scaffold (9 dimensions, 0/1/2 against a baseline, median over 3 or more blinded trials) with no live judge wired to it.
- `scripts/slopslap_corpus/calibrate.py` is measure-only with 0 usable calibration points.

## Evidence

A research run on 2026-09-02 (rawgentic workspace `claude_docs/research/2026-09-02-humanize-prior-art.md`, 8 lanes) found that the only humanizing methods with human-rater proof use blind paired preference.

| Source | What was measured | Result |
|---|---|---|
| LAMP, "Can AI writing be salvaged?" — https://arxiv.org/html/2409.14509v5 | 1,057 LLM paragraphs edited by professional writers; 600 blind judgments | Writer-edited text preferred in 65% of comparisons; raw LLM text last 60% of the time |
| Writing Quality Reward Model — https://arxiv.org/abs/2504.07532 | Best-of-20 selection judged by 9 professional writers | Preferred 66% overall, 72.2% when the score gap exceeded 1 point |
| MohamedAbdallah-14/unslop | Blind LLM-judge A/B, 7 fixtures, 3 runs | 21 of 21 — the eval slopslap designed and never ran |
| Substack 8-method test | Detector score versus a writing-quality rubric | Moved in opposite directions |
| StoryScope — https://arxiv.org/html/2604.03136 | LAMP-style surface edits versus discourse-level detection | Detection moved only from 95.5% to 93.9% |

## Acceptance criteria

1. A script under `scripts/eval/` takes N pairs (original paragraph, slopslap-applied paragraph), presents each pair as a randomized blind A/B, and records which side the rater preferred. Side order is randomized per pair and recorded with the pick.
2. **Human mode:** a static page or a CLI records one rater's picks into a JSON file bound to each pair's `source_sha256`, the same binding `scripts/slopslap_review/review.py` uses for `decisions.json`. The page shows nothing that reveals which side is slopslap's output.
3. **LLM-judge mode:** the existing `scripts/eval/judge.py` scaffold is wired to a live judge through `scripts/slopslap_invoke/invoke.py` and runs under `SLOPSLAP_LIVE=1`. Offline it stays `not_run` and says so. The judge model differs from the model that produced any rewrite.
4. A fixture set of 5 to 10 real design-doc paragraphs with verbatim, licence-clean text, in the `tests/fixtures/eval/pair-*` shape (`original.md`, the applied output, `fixture.json` with `provenance`). The applied side is produced by `assemble.py apply` on the original, never hand-written.
5. A results document under `docs/reviews/` reports human and LLM-judge results in separate sections, with pair counts and preference percentages. It never reports a single "AI %" or sloppiness score.
6. `README.md` replaces the "currently secondary/not-run" line with the measured result in the form "run, N pairs, X% preference", or an honest statement of what did not run.
7. `pytest -q` passes, with no change to any scanner rule, table, threshold or genre profile.

## Scope

**In:** the eval script, both modes, the fixture set, the results document, the README line.

**Out:** any change to `scripts/slopslap_scan/tables.py`, `scripts/slopslap_scan/metrics.py` or the genre gate; any new rule (the Kobak word list); the calibration corpus; the design-doc-publish integration; detector-score measurements of any kind.

## Affected components (verified to exist)

| Component | Role |
|---|---|
| `scripts/eval/judge.py` | The A/B scaffold to wire |
| `scripts/eval/run_eval.py` | Reports `judge: not_run` today |
| `scripts/eval/semantic.py` | The `SLOPSLAP_LIVE` gating pattern to reuse |
| `scripts/slopslap_invoke/invoke.py` | `invoke_semantic` (line 286), the `claude -p` transport |
| `scripts/slopslap_review/review.py` | The `source_sha256` binding pattern |
| `tests/fixtures/eval/pair-*` | The fixture shape |
| `docs/reviews/` | Results document home |
| `README.md` lines 203 to 205 | The line to replace |

## Risk

- **Product:** low. No rule changes ship.
- **Claim:** medium. 5 to 10 pairs and one rater is a small sample. The results document must say so and must not overstate.
- **Cost:** a live judge run makes model calls and needs `SLOPSLAP_LIVE=1`.

## Related

None open covers this. #101 (correspondence genre profile) and #42 (authenticated audit handle) are unrelated.

## WF2 Step 3 — design note (small-standard lane, 2026-09-02)

Authored inline by the WF2 orchestrator (model `claude-fable-5-1`) after the Step 2 codebase analysis. Lane form: one approach, file list, failure modes, security, platform dependencies. Owner decisions taken at bedtime (2026-09-02T07:55Z): small-standard lane; judge model **gpt-5.6-sol** (Codex CLI); merge when green for this run; the owner is the human rater and rates after waking.

### Chosen approach — model-lane edits, engine-applied fixtures, one stdlib script

**A (chosen).** A new `scripts/eval/preference.py` (stdlib only) with four subcommands — `build`, `human`, `judge`, `report`. Fixtures `tests/fixtures/eval/pair-102-NN-<slug>/` carry a verbatim `original.md` and an `applied.md` that `scripts/slopslap_assemble/assemble.py apply` produced from a committed `edits.json`. The judge transport is a new public `invoke_judge` in `scripts/slopslap_invoke/invoke.py` backed by a Codex runner; the judge request and strict response contract live in `scripts/eval/judge.py`, whose existing `Trial` / `evaluate` / `run_trials` scaffold is reused unchanged.

**B (rejected) — deterministic findings path for the applied side** (`assemble.py apply --decisions` accepting every strip recommendation). Rejected because a strip finding's proposed rewrite is a whole-Unit delete (`scripts/slopslap_review/findings.py:_unit_spans_for` + `_precheck`), so a one-paragraph fixture's applied side would be empty. slopslap's real output path is the model lane: the session applies `skills/slopslap/SKILL.md`, serializes an edit-script, and the verifier-gated engine applies it (`commands/apply.md`).

**C (rejected) — `claude -p` judge through the existing `_run_claude`.** Rejected by the owner's judge choice (gpt-5.6-sol), which also keeps the judge cross-vendor from the rewrite engine. `run_eval.py:219` already names "Codex gpt-5.6-sol" as the documented follow-up.

### Fixture set (AC4)

- Source: paragraphs from the owner's two PUBLIC repos only — `3D-Stories/slopslap` (this repo, `docs/planning/`) and `3D-Stories/design-doc-publish` (MIT, commit `0aa220d3c5a392ea43e85de6659c7856a4b4853d`). The other workspace repos are private (checked with `gh repo view` 2026-09-02) and are excluded so no private text is published.
- Selection: paragraphs of 40–170 words where the measure-only scanner reported at least one tell (126 candidates). The engine (this session, applying SKILL.md) diagnoses each; a paragraph slopslap abstains on yields no pair and is counted as an abstention in the results doc. Target 6–10 pairs; the AC floor is 5.
- Per pair: `original.md` (exact bytes, trailing newline preserved), `edits.json` (the engine's edit-script in original byte coordinates), `applied.md` (bytes produced by `assemble.py apply`), `apply_result.json` (the apply `RunResult`, which carries no source bytes), `fixture.json` — loader-valid, `pair: true`, `clean_file: "applied.md"`, `control: false`, `seeded_defects` = the typed diagnosis records, `provenance` = repo + path + commit + line range + license, and an `eval_pair` block `{schema_version, engine_model, source_sha256, applied_sha256, apply_exit, semantic_mode, edits_file, apply_result_file}`. `engine_model`, `apply_exit: 0`, `edits_file` and `apply_result_file` are all REQUIRED by the loader: it replays the edit script and refuses a pair it does not reproduce, and it refuses an `apply_result.json` whose status is not `ok` or whose audit stage binds to a different `source_sha256`. **What replay does NOT prove, stated plainly (Step 11 review):** that the ENGINE authored the edit script. A hand-written output paired with a whole-file replacement and freshly computed manifest hashes satisfies every check here. A cryptographic engine receipt was proposed and DECLINED: the actor who could forge one is a repository committer, who can equally edit the verifier and any key stored beside it, so the signature would raise no bar against the only actor that matters.
- Apply runs with `SLOPSLAP_LIVE=1` where `claude -p` auth is available so Layer 3 is a real verdict (`semantic_mode: live`); if unavailable the pair records `semantic_mode: offline_stub` honestly.
- Guard test: for every `pair-102-*`, `apply_edits(original, parse_edits(edits.json)) == applied.md`, both sha256 fields match, `eval_pair.apply_exit == 0`, and the offline `assemble.py run` dry-run on a temp copy reaches `verify.decision == "ACCEPT"`. The existing `tests/test_golden_pairs.py` still passes (its `clean_file` field is honored).

### Blinding protocol (AC1, AC2)

*(Revised at WF2 Step 3 pass 2, after the Step 4 self-review (F2) and the incremental verifier's findings V1–V4 and L1–L3. Picks are bound to the bytes the rater saw; roles are recovered per fixture, never by seed or by code order.)*

- **`build [--seed S] --out pairs.json`.** Collects every `pair-*` manifest carrying `eval_pair` (the two hand-written pairs are excluded — their after side is not slopslap output), sorts by directory name, computes `pair_id = sha256(source_sha256 + ":" + applied_sha256)[:16]`, generates `run_id = secrets.token_hex(16)` ONCE per build, and assigns side order per pair from `random.Random(seed)` in that sorted order (`seed` = `--seed` or `secrets.token_hex(8)`, recorded). Refuses with exit 2, naming the pair, when: zero eval pairs are found; a fixture has `source_sha256 == applied_sha256` (identical sides — a no-op apply is an abstention, never a pair); two fixtures share a `pair_id`. Output `pairs.json` (blind, PRIVATE — never handed to a rater): `{schema_version, run_id, seed, created_at, pairs: [{pair_id, token, source_sha256, a_text, b_text, a_side_hash, b_side_hash}]}` with `side_hash = sha256(run_id + ":" + text_bytes)` and `token = secrets.token_hex(8)` per pair per build — the only pair identifier the rater-facing page may carry. Determinism (tested): the same seed over the same fixture set gives the same side order and the same `pair_id`s; `run_id`, `created_at` and every `token` differ per build and are excluded from that test. **A SUPPLIED blind file is validated, not trusted** (`validate_blind_json`, added at the Step 11 review): its pair ids must equal the current fixture id set exactly, with no duplicate and no reused token, and each pair's two texts, `source_sha256` and both side hashes must recompute from the fixture bytes under the file's own `run_id`. Without that, a trimmed `pairs.json` holding one favorable pair drove a judge run that reported `completed` over the subset — the opposite of the drift refusal this design promises. Validating a blind file therefore requires the fixture set to be NAMED, so `--pairs` without `--fixtures` validates against the repository default.
- **What each artifact reveals, stated exactly — CORRECTED at the Step 8a review round.** There are TWO artifacts, and the split is the whole of the blinding. The PRIVATE blind file (`pairs.json`) carries `source_sha256` and `pair_id` and is an operator artifact; it never reaches a rater. The RATER-FACING page carries only the two texts, their two salted side hashes, the per-pair `token` and `run_id` — and it serializes that JSON with EVERY `<` and `>` escaped as `\u003c`/`\u003e`, so no fixture byte leaves a literal angle bracket in the page at all. A Step 11 reviewer read the older `</` escape as lowercase-only; that was wrong (`</` carries no letter, and `</SCRIPT>`, `</ScRiPt>` and `</script >` all measured as escaped), but the guarantee now holds without anyone reasoning about HTML raw-text end-tag rules, and a test asserts it.
  - The design first asserted that `source_sha256` "must ride along for the AC2 binding", and shipped it in the page. **That premise was false, and the shipped page violated AC2's second sentence:** a rater with devtools could hash each visible text and compare it with `source_sha256` to read the source side straight off. `pair_id = sha256(source_sha256 + ":" + applied_sha256)[:16]` de-blinds the same way and needed no `source_sha256` at all — the rater computes both candidate orderings from the two texts and keeps the one that matches.
  - AC2's binding lives on the PICKS FILE, not on the page. So the page carries neither field, and `report` re-binds each pick to its fixture from the side hashes (the same salted hashes it already used to recover roles) and writes `source_sha256` into the published record. The binding is preserved at the point that matters and the page reveals nothing.
  - Remaining channels, all needing repository access, none available to a rater at the page: the fixture directories, the private `pairs.json`, and `judge.json` (post-hoc by design). The page never carries the seed, `source_sha256` or `pair_id`.
- **`human --rater NAME (--pairs pairs.json | --seed S) --out picks.json [--static page.html]`.** With `--pairs` it reads an existing blind file; without it, it calls the same `build` function internally (fresh `run_id`, the given or a random seed). Terminal loop (`a` / `b` / `=` / `s`kip / `q`uit) or a self-contained static page (every string rendered with `textContent`, per-pair A/B/no-preference buttons, progress, Export downloads the same JSON). `picks.json`: `{schema_version, run_id, rater, mode, picks: [...]}` — `run_id` copied verbatim from the blind file, no seed. A TERMINAL pick carries `{pair_id, token, source_sha256, pick, a_side_hash, b_side_hash}`; a PAGE pick carries `{token, pick, a_side_hash, b_side_hash}` and no fixture identifier, because the page holds none — `report` resolves it by side hashes. Each pick is self-describing: the side letter plus the salted hash of what sat on each side records the side order with the pick (AC1).
- **`judge (--pairs pairs.json | --seed S) --model gpt-5.6-sol --trials 3 --out judge.json`.** Per pair, per trial, a fresh side order from `random.Random(f"{seed}:{pair_id}:{trial}")`; request = `judge.build_judge_request(a_text, b_text)`; transport `invoke_judge`; strict parse; `judge.trial_from_blind(parsed, applied_side)` maps each of the nine dimensions (`A`/`B`/`equal`) to the scaffold's 0/1/2 candidate-vs-baseline scores (applied wins → 2/0, equal → 1/1, loses → 0/2); `judge.evaluate(trials)` gives the per-pair verdict. Each trial record stores `a_side_hash`, `b_side_hash`, `applied_side`, `preferred_side` (this file is post-hoc and reveals roles by design). Offline (`SLOPSLAP_LIVE != "1"`): writes `{status: "not_run", reason}` and exits 0 (AC3). Live transport failure: `status: "failed"` with the invocation status — never laundered into `not_run`. `completed` (and exit 0) requires EVERY pair to reach a present, non-errored verdict on a full set of trials, over a blind file that covers the whole fixture set; anything in between is `status: "partial"` with exit 4 and a reason naming how many pairs landed. An errored pair's trials are counted in `trials_valid` but excluded from `trials_scored` and from every percentage, which is what the results doc already claimed. `majority_applied` is a WIN claim and the results document prints it as one, so it is false unless the pair is scored — an errored or short pair has won nothing, however its few answered trials fell (Step 11 review). The judge process holds the fixture set, so identical sides are refused here exactly as in `build`.
- **Cross-model guard.** `judge` refuses (exit 2, no call) when the judge model token-matches any `eval_pair.engine_model` in the fixture set, using the same token rule as `invoke._model_confirmed`.
- **`report [--picks P ...] [--judge J] --out results.md [--json results.json]`.** Role recovery is per fixture, in this order: (1) locate the fixture by the pick's `pair_id` when it carries one — an unknown `pair_id` refuses the picks file (exit 2, naming it) — else by matching the pick's two side hashes against each fixture's two files, which is how a page pick with no fixture identifier resolves; (2) require the pick's `source_sha256` to equal that fixture's `source_sha256` when the pick carries one, and refuse a pair picked twice in one file; (2b) **`--pairs` is REQUIRED with `--picks` (Step 11 review)** — side hashes recompute from repository-visible fixture bytes under whatever `run_id` a picks file names, so a self-consistent picks file proves only that its author can run sha256, and changing both `run_id` and rater slipped past the `(run_id, rater)` duplicate check; `report` now binds every picks file to the blind file the operator issued, requiring a matching `run_id` and a `token` that file actually handed out carrying the same two side hashes (an authority-signed rating-session manifest was proposed and DECLINED for the same reason as the engine receipt); (3) recompute `sha256(run_id + ":" + bytes)` for THAT fixture's `original.md` and `applied.md` under the picks file's `run_id`, and require the two side hashes to match exactly one file each, with the recovered role set exactly `{original, applied}` — equal side hashes, a hash matching both files, or both sides matching one file refuse the picks file (identical sides can never count as a preference). Then score. `--json` renders, per pick, the recovered side letter of the applied text, so the side order is readable without fixture access. Renders separate `## Human raters` and `## LLM judge` sections with pair counts and preference percentages, plus Method, Fixture set (with abstentions), Limitations, Reproduce. A supplied `judge.json` is VALIDATED before it is published (`validate_judge_json`): a closed status set, every `pair_id` present in the current fixture set and named once, every trial's side hashes matching that fixture's own bytes under the file's `run_id`, every recorded role recomputed from the side it names, and every summary total recomputed from the file's own trials — so a stale or edited file cannot supply arbitrary percentages. Since the Step 11 review the pair-id set must EQUAL the fixture set (not merely be a subset of it), and the validator rebuilds every trial from its recorded per-dimension roles, re-runs `judge.evaluate`, and refuses a mismatch on `present`, `errored` or `beat`, on any per-pair counter, on `majority_applied`, or on `pairs_majority_applied` and `pairs_beat` — all of which were rendered straight into the results table without ever being recomputed. Two picks files sharing a rater and `run_id` are refused. A guard test asserts the rendered doc contains both headings and never the strings `AI %` or `sloppiness score` (SKILL.md anchor:ratings).

### File changes

| File | Change |
|---|---|
| `scripts/eval/preference.py` | NEW — `build` / `human` / `judge` / `report`; stdlib only; `main(argv)` returns an exit code (0 ok · 2 invalid input or refusal · 4 execution failure). |
| `scripts/slopslap_invoke/invoke.py` | ADD `_run_codex(...)` (module-private, same lockdown philosophy as `_run_claude`: fresh temp cwd, env scrubbed to `HOME`, `PATH` and the `CODEX`/`XDG` prefixes ONLY, own process group, SIGTERM→SIGKILL on timeout, the SCHEMA file created 0600 while the `-o` answer file is the CLI's to create (the temp dir itself is `mkdtemp`, 0700, and that is the real protection), statuses `ok|timeout|cli_missing|nonzero_exit|parse_error`) and public `invoke_judge(request, *, model, schema, timeout_s=180.0, executable=None, status_sink=None) -> Optional[dict]`. `invoke_semantic` and `_run_claude` untouched. |
| `scripts/eval/judge.py` | ADD `JUDGE_SCHEMA`, `build_judge_request`, `parse_judge_response` (fail-closed), `trial_from_blind`, `live_judge_available()`; existing API unchanged (10 pinned tests). |
| `scripts/eval/run_eval.py` | Judge note text only: points at `preference.py judge` under `SLOPSLAP_LIVE=1` and the results doc; `status` stays `not_run` (pinned enum in `tests/test_eval_run.py:110`). |
| `tests/fixtures/eval/pair-102-*/` | NEW fixtures (5–10). |
| `tests/test_preference.py`, `tests/test_judge.py` (+), `tests/test_invoke_judge.py` | NEW tests: build determinism and blindness, role recovery by salted side hash, picks binding + drift refusal, static page content, CLI human loop via scripted stdin, judge offline `not_run`, judge live path with an injected transport, same-model refusal, malformed response → errored trial, report sections + banned strings, fixture reproducibility guard, `_run_codex` via a fake executable (ok / missing / timeout / bad JSON). |
| `docs/reviews/2026-09-02-102-blind-paired-preference-results.md` | NEW — rendered by `report` from the live judge run; human section states "0 raters yet" until the owner rates. |
| `README.md` | Replace the "currently secondary/not-run" line (README.md:203-205) with the measured form; changelog entry; version bump per repo convention. |
| `.rawgentic.json` | `ci` section added (learning-config; `.github/workflows/test.yml` exists). Carries a pre-existing uncommitted reformat + `contextMeter` block — flagged in the PR body. |
| `docs/planning/2026-09-02-102-blind-paired-preference-eval.{md,html}` | This doc (WF1 artifact + this section), re-rendered with design-doc-publish 5.0.0. |

No new Python dependency. Estimated diff: about 1,200–1,500 inserted lines including fixtures and docs; one PR (the pieces are not separable — the results doc needs the fixtures and the script).

### Failure modes

- Codex CLI missing or not logged in under `SLOPSLAP_LIVE=1` → `judge` status `failed`, reason names the invocation status; never `not_run`.
- A pair with fewer than 3 valid trials → `judge.evaluate` returns `errored`; the pair is reported as errored, never dropped or counted as a win.
- Same judge and engine model → refused before any call (exit 2).
- Zero eval pairs found → `build` refuses (exit 2); a vacuous 0-pair run can never render a percentage.
- Picks bound to a different fixture set (sha mismatch) → that picks file is refused with the offending `pair_id`.
- Fixture drift (edits no longer reproduce `applied.md`) → guard test fails.
- A judge response outside the schema (unknown dimension, bad enum) → that trial errors; the parser never invents a score.
- Identical sides (`source_sha256 == applied_sha256`) → `build` and `judge` refuse the pair (exit 2); `report` refuses a pick whose recovered roles are not exactly {original, applied}.
- An unknown `pair_id` in a picks file → refused (exit 2, naming it); a duplicate `pair_id` across fixtures → `build` refuses; the same pair picked twice in one picks file → refused; two picks files with one rater and one `run_id` → refused.

### Security

- The paragraphs are untrusted data inside the judge request: a fixed instruction names them as data, and the reply is validated locally against a closed schema (enums, exact dimension set) — prompt wording is never schema enforcement (same stance as `contract.py`).
- The static page renders every string via `textContent`; no HTML from fixtures reaches the DOM. Export uses a Blob download, like `review.py`.
- The Codex runner writes only inside its own temp dir. **CORRECTED at the Step 11 review:** this said "schema + `-o` files created 0600", and only the schema is ours — we create it with `os.open(..., 0o600)`, while the `-o` answer file is created by the CLI under its own umask. The protection is therefore the DIRECTORY: `tempfile.mkdtemp` makes it 0700, so no other user can reach either file. The code docstring already said this; the doc overclaimed. It runs `--sandbox read-only --ephemeral`, and scrubs the child env to `HOME`, `PATH` and the `CODEX`/`XDG` prefixes. **KNOWN LIMIT, MEASURED at the Step 11 review and DEFERRED:** `--sandbox read-only` denies WRITES, and that is all it denies. Probed directly on this host with `codex sandbox -c 'sandbox_mode="read-only"'` (codex-cli 0.150.1): the child could read `$HOME/.codex/auth.json`, `/etc/hostname` and `~/.ssh`, and `-c 'sandbox_permissions=[]'` did not close it — `disk-full-read-access` is an opt-in for something already permitted. So a prompt-injected paragraph that persuades the judge to read a host file and return it in `reason` has a path into `judge.json`, which is committed. The judge instruction states that the texts are data and never instructions, which is a mitigation, not a boundary. There is NO CLI-level read-deny knob, so the real fix is the reviewer's own first recommendation — a non-agentic model API with no filesystem or shell tools — or an OS-level mount namespace around the child. Both are out of scope for #102 and are the owner's call. Today's exposure is bounded by who can commit a fixture, because every judged paragraph in the repository is a verbatim public paragraph the owner selected. **CORRECTED at the Step 8a review round:** it first reused the Anthropic transport's allowlist, which passed every `CLAUDE_*`/`ANTHROPIC_*` variable — an API key among them — into a different vendor's process. The judge needs neither, and Codex auth lives under `HOME` (`~/.codex`).
- No secrets in code or fixtures; auth comes from the host's Codex login.

## Platform / external dependencies

platform_apis:
- api: `codex exec -m <model> --sandbox read-only --output-schema <f> -o <f> -c model_reasoning_effort=<e> --ephemeral --color never -c project_doc_max_bytes=0 -C <tmp> --skip-git-repo-check -` with the prompt on stdin, codex-cli 0.150.1
  feasibility: verified via spike — run live 2026-09-02T08:00Z with `-m gpt-5.6-sol`: exit 0 in 7 s, the `-o` file held a schema-conforming JSON object (`{"preferred":"B","reason":...}`), `codex login status` = "Logged in using ChatGPT" (session notes, Step 3 probe)
  failure: fail-silent — the CLI never echoes the model that answered (no `model` field in any `--json` event), so a substituted model would go unnoticed
  surface: `judge.json.model_confirmed` is always `false` for this transport and the results doc + README line say "model pinned by `-m`, not echoed"; a non-zero exit, timeout or unparseable `-o` file surfaces as `status: failed` with the invocation status
- api: `scripts/slopslap_assemble/assemble.py apply --path P --edits E.json` and library `apply_edits` / `parse_edits`
  feasibility: verified via existing-call-site — `commands/apply.md` step 3, `tests/test_apply_from_decisions.py:test_approved_safe_hunk_applies_and_changes_file`, `tests/helpers.py:make_envelope`
  failure: fail-loud — exit 2/3/4 with a JSON `RunResult`; nothing mutates on failure
- api: `SLOPSLAP_LIVE == "1"` live gate
  feasibility: verified via existing-call-site — `scripts/eval/semantic.py:28`, `tests/test_invoke_live.py:76`
  failure: fail-loud — offline is an explicit `not_run` record
- api: `claude -p` Layer-3 semantic pass during the fixture apply (`invoke_semantic`, model `sonnet`)
  feasibility: verified via existing-call-site — `scripts/slopslap_invoke/invoke.py:286`, `tests/test_invoke_live.py:80`
  failure: fail-loud — `semantic_invocation_failed` → apply exit 4; the pair records `semantic_mode`

## WF2 Step 8 — implementation outcome (2026-09-02)

- Shipped: `scripts/eval/preference.py` (build / human / judge / report), `invoke_judge` + `models_match` in `scripts/slopslap_invoke/invoke.py`, the blind A/B contract in `scripts/eval/judge.py`, 3 `pair-102-*` fixtures with a reproducibility guard, the results document `docs/reviews/2026-09-02-102-blind-paired-preference-results.md`, and the README line.
- **AC4 shortfall, decided while the owner slept:** 3 pairs shipped against a floor of 5. 31 public paragraphs sampled → 18 authorized under the auto-classified `spec` genre → 9 engine proposals → 3 verifier ACCEPTs. No genre was declared to widen edits and no private text was used; the results document states the shortfall and the owner's four ways forward. The PR is left OPEN (merge-when-green assumed the ACs were met).
- Live judge (gpt-5.6-sol, 9 trials): applied preferred in 5 of 9 trials, applied majority on 2 of 3 pairs. Human mode: built, 0 raters.
- Two product limitations found (follow-ups, not filed — issue throttle): a review-stage `edit` on any invariant-bearing paragraph is always rejected (`entry_dropped` for every entry inside the replaced span, even when preserved byte for byte); `technical` is in the genre table but not declarable (`genre._DECL_ALIASES`).
