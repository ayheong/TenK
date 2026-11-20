import pytest

from app.edgar.sector import classify_sector


@pytest.mark.parametrize(
    "sic,expected",
    [
        ("6021", "financials"),  # national commercial bank
        ("6331", "financials"),  # fire, marine & casualty insurance
        ("6199", "financials"),
        ("6770", "financials"),  # blank check / holding
        ("6798", "real_estate"),  # REIT, carved out of the finance range
        ("6512", "real_estate"),
        ("4911", "utilities"),
        ("4813", "other"),  # telecom sits next to utilities but is not one
        ("1311", "energy"),  # crude petroleum & natural gas
        ("2911", "energy"),  # petroleum refining
        ("2836", "biotech_pharma"),
        ("2834", "biotech_pharma"),
        ("8731", "biotech_pharma"),
        ("5331", "other"),
        ("7372", "other"),
    ],
)
def test_classify_sector(sic, expected) -> None:
    assert classify_sector(sic) == expected


def test_accepts_integer_codes() -> None:
    assert classify_sector(6021) == "financials"


@pytest.mark.parametrize("sic", [None, "", "abc", "60x1"])
def test_missing_or_malformed_code_is_other(sic) -> None:
    assert classify_sector(sic) == "other"


@pytest.mark.parametrize("boundary,expected", [
    ("5999", "other"),
    ("6000", "financials"),
    ("6499", "financials"),
    ("6500", "real_estate"),
    ("6599", "real_estate"),
    ("6600", "other"),
    ("6699", "other"),
    ("6700", "financials"),
])
def test_range_boundaries(boundary, expected) -> None:
    assert classify_sector(boundary) == expected
