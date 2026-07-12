# Genre profiles — preservation priorities (elaborates SKILL.md; adds no safety rule)

Genre modifies the diagnosis and rewrite constraints; it **never decides prose is "bad"** and never
authorizes an edit (keystone rule). Classify per region, not whole-document.

## Classification precedence
explicit user declaration > file/repo context > structural markers > content inference.
Segment at headings/blocks; merge adjacent same-profile regions.

## Asymmetric-failure rule
On **low genre confidence, use the MOST preservation-heavy applicable profile.** Stiffening a
marketing paragraph is a small harm; changing a spec's normative vocabulary is a large one — so when
unsure between two profiles, apply the one that preserves more.

## Profiles
| profile | what to preserve hardest | what harm looks like here |
|---|---|---|
| general-prose | meaning, the author's cadence | genuine emptiness; unsupported claims |
| technical-doc | identifiers, commands, exact terms | vagueness where precision was available |
| spec | normative modals, numbers, **parallelism/repetition (correctness infra)**, enumerations | laundered non-requirements; changed limits or modality |
| legal | every clause, verbatim | (audit-only — flag, do not edit) |
| PRD | real constraints; unresolved decisions kept visibly unresolved | adjectives-as-requirements; simulated decisions. Do NOT police every aspiration (vision-policing) |
| marketing | the evocation is allowed | unsupported superiority / false specifics only |
| personal | **voice weighted very high** — fragments, em-dashes, pet words are the point | genuine emptiness only; almost never "style" |

## Notes
- A spec that repeats "A message MUST …" three times in parallel is not repetitive slop — the
  repetition is the guarantee. Leave it.
- A PRD that says "auth will be decided later" must stay unresolved; a rewrite that asserts a decision
  is a failure, not a repair.
- In `personal` and `marketing` regions, the bar for calling something harm is highest; prefer
  abstention.
