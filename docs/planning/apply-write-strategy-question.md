# Design question — slopslap `apply` mode: how to write the mutation safely

slopslap repairs prose in files. `apply` mode mutates a source file in place, on explicit request,
**gated by a mandatory pre-mutation backup**. We're deciding the safest write strategy. Give an
independent recommendation — do not just ratify; if the framing is wrong, say so.

## The three candidate models

**(A) backup → edit the LIVE file in place.** Take a backup, then write the edits directly into the
source file's bytes. (This is what the spec PROSE currently reads like: "in-place, backup-first.")

**(B) backup → edit the BACKUP → verify → move the backup into the live path.** The backup copy is the
working copy; once verified, it replaces the live file.

**(C) backup (pristine original) → build + verify the revised bytes on a SAME-DIRECTORY temp file →
atomic `os.replace(temp, source)`.** The backup stays a pristine untouched snapshot; the live file is
never in a half-written state.

## What's actually built today (`scripts/slopslap_apply/`)

The implementation is **(C)**, with these properties:
- The **backup** is a timestamped copy written to a user-local state dir **OUTSIDE the repo** by default
  (so original prose can't be swept into a commit); read-back-verified; owner-private; the pristine
  recovery net, **never consumed**.
- The revised bytes are built **in memory** from the original, run through a deterministic + (intended)
  semantic verifier, written to a **same-directory temp file** (`source + ".slopslap.tmp.<pid>"`),
  read back, then committed with **`os.replace(temp, source)`** (atomic rename within one filesystem).
- Before the replace: a guard re-reads the live source and aborts if its digest OR dev/inode changed
  since we read it (concurrent-edit protection); the source path is `realpath`-resolved.

## The owner's proposal + the tension
The owner initially proposed **(B)** ("make the edits on the backup, verify, then switch the backup for
the live"), then wavered toward **(A)** ("edit on live"). We think the owner's *instinct* — edit a copy,
verify, then swap — is right, and is exactly **(C)** — but the copy should be a same-dir temp, not the
external backup, and the backup should stay pristine.

## Questions for you (GPT Soul)
1. Rank A / B / C for safety and correctness. Which do you recommend, and why?
2. Specifically critique **(B)**: if the backup lives on a *different* filesystem (the external state
   dir), is "move the backup into the live path" atomic? What breaks on a crash mid-move? Does making
   the backup the work-copy lose anything (e.g., the pristine snapshot)?
3. Is there ANY real advantage (B) has over (C) that we're missing?
4. Any hardening (C) still lacks — permissions/ownership carry-over, symlinked source, hardlinks, EXDEV
   fallback when temp and source somehow aren't co-located, fsync/durability ordering, editors holding
   the file open, Windows `os.replace` semantics?
5. Is the current spec PROSE ("in-place, backup-first") actively misleading vs the (C) implementation —
   should it be rewritten to describe (C) precisely?
