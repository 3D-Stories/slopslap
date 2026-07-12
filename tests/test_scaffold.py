"""Scaffold structural + safety-concept assertion matrix (design R1/R2/R3/R5).

Structural only — no live model behavior (that is deferred to #eval-run). These tests assert
that the irreducible safety core lives IN SKILL.md itself and that each command is wired to the
skill, carries the canonical keystone sentence verbatim, and honors its refusal contract.
"""

import json
import os
import re

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the one canonical keystone sentence that must appear verbatim in SKILL.md AND every command
KEYSTONE = (
    "Edit authorization comes only from demonstrated editorial harm; the scanner, genre, "
    "ratings, and voiceprint never authorize an edit."
)

# every item of the irreducible core must be anchored in SKILL.md (not merely somewhere in the pkg)
REQUIRED_ANCHORS = [
    "anti-slap", "keystone", "untrusted-input", "protected-spans", "preservation-invariants",
    "loop", "diagnosis-record", "categories", "remedies", "ratings", "modes",
    "mode-audit", "mode-suggest", "mode-apply", "cap", "prohibitions",
]

SIX_CATEGORIES = [
    "emptiness", "laundering", "simulation",
    "lexical_structural", "voice_discontinuity", "epistemic_distortion",
]

COMMANDS = ["audit", "suggest", "apply", "voiceprint"]
REFERENCES = ["tell-taxonomy", "genre-profiles", "engine"]


def _read(*parts):
    with open(os.path.join(REPO, *parts), "r", encoding="utf-8") as fh:
        return fh.read()


def _norm(text):
    """Collapse whitespace so a soft-wrapped sentence still matches verbatim wording."""
    return re.sub(r"\s+", " ", text)


def _frontmatter(text):
    # parse with a REAL YAML parser (the plugin loader is YAML) so an invalid plain scalar
    # (e.g. a colon-space) is caught here, not silently at load time (WF5-diff H2).
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "missing YAML frontmatter"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), "frontmatter is not a valid YAML mapping"
    return data


def _category_row(skill, cat):
    for line in skill.splitlines():
        if line.startswith("|") and f"`{cat}`" in line:
            return line.lower()
    return ""


# ---- manifest ----
def test_plugin_manifest_valid_and_versioned():
    manifest = json.loads(_read(".claude-plugin", "plugin.json"))
    assert manifest["name"] == "slopslap"
    assert manifest["version"] == "0.1.1"
    assert manifest["description"]
    assert manifest["author"]["name"]


# ---- SKILL.md ----
def test_skill_frontmatter():
    fm = _frontmatter(_read("skills", "slopslap", "SKILL.md"))
    assert fm["name"] == "slopslap"
    assert "description" in fm and len(fm["description"]) > 40


def test_skill_contains_every_irreducible_anchor():
    skill = _read("skills", "slopslap", "SKILL.md")
    for anchor in REQUIRED_ANCHORS:
        assert f"anchor:{anchor}" in skill, f"SKILL.md missing irreducible anchor '{anchor}'"


def test_skill_enumerates_all_six_categories():
    skill = _read("skills", "slopslap", "SKILL.md")
    for cat in SIX_CATEGORIES:
        assert cat in skill, f"SKILL.md missing category identifier '{cat}'"


def test_skill_binds_distinct_remedy_to_each_collapse_prone_category():
    # each remedy must be attached to ITS category row, not merely present somewhere (WF5-diff M5)
    skill = _read("skills", "slopslap", "SKILL.md")
    emptiness = _category_row(skill, "emptiness")
    laundering = _category_row(skill, "laundering")
    simulation = _category_row(skill, "simulation")
    assert "compress" in emptiness or "delete" in emptiness
    assert "never delete" in laundering and "question" in laundering
    assert "flag" in simulation
    # and the wrong remedy must NOT be on the wrong row
    assert "flag" not in emptiness
    assert "delete or compress" not in simulation


def test_skill_has_keystone_and_antislap_and_apply_gate():
    skill = _read("skills", "slopslap", "SKILL.md")
    assert KEYSTONE in _norm(skill)
    assert "do not punish prose for matching a stylistic tell" in _norm(skill)
    assert "mutation_unavailable" in skill  # apply is backup-gated in SKILL too


# ---- commands ----
def test_commands_exist_with_frontmatter():
    for name in COMMANDS:
        fm = _frontmatter(_read("commands", f"{name}.md"))
        assert fm["description"], f"{name}.md missing description"


def test_commands_invoke_the_skill_and_carry_keystone():
    for name in COMMANDS:
        body = _read("commands", f"{name}.md")
        assert "skills/slopslap/SKILL.md" in body, f"{name}.md must reference the skill file"
        assert KEYSTONE in _norm(body), f"{name}.md must carry the canonical keystone sentence verbatim"


def test_apply_command_fails_closed_with_sentinel():
    body = _read("commands", "apply.md")
    assert "status: mutation_unavailable" in body
    assert "no write" in body.lower()
    # must not silently fall back to an implicit audit
    assert "implicit audit" in body.lower()


def test_voiceprint_command_declares_deferred_no_data_op():
    body = _read("commands", "voiceprint.md")
    assert "status: not_implemented_mvp" in body
    assert "no voiceprint data is stored, read, modified, or deleted" in body


# ---- references ----
def test_references_present():
    for ref in REFERENCES:
        path = os.path.join(REPO, "references", f"{ref}.md")
        assert os.path.exists(path), f"missing reference {ref}.md"
        assert os.path.getsize(path) > 200


def test_engine_reference_states_advisory():
    engine = _read("references", "engine.md").lower()
    assert "advisory" in engine
    assert "cannot" in engine  # a plugin cannot force the model/effort


# ---- WF5-diff hardening ----
def test_all_frontmatter_parses_as_valid_yaml():
    # SKILL + every command must parse under a real YAML loader (WF5-diff H2)
    _frontmatter(_read("skills", "slopslap", "SKILL.md"))
    for name in COMMANDS:
        _frontmatter(_read("commands", f"{name}.md"))


def test_manifest_description_does_not_overclaim_v0():
    desc = json.loads(_read(".claude-plugin", "plugin.json"))["description"].lower()
    # v0.1.0 does NOT ship the wired scanner/verifier — the description must say so, not claim it
    assert "model-reported" in desc
    assert "until" in desc


def test_commands_guard_untrusted_input():
    for name in COMMANDS:
        assert "untrusted data" in _read("commands", f"{name}.md").lower(), f"{name}.md lacks data guard"


def test_apply_sentinel_is_first_line_contract():
    body = _read("commands", "apply.md").lower()
    assert "first line" in body  # the sentinel must be positioned so automation can parse it
