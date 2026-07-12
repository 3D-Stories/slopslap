from slopslap_verification import mdstructure


def test_parser_capability_ok_in_test_env():
    cap, version = mdstructure.parser_capability()
    assert cap == "ok"
    assert version == mdstructure.PINNED_VERSION


def test_parser_capability_version_mismatch(monkeypatch):
    import markdown_it

    monkeypatch.setattr(markdown_it, "__version__", "0.0.0", raising=False)
    cap, version = mdstructure.parser_capability()
    assert cap == "version_mismatch"
    assert version == "0.0.0"


def test_parser_capability_unavailable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "markdown_it":
            raise ImportError("simulated missing parser")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    cap, version = mdstructure.parser_capability()
    assert cap == "unavailable"
    assert version is None


def test_clean_prose_edit_no_violation():
    orig = "# Title\n\nHello world.\n"
    rev = "# Title\n\nHello there.\n"
    assert mdstructure.compare(orig, rev) == []


def test_unclosed_fence_detected():
    orig = "before\n\n```py\nx = 1\n```\n\nafter\n"
    rev = "before\n\n```py\nx = 1\n\nafter\n"  # closing fence deleted -> odd parity
    violations = mdstructure.compare(orig, rev)
    assert any("fence" in v for v in violations)


def test_code_block_count_change_detected():
    orig = "a\n\n```\ncode\n```\n\nb\n"
    rev = "a\n\nb\n"  # code block removed
    violations = mdstructure.compare(orig, rev)
    assert any("code-block count" in v for v in violations)


def test_broken_link_detected():
    orig = "see [docs](https://x.example) here\n"
    rev = "see [docs](https://x.example here\n"  # missing close paren
    violations = mdstructure.compare(orig, rev)
    assert any("unterminated" in v for v in violations)


def test_broken_inline_code_delimiter_detected():
    # deleting a closing backtick turns a code span into literal text (WF5-diff F2)
    orig = "use the `flag` here\n"
    rev = "use the `flag here\n"
    violations = mdstructure.compare(orig, rev)
    assert any("inline code-span" in v for v in violations)
