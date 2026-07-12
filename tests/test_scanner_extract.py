"""Markdown extraction fixtures — exclusions, bare-URL removal, retained structure.

Uses an importable markdown-it-py 3.0.0 (env copy); the extraction LOGIC is under test.
Vendoring isolation is proven separately in test_scanner_capability.py.
"""

from markdown_it import MarkdownIt

from slopslap_scan.extract import extract_markdown


def _units(src):
    return extract_markdown(src, MarkdownIt)


def _alltext(units):
    return " ".join(u.text for u in units)


def test_fenced_code_excluded():
    u = _units("Prose here works.\n\n```\nsecret_token = 1\n```\n")
    assert "secret_token" not in _alltext(u)
    assert "Prose here" in _alltext(u)


def test_indented_code_excluded():
    u = _units("Prose paragraph.\n\n    indented_secret = 2\n")
    assert "indented_secret" not in _alltext(u)


def test_inline_code_excluded():
    u = _units("Use the `flag_name` option please.\n")
    t = _alltext(u)
    assert "flag_name" not in t and "option please" in t


def test_blockquote_excluded():
    u = _units("Body paragraph.\n\n> quoted secret words\n")
    assert "quoted secret" not in _alltext(u)


def test_link_label_kept_destination_dropped():
    u = _units("See [the label](https://x.example/secretpath) now.\n")
    t = _alltext(u)
    assert "the label" in t
    assert "secretpath" not in t and "x.example" not in t


def test_bare_urls_removed_email_kept():
    u = _units("Visit https://y.example/z and www.foo.example but mail a@b.example please.\n")
    t = _alltext(u)
    assert "y.example" not in t
    assert "foo.example" not in t
    assert "a@b.example" in t  # email preserved as prose (left boundary '@')


def test_bare_domain_removed_but_version_string_kept():
    u = _units("Ship v3.0.0 today and see docs.example for more.\n")
    t = _alltext(u)
    assert "docs.example" not in t
    assert "v3.0.0" in t  # not a URL


def test_heading_and_list_structural_types():
    u = _units("# Title Heading\n\n- item one\n- item two\n")
    types = {x.structural_type for x in u}
    assert "heading" in types and "list_item" in types


def test_line_locations_are_one_indexed():
    u = _units("# H\n\nParagraph on line three.\n")
    para = [x for x in u if x.structural_type == "paragraph"][0]
    assert para.line_start == 3


def test_no_fusion_across_inline_code():
    # "foo." + `sep` + "com" must NOT fuse into the synthetic domain foo.com and be removed
    # (WF5-diff M4). If fusion happened, strip_urls would delete both halves.
    u = _units("The value foo.`sep`com stays as words.\n")
    t = _alltext(u)
    assert "foo" in t and "com" in t  # both survive => no synthetic-domain removal
    assert "sep" not in t  # the inline code content itself is excluded


def test_nested_list_item_keeps_outer_classification():
    # after a nested list closes, the outer item's continuation stays list_item (WF5-diff M6)
    src = "- outer start\n    - inner one\n\n  outer continuation prose here\n"
    u = _units(src)
    conts = [x for x in u if "outer continuation" in x.text]
    assert conts and conts[0].structural_type == "list_item"


def test_bare_domain_query_suffix_removed():
    # example.com?q=1 — the whole URL incl. the ?query goes (WF5-diff M5)
    u = _units("See example.com?q=1 for details.\n")
    t = _alltext(u)
    assert "example.com" not in t and "q=1" not in t
