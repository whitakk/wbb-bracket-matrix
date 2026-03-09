from bracket_matrix.render import (
    _abbrev_source_label,
    _format_source_update_date,
    _order_source_keys_by_recency,
    split_projected_field,
)
from bracket_matrix.types import MatrixRow


def _row(team: str, conference: str, appearances: int, avg_seed: float) -> MatrixRow:
    return MatrixRow(
        canonical_slug=team.lower().replace(" ", "-"),
        team_display=team,
        ncaa_id="",
        espn_id="",
        appearances=appearances,
        avg_seed=avg_seed,
        conference=conference,
        source_seeds={},
    )


def test_split_projected_field_picks_conference_plurality_winner():
    rows = [
        _row("Team A", "SEC", appearances=4, avg_seed=3.0),
        _row("Team B", "SEC", appearances=3, avg_seed=1.0),
        _row("Team C", "ACC", appearances=2, avg_seed=2.0),
        _row("Team D", "ACC", appearances=2, avg_seed=4.0),
        _row("Team E", "B12", appearances=1, avg_seed=5.0),
    ]

    projected, others = split_projected_field(rows, field_size=3)

    projected_teams = {row.team_display for row in projected}
    assert "Team A" in projected_teams
    assert "Team C" in projected_teams
    assert "Team E" in projected_teams
    assert "Team B" in {row.team_display for row in others}


def test_split_projected_field_fills_remaining_by_appearances_then_seed():
    rows = [
        _row("SEC Winner", "SEC", appearances=5, avg_seed=1.0),
        _row("ACC Winner", "ACC", appearances=4, avg_seed=2.0),
        _row("At Large 1", "", appearances=4, avg_seed=3.0),
        _row("At Large 2", "", appearances=4, avg_seed=4.0),
        _row("At Large 3", "", appearances=3, avg_seed=1.0),
    ]

    projected, others = split_projected_field(rows, field_size=4)

    assert [row.team_display for row in projected] == [
        "SEC Winner",
        "ACC Winner",
        "At Large 1",
        "At Large 2",
    ]
    assert [row.team_display for row in others] == ["At Large 3"]


def test_abbrev_source_label_prefers_short_initials_when_long():
    assert _abbrev_source_label("Her Hoop Stats") == "HHS"
    assert _abbrev_source_label("College Sports Madness") == "CSM"
    assert _abbrev_source_label("CBS Sports") == "CBS"
    assert _abbrev_source_label("USA Today") == "USAT"
    assert _abbrev_source_label("The Athletic") == "ATH"
    assert _abbrev_source_label("ESPN") == "ESPN"


def test_source_keys_order_by_updated_at_recency():
    source_keys = ["a", "b", "c"]
    source_meta_lookup = {
        "a": {"source_updated_at_iso": "2026-03-05T00:00:00+00:00"},
        "b": {"source_updated_at_iso": "2026-03-08T00:00:00+00:00"},
        "c": {"source_updated_at_iso": ""},
    }
    assert _order_source_keys_by_recency(source_keys, source_meta_lookup) == ["b", "a", "c"]


def test_format_source_update_date_returns_iso_date_only():
    row = {"source_updated_at_iso": "2026-03-08T23:55:00+00:00", "source_updated_at_raw": "3/8/26, 11:55pm ET"}
    assert _format_source_update_date(row) == "3/8"
