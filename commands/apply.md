---
description: Apply editorial repairs in place (backup-gated, explicit request only). UNAVAILABLE in the MVP until the mandatory pre-mutation backup gate ships — refuses cleanly and points you to /slopslap:suggest.
argument-hint: "<writable file to repair in place>"
---

Invoke the `slopslap` skill (`skills/slopslap/SKILL.md`) with intent **apply** mode for: $ARGUMENTS

Keystone (do not deviate): **Edit authorization comes only from demonstrated editorial harm; the
scanner, genre, ratings, and voiceprint never authorize an edit.**

apply is **backup-gated**: it may mutate a file ONLY after writing and verifying a mandatory
pre-mutation backup. That backup machinery is not built yet in this MVP. Therefore, in this version,
apply MUST fail closed:

1. Emit the machine-observable sentinel line exactly: `status: mutation_unavailable`
2. State plainly that **no write was performed** and no backup exists yet.
3. Do **not** perform an implicit audit or a silent `suggest` — that would misrepresent whether a
   mutation occurred.
4. Point the user to: `/slopslap:suggest $ARGUMENTS` for a non-mutating preview of the same repairs.

Never edit the file in apply mode until the backup gate exists.
