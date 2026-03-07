from pathlib import Path

from bracket_matrix.scrapers.collegesportsmadness import parse_college_sports_madness
from bracket_matrix.scrapers.espn import parse_espn
from bracket_matrix.scrapers.herhoopstats import parse_her_hoop_stats


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_her_hoop_stats_fixture():
    result = parse_her_hoop_stats(
        source_key="her_hoop_stats",
        source_name="Her Hoop Stats",
        source_url="https://example.com",
        html=_read("herhoopstats.html"),
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )
    assert result.updated_at_raw
    assert any(row.team_raw == "UCLA" and row.seed == 1 for row in result.rows)


def test_parse_college_sports_madness_fixture():
    result = parse_college_sports_madness(
        source_key="college_sports_madness",
        source_name="College Sports Madness",
        source_url="https://example.com",
        html=_read("collegesportsmadness.html"),
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )
    assert len(result.rows) >= 2
    assert any(row.team_raw == "Texas" and row.seed == 1 for row in result.rows)


def test_parse_espn_blocked_page_returns_no_rows():
    blocked = _read("espn_blocked.html")
    result = parse_espn(
        source_key="espn",
        source_name="ESPN",
        source_url="https://example.com",
        html=blocked,
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )
    assert len(result.rows) == 0
