"""#102 — the committed `pair-102-*` eval fixtures are REPRODUCIBLE slopslap output, not hand-written.

For every pair: replaying the committed edit-script over original.md with the production
`apply_edits` yields applied.md byte-for-byte; the manifest's shas match the files; the recorded
apply exited 0; a fresh offline dry-run through the real seam still reaches ACCEPT; the sides
differ; and the provenance names the public source (repo, path, lines, commit, license).

Count pin: the issue's AC4 asked for 5 to 10 pairs. The shipped set is SMALLER — slopslap's default
autonomous path (auto-classified genre, byte-exact verifier) produced 3 verifier-clean pairs out of
31 sampled public design-doc paragraphs; the results document states the shortfall and the owner
decides how to widen it. This guard pins the shipped floor so a fixture cannot silently vanish.
"""
import base64
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from eval.loader import load_fixture, validate_manifest
from slopslap_verification.editscript import apply_edits, parse_edits

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(REPO, "tests", "fixtures", "eval")
SEAM = os.path.join(REPO, "scripts", "slopslap_assemble", "assemble.py")
PAIRS = sorted(d for d in glob.glob(os.path.join(FX, "pair-102-*")) if os.path.isdir(d))
SHIPPED_FLOOR = 3  # see the module docstring; the AC4 floor of 5 was NOT met on the default path


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_shipped_pair_count_holds():
    assert len(PAIRS) >= SHIPPED_FLOOR, [os.path.basename(p) for p in PAIRS]


@pytest.mark.parametrize("d", PAIRS, ids=[os.path.basename(p) for p in PAIRS])
def test_pair_is_loader_valid_with_an_eval_pair_block(d):
    original, manifest = load_fixture(d)
    assert validate_manifest(original, manifest) == []
    ep = manifest["eval_pair"]
    assert ep["schema_version"] == 1 and ep["engine_model"]
    assert manifest["pair"] is True and manifest["control"] is False
    assert manifest["clean_file"] == "applied.md"
    assert manifest["seeded_defects"], "a pair must name the harm it repaired"


@pytest.mark.parametrize("d", PAIRS, ids=[os.path.basename(p) for p in PAIRS])
def test_applied_side_reproduces_from_the_committed_edit_script(d):
    original, manifest = load_fixture(d)
    ep = manifest["eval_pair"]
    with open(os.path.join(d, "applied.md"), "rb") as fh:
        applied = fh.read()
    with open(os.path.join(d, ep["edits_file"]), "r", encoding="utf-8") as fh:
        edits = json.load(fh)
    assert edits, "an eval pair carries at least one edit"
    assert apply_edits(original, parse_edits(edits)) == applied, "applied.md is not the edit-script's output"
    assert applied != original
    assert ep["source_sha256"] == _sha(original) and ep["applied_sha256"] == _sha(applied)
    assert ep["source_sha256"] != ep["applied_sha256"]
    assert ep["apply_exit"] == 0
    assert ep["semantic_mode"] in ("live", "offline_stub")


@pytest.mark.parametrize("d", PAIRS, ids=[os.path.basename(p) for p in PAIRS])
def test_apply_result_is_a_run_result_without_source_bytes(d):
    original, manifest = load_fixture(d)
    with open(os.path.join(d, manifest["eval_pair"]["apply_result_file"]), "r", encoding="utf-8") as fh:
        res = json.load(fh)
    assert res["status"] == "ok" and {s["stage"] for s in res["stages"]} == {"audit", "candidate", "verify", "apply"}
    audit = [s for s in res["stages"] if s["stage"] == "audit"][0]["data"]
    assert audit["source_sha256"] == manifest["eval_pair"]["source_sha256"]
    assert original.decode("utf-8")[:40] not in json.dumps(res)  # no source bytes leak into the record


@pytest.mark.parametrize("d", PAIRS, ids=[os.path.basename(p) for p in PAIRS])
def test_offline_dry_run_through_the_real_seam_still_accepts(d, tmp_path):
    original, manifest = load_fixture(d)
    src = tmp_path / "doc.md"
    src.write_bytes(original)
    proc = subprocess.run([sys.executable, SEAM, "run", "--path", str(src), "--edits",
                           os.path.join(d, manifest["eval_pair"]["edits_file"])],
                          capture_output=True, text=True, cwd=REPO, env={**os.environ, "SLOPSLAP_LIVE": ""})
    assert proc.returncode == 0, proc.stdout[-400:] + proc.stderr[-400:]
    out = json.loads(proc.stdout)
    verify = [s for s in out["stages"] if s["stage"] == "verify"][0]["data"]
    assert verify["decision"] == "ACCEPT"
    assert src.read_bytes() == original  # dry-run never mutates


@pytest.mark.parametrize("d", PAIRS, ids=[os.path.basename(p) for p in PAIRS])
def test_provenance_names_a_public_source(d):
    _, manifest = load_fixture(d)
    src = manifest["eval_pair"]["source"]
    for k in ("repo", "path", "lines", "commit", "license"):
        assert src.get(k), k
    assert src["repo"] in ("3D-Stories/slopslap", "3D-Stories/design-doc-publish")  # the two PUBLIC repos
    assert len(src["commit"]) == 40 and src["license"] == "MIT"
    assert "verbatim" in manifest["provenance"] and "never hand-written" in manifest["provenance"]
