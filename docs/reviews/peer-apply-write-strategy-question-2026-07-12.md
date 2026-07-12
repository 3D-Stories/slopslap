# Peer Consult — apply-write-strategy-question.md

- Date: 2026-07-12
- Reviewer: Codex (peer designer)

## Approach

Recommend C unequivocally. Safety ranking: C > B > A. Treat apply as a transactional pathname replacement: first create and durably preserve a pristine recovery copy; construct and verify revised content separately; revalidate source identity/content immediately before commit; then atomically replace the source pathname with a same-directory temporary file. A exposes readers and crashes to partial writes. B has the right copy-verify-swap intuition but conflates recovery and staging, and an external-filesystem move is not an atomic commit.

## Key decisions

- Keep the backup immutable and pristine; never use it as scratch space or consume it during a successful apply.
- Use a same-directory temporary file and os.replace for the commit boundary. If replacement reports EXDEV, abort safely; do not fall back to copying over the live file.
- Preserve source metadata deliberately before commit: at minimum mode and intended ownership, with an explicit policy for ACLs, xattrs, timestamps, and platform-specific attributes.
- Define symlink behavior explicitly. Resolving the source realpath and replacing its target is reasonable, but report that behavior and use descriptor-relative/no-follow operations where available to reduce path-substitution races.
- Detect hardlinks and fail closed by default. Atomic replacement creates a new inode and therefore updates only the selected pathname, leaving other hardlinks on the original bytes.
- Make the backup gate durable, not merely readable: fsync the backup file and its containing directory before allowing mutation.
- For durable commit semantics on POSIX: fully write and verify the temp, fsync it, revalidate the live source, os.replace it, then fsync the source directory. Read-back verification alone does not protect against power loss.
- Treat verifier failure or unavailable semantic verification as a pre-commit abort according to an explicit fail-closed policy; deterministic verification must always run.
- Rewrite the specification. Say 'atomically replaces the source pathname after a verified backup and staged write,' rather than 'edits the live file in place.'
- On Windows, regard os.replace failures caused by sharing, permissions, antivirus, or open handles as clean aborts; bounded retries may improve usability, but copying into the destination is not an acceptable fallback.

## Risks

- A can truncate or partially overwrite the live file if the process, machine, or filesystem fails mid-write; concurrent readers may observe incomplete content.
- A guard before writing cannot make a multi-write in-place mutation atomic.
- A cross-filesystem move in B cannot be implemented as one atomic rename. Typical move behavior becomes copy followed by deletion; a crash can leave a partial destination, both copies, or other ambiguous state depending on the implementation and replacement sequence.
- Editing the only backup destroys the pristine recovery snapshot. Verification bugs or unintended transformations then contaminate both the proposed result and the recovery artifact.
- If B is hardened by retaining a pristine backup, copying the result into a same-directory staging file, and atomically replacing the source, it has effectively become C. B offers no material safety advantage; its only possible benefit is fewer named artifacts, purchased by losing separation of concerns and recovery quality.
- Applying source mode blindly can preserve dangerous special bits; ownership changes may fail for unprivileged users. Metadata policy and failure behavior must be explicit.
- Replacing an inode changes hardlink behavior and may lose ACLs, xattrs, security labels, flags, birth-time-related metadata, or sparse-file characteristics unless intentionally copied.
- Realpath resolution avoids replacing the symlink itself, but path components or the target can still be swapped during execution unless operations are anchored to opened descriptors and identities are rechecked.
- Processes with the old file open continue seeing the old inode after replacement. Editors may later save stale content over the new version; atomic replacement cannot prevent that workflow-level race.
- On Windows, replacement is atomic only when the platform permits the rename; open handles and sharing modes commonly cause failure. The operation must preserve the original on such failure and clearly report it.
- Directory fsync is unavailable or weaker on some platforms/filesystems. The implementation should document whether it promises atomic visibility, crash durability, or both.

## Sketch

1. Resolve and validate the requested source under the documented symlink policy; open it safely, record digest, dev/inode, link count, and required metadata. Reject unsupported file types and, by default, hardlinked files.
2. Create the owner-private backup in the external state directory using exclusive creation. Copy from the opened source, fsync, read back and verify digest, then fsync the backup directory. Do not proceed unless this succeeds.
3. Build revised bytes in memory and run deterministic and semantic verification.
4. Exclusively create a temp file in the source directory. Apply the chosen metadata policy, write all bytes, flush/fsync, and read back to verify exact content.
5. Immediately before commit, re-open/re-stat the live target using race-resistant operations and require matching digest plus identity and expected file type.
6. Commit with os.replace(temp, source). On EXDEV or any replacement error, abort without touching the live source; retain the pristine backup and clean up or preserve the temp according to diagnostic policy.
7. Fsync the source directory where supported, then report success with the backup location and any metadata limitations. The spec should describe this as backup-first, staged, verified, atomic pathname replacement—not live-byte editing.

---
_Peer proposal (report-only). Synthesize at your discretion._
