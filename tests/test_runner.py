"""Two-stage runner: deterministic_state -> acceptance_state across the fixture contract."""

from helpers import fixture_dir, make_envelope, make_second_pass

from eval.loader import load_fixture
from eval.runner import JudgeOutcome, State, run


def _editable(name):
    orig, man = load_fixture(fixture_dir(name))
    return orig, man, man["editable_ranges"][0]


def test_original_unchanged_incomplete_without_second_pass():
    orig, _ = load_fixture(fixture_dir("distinctive-essay"))
    env, _ = make_envelope(orig, [], baseline="original-unchanged")
    r = run(fixture_dir("distinctive-essay"), env)
    # canonical fixture: no 2nd pass -> idempotence NOT_EVALUATED -> INCOMPLETE
    assert r.deterministic_state == State.INCOMPLETE


def test_good_edit_with_second_pass_deterministic_pass_acceptance_needs_judge():
    orig, man, er = _editable("distinctive-essay")
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Solder carefully.")])
    r = run(fixture_dir("distinctive-essay"), env, second_pass=make_second_pass(rev, []))
    assert r.deterministic_state == State.PASS
    assert r.acceptance_state == State.INCOMPLETE  # no judge yet


def test_good_edit_judge_beat_acceptance_pass():
    orig, man, er = _editable("distinctive-essay")
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Solder carefully.")])
    r = run(
        fixture_dir("distinctive-essay"),
        env,
        second_pass=make_second_pass(rev, []),
        judge=JudgeOutcome(present=True, errored=False, beat=True),
    )
    assert r.acceptance_state == State.PASS


def test_judge_loss_demotes_to_fail():
    orig, man, er = _editable("distinctive-essay")
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Solder carefully.")])
    r = run(
        fixture_dir("distinctive-essay"),
        env,
        second_pass=make_second_pass(rev, []),
        judge=JudgeOutcome(present=True, errored=False, beat=False),
    )
    assert r.deterministic_state == State.PASS
    assert r.acceptance_state == State.FAIL


def test_control_abstain_passes_without_judge():
    orig, _ = load_fixture(fixture_dir("clean-personal"))
    env, _ = make_envelope(orig, [], baseline="original-unchanged")
    r = run(fixture_dir("clean-personal"), env)
    assert r.deterministic_state == State.PASS
    assert r.acceptance_state == State.PASS


def test_control_material_edit_fails():
    orig, _ = load_fixture(fixture_dir("clean-spec"))
    # edit somewhere (there are no editable ranges) -> control_abstention FAIL
    env, _ = make_envelope(orig, [(0, 2, b"# ")])
    r = run(fixture_dir("clean-spec"), env)
    assert r.deterministic_state == State.FAIL


def test_envelope_hash_mismatch_is_fixture_error():
    orig, _ = load_fixture(fixture_dir("distinctive-essay"))
    env, _ = make_envelope(orig, [])
    env["revision_sha256"] = "deadbeef" * 8  # wrong
    r = run(fixture_dir("distinctive-essay"), env)
    assert r.deterministic_state == State.FIXTURE_ERROR


def test_second_pass_base_hash_mismatch_is_fixture_error():
    orig, man, er = _editable("distinctive-essay")
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Solder.")])
    bad_second = make_second_pass(orig, [])  # base_hash of ORIGINAL, not the revision
    r = run(fixture_dir("distinctive-essay"), env, second_pass=bad_second)
    assert r.deterministic_state == State.FIXTURE_ERROR


def test_idempotence_unstable_second_pass_fails():
    orig, man, er = _editable("distinctive-essay")
    env, rev = make_envelope(orig, [(er["start_byte"], er["end_byte"], b"Solder.")])
    # 2nd pass edits the revision again -> not idempotent
    second = make_second_pass(rev, [(0, 1, b"x")])
    r = run(fixture_dir("distinctive-essay"), env, second_pass=second)
    assert r.deterministic_state == State.FAIL


def test_invalid_manifest_is_fixture_error(tmp_path):
    (tmp_path / "original.md").write_bytes(b"hello\n")
    (tmp_path / "fixture.json").write_text(
        '{"schema_version": 1, "genre": "spec", "editable_ranges": '
        '[{"start_byte": 0, "end_byte": 999}]}'
    )
    env, _ = make_envelope(b"hello\n", [])
    r = run(str(tmp_path), env)
    assert r.deterministic_state == State.FIXTURE_ERROR
