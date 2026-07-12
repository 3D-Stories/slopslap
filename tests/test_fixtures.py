"""The 5 canonical/control fixtures + kukakuka PRD load, validate, and are well-formed."""

import os
import subprocess
import sys

import pytest

from helpers import fixture_dir
from eval.loader import load_fixture, validate_manifest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL = ["distinctive-essay", "normative-spec", "underspecified-prd"]
CONTROLS = ["clean-personal", "clean-spec"]
ALL = CANONICAL + CONTROLS


@pytest.mark.parametrize("name", ALL)
def test_fixture_validates(name):
    orig, man = load_fixture(fixture_dir(name))
    assert validate_manifest(orig, man) == []


@pytest.mark.parametrize("name", CANONICAL)
def test_canonical_has_editable_ranges_and_defects(name):
    _, man = load_fixture(fixture_dir(name))
    assert man["editable_ranges"], f"{name} needs at least one editable range"
    assert man["seeded_defects"], f"{name} needs seeded defects"
    assert man["control"] is False


@pytest.mark.parametrize("name", CONTROLS)
def test_control_is_marked_and_empty_editable(name):
    _, man = load_fixture(fixture_dir(name))
    assert man["control"] is True
    assert man["editable_ranges"] == []
    assert man["seeded_defects"] == []
    assert man["control_reason"]


def test_kukakuka_prd_fixture_present_and_nonempty():
    path = os.path.join(REPO, "tests", "fixtures", "kukakuka-prd.md")
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1000


def test_build_fixture_validate_cli():
    # the authoring utility's validate subcommand agrees with the loader
    for name in ALL:
        out = subprocess.run(
            [sys.executable, os.path.join(REPO, "scripts", "eval", "build_fixture.py"),
             "validate", "--dir", fixture_dir(name)],
            capture_output=True, text=True,
        )
        assert out.returncode == 0, f"{name}: {out.stdout}{out.stderr}"
        assert "OK" in out.stdout
