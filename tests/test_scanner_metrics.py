"""Metric behavior on crafted inputs. Text path (stdlib) so no parser needed."""

from slopslap_scan import TEXT_PROFILE
from slopslap_scan.extract import extract_text
from slopslap_scan.metrics import compute_all


def _metrics(text):
    return compute_all(extract_text(text), TEXT_PROFILE, source=text)


def test_flat_schema_fields_present_on_every_metric():
    m = _metrics("Hello world here. It runs fine.")
    for name, res in m.items():
        for k in ("eligible_units", "count", "locations", "soft_flag",
                  "metric_version", "extraction_profile", "confidence", "purpose"):
            assert k in res, (name, k)
        assert res["extraction_profile"] == TEXT_PROFILE


def test_stock_cluster_detected():
    m = _metrics("In conclusion, we should delve into the topic.")
    assert m["stock_lexical_clusters"]["count"] >= 1
    assert m["stock_lexical_clusters"]["confidence"] == "low"
    assert m["stock_lexical_clusters"]["soft_flag"] is None


def test_duality_template_detected():
    m = _metrics("This is not only fast but also cheap to run.")
    clusters = [h["cluster"] for h in m["stock_lexical_clusters"]["locations"]]
    assert "duality_framing" in clusters


def test_repeated_openers_cluster_event():
    text = "\n\n".join(["The cat sat down.", "The cat ran off.", "The cat ate lunch."])
    m = _metrics(text)
    assert m["repeated_openers"]["count"] >= 1
    assert m["repeated_openers"]["confidence"] == "medium"


def test_transition_clusters_sentence_initial():
    m = _metrics("However, this works. Furthermore, it scales well.")
    assert m["transition_clusters"]["count"] >= 1


def test_punctuation_rates():
    r = _metrics("This thing — that thing; and more here.")["punctuation_rates"]["rates"]
    assert r["em_dash"] == 1 and r["semicolon"] == 1


def test_negative_parallelism_detected():
    # "X, not Y" cadence tic (issue #14)
    m = _metrics("Built for quality, not expediency. The wedge is the room, not the panes.")
    np = m["negative_parallelism"]
    assert np["count"] >= 2 and np["confidence"] == "medium"


def test_negative_parallelism_soft_flag_on_density():
    text = ". ".join(f"choose {w} thing, not other thing" for w in
                     ["a", "b", "c", "d", "e", "f"]) + "."
    assert _metrics(text)["negative_parallelism"]["soft_flag"] is True


def test_negative_parallelism_absent_on_plain_prose():
    m = _metrics("The server accepts a request and returns a response within the budget.")
    assert m["negative_parallelism"]["count"] == 0


def test_rule_of_three_tricolon():
    m = _metrics("It is fast, cheap, and reliable under load.")
    assert m["rule_of_three"]["count"] >= 1
    assert m["rule_of_three"]["confidence"] == "low"


def test_punctuation_soft_flag_on_high_density():
    # a paragraph dense with em-dashes/semicolons flags (candidate_selection_only)
    text = "one — two; three — four; five — six; seven — eight; nine — ten."
    assert _metrics(text)["punctuation_rates"]["soft_flag"] is True


def test_sentence_length_distribution():
    d = _metrics("One two three. Four five.")["sentence_length_distribution"]["distribution"]
    assert d["max"] == 3 and d["min"] == 2


def test_vague_attribution_low_null_flag():
    m = _metrics("Studies show it is true. Experts say so.")["vague_attribution"]
    assert m["count"] >= 2 and m["confidence"] == "low" and m["soft_flag"] is None


def test_paragraph_sentence_count_runs():
    p = "A one thing. A two thing."
    m = _metrics("\n\n".join([p, p, p]))
    assert m["paragraph_sentence_count_runs"]["count"] >= 1


def test_bold_label_density_markdown():
    from markdown_it import MarkdownIt

    from slopslap_scan import EXTRACTION_PROFILE
    from slopslap_scan.extract import extract_markdown

    units = extract_markdown("**Note**: something here.\n\n**Warning**: else here.\n", MarkdownIt)
    m = compute_all(units, EXTRACTION_PROFILE)
    assert m["bold_label_density"]["count"] == 2


def test_bold_label_in_code_fence_not_counted():
    from markdown_it import MarkdownIt

    from slopslap_scan import EXTRACTION_PROFILE
    from slopslap_scan.extract import extract_markdown

    src = "Prose here.\n\n```\n**NotALabel**: in code\n```\n"
    units = extract_markdown(src, MarkdownIt)
    assert compute_all(units, EXTRACTION_PROFILE)["bold_label_density"]["count"] == 0


def test_unicode_words_counted():
    # accented + non-Latin letters must count as words (WF5-diff H2)
    d = _metrics("Café niño déjà vu élan.")["sentence_length_distribution"]["distribution"]
    assert d["max"] == 5  # five accented words, one sentence


def test_abbreviation_not_a_sentence_boundary():
    # "e.g." must not split the sentence
    d = _metrics("We support many formats e.g. json and yaml here.")["sentence_length_distribution"]
    assert d["count"] == 1  # one sentence, not split at 'e.g.'
