from bracket_matrix.render import split_projected_field
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
