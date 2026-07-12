from slopslap_verification import atoms


def test_numbers_normalize_thousands_and_percent():
    c = atoms.numbers("we support 10,000 users at 99.9% over 300 ms")
    assert c["10000"] == 1
    assert c["99.9%"] == 1
    assert c["300"] == 1


def test_numbers_comparator_captured():
    c = atoms.numbers("latency < 300 and count >= 5")
    assert c["<300"] == 1
    assert c[">=5"] == 1


def test_reordered_duplicate_numbers_are_a_multiset():
    # same multiset regardless of order; a deleted value changes the multiset
    a = atoms.numbers("5 then 200 then 2000")
    b = atoms.numbers("2000 then 5 then 200")
    assert a == b
    c = atoms.numbers("5 then 200")  # 2000 dropped
    assert a != c


def test_dates():
    c = atoms.dates("on 2026-07-12 and 7/4/2026 and Jul 4, 2026")
    assert c["2026-07-12"] == 1
    assert c["7/4/2026"] == 1
    assert any("Jul 4" in k for k in c)


def test_urls():
    c = atoms.urls("see https://api.example.com/v1/ping, and www.example.org.")
    assert "https://api.example.com/v1/ping" in c
    assert "www.example.org" in c


def test_modality_phrase_aware_and_negation():
    c = atoms.modality("The client MUST retry but MUST NOT loop; it should stop")
    assert c["must"] == 1
    assert c["must not"] == 1
    assert c["should"] == 1


def test_negation_and_conditions():
    assert atoms.negation("this is not allowed and cannot happen")["not"] == 1
    assert atoms.conditions("if the server returns 429 unless told otherwise")["if"] == 1


def test_new_claim_atoms_detects_invented_number():
    intro = atoms.new_claim_atoms("supports 10,000 users", "supports 10,000 users within 50 ms")
    assert "number" in intro and "50" in intro["number"]


def test_new_claim_atoms_allows_declared():
    intro = atoms.new_claim_atoms(
        "supports users", "supports 10,000 users", allowed=["10000"]
    )
    assert intro == {}


def test_new_claim_atoms_reuse_is_fine():
    # re-using an existing atom is not "new"
    assert atoms.new_claim_atoms("5 apples", "5 apples and 5 pears") == {}
