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
    "Every tell is detected and prepared for removal; genre and learned feedback set each "
    "finding's recommendation; the user's review decision — not the scanner, not the genre, "
    "not the learning — authorizes the edit; and the byte-exact verifier guarantees no applied "
    "edit changes a number, requirement, negation, condition, defined term, or protected span. "
    "Recommendations may learn; authorization never does."
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

COMMANDS = ["audit", "suggest", "apply", "voiceprint", "review", "feedback"]
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
    assert manifest["version"] == "0.12.0"
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
    # apply is now ENABLED (#29) but still backup-gated: SKILL must describe the mandatory
    # pre-mutation backup, not the old disabled sentinel.
    assert "backup" in skill.lower() and "atomic" in skill.lower()


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


def test_apply_command_enabled_and_backup_gated():
    """#29: apply is wired to the engine (the mutating `apply` subcommand), but stays backup-gated
    and fail-closed — it never mutates without a verified backup + a passing verifier."""
    body = _read("commands", "apply.md")
    assert "assemble.py apply" in body                      # wired to the mutating engine path
    assert "backup" in body.lower() and "atomic" in body.lower()
    assert "fails closed" in body.lower() or "fail closed" in body.lower()
    # must not claim an unconfirmed mutation or silently fall back
    assert "never claim a mutation" in body.lower() or "exit code" in body.lower()


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


def test_manifest_description_matches_v0_2_reality():
    """v0.2.0 WIRED the scanner + verifier + apply, so the old 'model-reported ... until' hedge is
    RETIRED (it would now be false). The description must reflect the shipped reality without the
    stale not-yet-wired clause."""
    desc = json.loads(_read(".claude-plugin", "plugin.json"))["description"].lower()
    assert "model-reported" not in desc          # retired at 0.2.0 (#25) — the verifier is wired
    assert "verifier" in desc and "0.2.0" in desc


def test_commands_guard_untrusted_input():
    for name in COMMANDS:
        assert "untrusted data" in _read("commands", f"{name}.md").lower(), f"{name}.md lacks data guard"


def test_target_wrapping_commands_treat_an_inner_fence_line_as_data():
    # #46: audit/suggest/apply wrap an UNTRUSTED target. A static command prompt cannot carry an
    # unforgeable per-run delimiter, so the defense is RULE-based: the framing must declare that a line
    # inside the block is DATA *even if it reproduces the fence marker verbatim* (that is what stops a
    # target line closing the wrapper and injecting the diagnosis step).
    for name in ("audit", "suggest", "apply"):
        body = _read("commands", f"{name}.md")
        low = body.lower()
        assert "data even if it reproduces the fence marker verbatim" in low, \
            f"{name}.md missing the content-is-always-data (inner-fence-is-data) rule"
        assert "never ends the block" in low, f"{name}.md missing the block-boundary rule"
        assert "SLOPSLAP_UNTRUSTED_TARGET" in body, f"{name}.md missing the distinctive fence token"
        # the old bare-sentinel fence must be gone
        assert "<<<SLOPSLAP_TARGET\n" not in body, f"{name}.md still uses the old bare fence"


def test_apply_completion_signal_contract():
    """#29: the disabled first-line sentinel is retired — apply now emits a machine-observable JSON
    RunResult + exit code (0 applied / 2 blocked / 3-4 failure) as the completion signal."""
    body = _read("commands", "apply.md").lower()
    assert "runresult" in body and "exit code" in body
