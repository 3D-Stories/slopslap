---
description: Manage your voiceprint (show / reset / export / delete) — the per-author whitelist of genuine habits that keeps slopslap from stripping real voice. RESERVED for v2; not implemented in the MVP, which stores and reads nothing.
argument-hint: "show | reset | export | delete"
---

Invoke the `slopslap` skill (`skills/slopslap/SKILL.md`) for a **voiceprint** operation: $ARGUMENTS

Keystone (do not deviate): **Edit authorization comes only from demonstrated editorial harm; the
scanner, genre, ratings, and voiceprint never authorize an edit.** (Even in v2, the voiceprint only
picks among already-safe phrasings and defends real voice; it never authorizes an edit.)

The voiceprint is the reason slopslap is a plugin (its future capture needs a UserPromptSubmit hook),
but the persistent-learning feature is **v2, deferred**. In this MVP the reserved operations
`show | reset | export | delete` are **not implemented**:

1. Emit the sentinel line exactly: `status: not_implemented_mvp`
2. Guarantee and state that **no voiceprint data is stored, read, modified, or deleted** — no profile
   exists yet.
3. If the user wants voice preserved now, tell them: paste a short voice sample inline with a
   `/slopslap:suggest` request and slopslap will treat it as a one-shot manual voice sample (no
   persistence).
