import unicodedata

from pipeline.text import MIN_QUOTE_CHARS, copied_span, find_quote


def span_text(text, quote):
    s = find_quote(text, quote)
    return None if s is None else text[s[0]:s[1]]


def test_dotted_capital_i_before_match_keeps_offsets():
    # 'İ'.lower() is two characters; offsets used to shift or raise IndexError.
    text = "İİİİ İstanbul: The Ferry Tickets cost too much every week."
    assert span_text(text, "the ferry tickets cost too much") == "The Ferry Tickets cost too much"
    text = "İ" * 30 + " ABCDEFGHIJKLMNOPQRST"
    assert span_text(text, "abcdefghijklmnopqrst") == "ABCDEFGHIJKLMNOPQRST"


def test_curly_and_straight_apostrophes_match_both_ways():
    text = "He said “it’s been broken for three weeks” and left."
    assert span_text(text, "it's been broken for three weeks") == "it’s been broken for three weeks"
    assert span_text(text, '"it\'s been broken for three weeks"') == \
        "“it’s been broken for three weeks”"
    straight = "We can't export the invoices at all."
    assert span_text(straight, "can’t export the invoices") == "can't export the invoices"


def test_nfd_text_matches_nfc_quote_with_whole_characters():
    text = unicodedata.normalize("NFD", "Le café était fermé depuis trois semaines.")
    quote = unicodedata.normalize("NFC", "Café était fermé depuis")
    got = span_text(text, quote)
    assert unicodedata.normalize("NFC", got) == "café était fermé depuis"
    assert got.startswith("c") and unicodedata.combining(got[-1]) == 0  # no split mark


def test_non_breaking_spaces_and_whitespace_runs():
    text = "Il faut attendre   trois mois pour un rendez-vous."
    assert span_text(text, "faut attendre trois mois") == "faut attendre   trois mois"


def test_short_quotes_are_rejected():
    text = "The scanner jams on every page and wastes paper."
    assert find_quote(text, "x" * 3) is None
    assert find_quote(text, "scanner jams o") is None             # 14 chars, present
    assert span_text(text, "scanner jams on") == "scanner jams on"  # 15 chars
    assert MIN_QUOTE_CHARS == 15


def test_copied_span_whole_field_and_long_runs():
    text = "Je passe trois heures chaque vendredi à recopier les factures à la main."
    assert copied_span(text, "trois heures chaque vendredi")
    assert copied_span(text, "Summary: je passe trois heures chaque vendredi à recopier les factures")
    assert not copied_span(text, "They copy invoices by hand every Friday.")
    assert not copied_span(text, "trois heures")  # too short to count as a copy
