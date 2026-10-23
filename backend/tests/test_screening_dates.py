from datetime import date

from app.services.dates import add_years, age_on, parse_date
from app.services.rules import format_score
from app.services.screening import WatchlistEntry, normalise, screen, similarity

TITLES = {"MR", "MRS", "MS", "MISS", "DR", "SHRI", "SMT", "KUMARI"}


def test_normalise_drops_titles_punctuation_and_sorts_tokens():
    assert normalise("Mr. Ravi-Kumar  Sharma", TITLES) == "KUMAR RAVI SHARMA"
    assert normalise("Shri Varun Chandra Verma", TITLES) == "CHANDRA VARUN VERMA"
    assert normalise("Sharma Ravi Kumar", TITLES) == normalise("Ravi Kumar Sharma", TITLES)


def test_example_4_similarity_is_0_7647():
    s = similarity(normalise("Ravi Kumar Sharma", TITLES), normalise("Ravi K Sharma", TITLES))
    assert format_score(s) == "0.7647"


def test_similarity_edge_cases():
    assert similarity("", "") == 1.0
    assert format_score(similarity(normalise("Aisha Gupta", TITLES), normalise("Aish Gupta", TITLES))) == "0.9091"


def test_screening_match_possible_and_empty_dob():
    entries = [
        WatchlistEntry("SANCTIONS", "SAN0002", "Valko Quillon", "", "1986-02-23"),
        WatchlistEntry("SANCTIONS", "SAN0048", "Tavish Morrigan", "", ""),
    ]
    assert screen("Valko Quillon", "1986-02-23", entries, TITLES, 0.9, 0.8)[0] == "MATCH"
    result, hit = screen("Valko Quillon", "1979-07-14", entries, TITLES, 0.9, 0.8)
    assert result == "POSSIBLE" and hit.dob_comparison == "DIFFERENT"
    result, hit = screen("Tavish Morrigana", "1979-07-14", entries, TITLES, 0.9, 0.8)
    assert result == "MATCH" and hit.dob_comparison == "LIST_DOB_EMPTY"
    assert screen("Ravi Kumar Sharma", "1990-05-15", entries, TITLES, 0.9, 0.8)[0] == "NONE"


def test_age_and_rekyc_dates():
    assert age_on(date(2008, 3, 4), date(2026, 3, 4)) == 18
    assert age_on(date(2008, 3, 5), date(2026, 3, 4)) == 17
    assert add_years(date(2024, 2, 29), 2) == date(2026, 2, 28)
    assert add_years(date(2026, 3, 4), 10) == date(2036, 3, 4)
    assert parse_date("1977-11-Z6") is None
