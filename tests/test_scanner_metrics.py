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


def test_bold_label_density():
    m = _metrics("**Note**: something here.\n\n**Warning**: else here.")
    assert m["bold_label_density"]["count"] == 2


def test_abbreviation_not_a_sentence_boundary():
    # "e.g." must not split the sentence
    d = _metrics("We support many formats e.g. json and yaml here.")["sentence_length_distribution"]
    assert d["count"] == 1  # one sentence, not split at 'e.g.'
