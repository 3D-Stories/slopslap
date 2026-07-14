"""#43 (Epic #67 Wave 3): self-checking edit-script — an optional per-range expected preimage.

The wire shape {start_byte,end_byte,replacement_b64} has no preimage, so an in-bounds offset at the
WRONG bytes (a drifted doc, a stale script) that still preserves every invariant is not caught
structurally. An optional `preimage_b64` / `preimage_sha256` per range lets `apply_edits` reject a
mismatch. Backward-compatible: absent → no check, exactly as before.
"""

import base64

import pytest

from slopslap_apply.backup import BackupConfig
from slopslap_assemble.assemble import apply_from_decisions, audit_document, exit_code, main  # noqa: F401
from slopslap_verification.editscript import Edit, EditError, apply_edits, parse_edits, sha256_hex

_DOC = b"the client MUST wait 200 ms.\n"


def _raw(s, e, repl, **extra):
    d = {"start_byte": s, "end_byte": e, "replacement_b64": base64.b64encode(repl).decode()}
    d.update(extra)
    return d


def test_correct_preimage_b64_applies():
    pre = base64.b64encode(_DOC[4:10]).decode()   # "client"
    edits = parse_edits([_raw(4, 10, b"user", preimage_b64=pre)])
    assert apply_edits(_DOC, edits) == b"the user MUST wait 200 ms.\n"


def test_wrong_preimage_b64_rejected():
    pre = base64.b64encode(b"SERVER").decode()     # NOT the bytes at [4,10)
    edits = parse_edits([_raw(4, 10, b"user", preimage_b64=pre)])
    with pytest.raises(EditError, match="preimage"):
        apply_edits(_DOC, edits)


def test_correct_preimage_sha256_applies():
    sha = sha256_hex(_DOC[4:10])
    edits = parse_edits([_raw(4, 10, b"user", preimage_sha256=sha)])
    assert apply_edits(_DOC, edits) == b"the user MUST wait 200 ms.\n"


def test_wrong_preimage_sha256_rejected():
    edits = parse_edits([_raw(4, 10, b"user", preimage_sha256="0" * 64)])
    with pytest.raises(EditError, match="preimage"):
        apply_edits(_DOC, edits)


def test_no_preimage_is_backward_compatible():
    # absent preimage → no check, exactly the pre-#43 behavior
    edits = parse_edits([_raw(4, 10, b"user")])
    assert apply_edits(_DOC, edits) == b"the user MUST wait 200 ms.\n"
    assert edits[0].preimage_sha256 is None


def test_right_offset_wrong_bytes_caught_even_when_in_bounds():
    # the issue's scenario: a stale/drifted doc — the SAME offsets, but the bytes there changed. Bounds
    # + overlap pass; only the preimage catches it.
    drifted = b"the SERVER MUST wait 200 ms.\n"          # "client" -> "SERVER" at [4,10)
    pre = base64.b64encode(b"client").decode()
    edits = parse_edits([_raw(4, 10, b"user", preimage_b64=pre)])
    with pytest.raises(EditError, match="preimage"):
        apply_edits(drifted, edits)


def test_apply_from_decisions_rejects_a_preimage_mismatch_cleanly(tmp_path):
    # integration: a mismatching preimage surfaces as a clean invalid-input failure (exit-classable),
    # never an uncaught traceback — run_candidate's public validator catches the EditError.
    from slopslap_assemble.assemble import run_candidate
    p = tmp_path / "d.md"
    p.write_text(_DOC.decode(), encoding="utf-8")
    audit = audit_document(str(p), declared_genre="general").data
    bad = [_raw(4, 10, b"user", preimage_b64=base64.b64encode(b"WRONG!").decode())]
    run = run_candidate(audit, bad, semantic_fn=lambda o, r, l: {"verdict": "clean", "concerns": []},
                        write=False, apply_config=BackupConfig(root=str(tmp_path / "b")))
    cand = next(s for s in run.stages if s.stage == "candidate")
    assert cand.status == "failed"                       # clean rejection, not a crash
    assert p.read_bytes() == _DOC                         # untouched
