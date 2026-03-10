from bracket_matrix.render import (
    _abbrev_source_label,
    _bracket_share_heat_class,
    _format_avg_seed,
    _format_bracket_share,
    _format_generated_at_et,
    _format_source_update_date,
    _order_source_keys_by_recency,
    render_index_html,
    split_other_candidates,
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


def _row_with_sources(
    team: str,
    conference: str,
    appearances: int,
    avg_seed: float,
    source_seeds: dict[str, int | str | None],
) -> MatrixRow:
    return MatrixRow(
        canonical_slug=team.lower().replace(" ", "-"),
        team_display=team,
        ncaa_id="",
        espn_id="",
        appearances=appearances,
        avg_seed=avg_seed,
        conference=conference,
        source_seeds=source_seeds,
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


def test_split_projected_field_prefers_recency_before_avg_seed_for_ties():
    rows = [
        _row_with_sources(
            "Recent Inclusion",
            "",
            appearances=3,
            avg_seed=4.0,
            source_seeds={"new": 6, "old": 4},
        ),
        _row_with_sources(
            "Older Inclusion Better Seed",
            "",
            appearances=3,
            avg_seed=2.0,
            source_seeds={"old": 2},
        ),
    ]

    projected, _ = split_projected_field(rows, source_keys_by_recency=["new", "old"], field_size=1)
    assert [row.team_display for row in projected] == ["Recent Inclusion"]


def test_split_other_candidates_prioritize_in_then_ffo_then_nfo():
    rows = [
        _row_with_sources(
            "FFO Heavy",
            "",
            appearances=1,
            avg_seed=99.0,
            source_seeds={"s1": "FFO", "s2": "FFO", "s3": "NFO"},
        ),
        _row_with_sources(
            "NFO Heavy",
            "",
            appearances=1,
            avg_seed=99.0,
            source_seeds={"s1": "NFO", "s2": "NFO"},
        ),
        _row_with_sources(
            "Seeded Bubble",
            "",
            appearances=2,
            avg_seed=12.0,
            source_seeds={"s1": 12, "s2": 11, "s3": "NFO"},
        ),
    ]

    bubble, auto_bid = split_other_candidates(rows)
    assert [row.team_display for row in bubble] == ["Seeded Bubble", "FFO Heavy", "NFO Heavy"]
    assert auto_bid == []


def test_split_other_candidates_separates_auto_bid_and_sorts_by_avg_seed():
    rows = [
        _row_with_sources(
            "Fewer Mentions",
            "",
            appearances=2,
            avg_seed=6.0,
            source_seeds={"s1": 6, "s2": 8},
        ),
        _row_with_sources(
            "Lower Seed",
            "",
            appearances=1,
            avg_seed=5.0,
            source_seeds={"s2": 5},
        ),
        _row_with_sources(
            "Bubble Team",
            "",
            appearances=1,
            avg_seed=11.0,
            source_seeds={"s1": "FFO", "s3": "NFO", "s4": 11},
        ),
    ]

    bubble, auto_bid = split_other_candidates(rows)
    assert [row.team_display for row in bubble] == ["Bubble Team"]
    assert [row.team_display for row in auto_bid] == ["Lower Seed", "Fewer Mentions"]


def test_split_projected_field_excludes_ffo_only_rows_from_projected():
    rows = [
        _row_with_sources(
            "FFO Champ",
            "Summit",
            appearances=0,
            avg_seed=99.0,
            source_seeds={"s1": "FFO", "s2": "FFO"},
        ),
        _row_with_sources(
            "Seeded Team",
            "ACC",
            appearances=2,
            avg_seed=7.0,
            source_seeds={"s1": 7, "s2": 7},
        ),
    ]

    projected, others = split_projected_field(rows, field_size=1)
    assert [row.team_display for row in projected] == ["Seeded Team"]
    assert [row.team_display for row in others] == ["FFO Champ"]


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


def test_format_bracket_share_calculates_percentage():
    assert _format_bracket_share(5, 6) == "83%"
    assert _format_bracket_share(0, 0) == "0%"


def test_bracket_share_heat_class_uses_percentage_buckets():
    assert _bracket_share_heat_class(0, 0) == "share-0"
    assert _bracket_share_heat_class(1, 4) == "share-0"
    assert _bracket_share_heat_class(2, 5) == "share-1"
    assert _bracket_share_heat_class(3, 5) == "share-2"
    assert _bracket_share_heat_class(4, 5) == "share-3"
    assert _bracket_share_heat_class(5, 5) == "share-4"


def test_format_generated_at_et_converts_from_utc_iso():
    assert _format_generated_at_et("2026-01-15T15:30:00+00:00") == "01/15 10:30 ET"


def test_format_avg_seed_returns_na_for_sentinel_value():
    assert _format_avg_seed(99.0) == "na"
    assert _format_avg_seed(7.25) == "7.2"


def test_render_index_html_links_source_headers(tmp_path):
    output_path = tmp_path / "index.html"
    matrix_rows = [
        _row("Team A", "SEC", appearances=2, avg_seed=1.0),
        _row_with_sources(
            "Bubble Team",
            "A10",
            appearances=0,
            avg_seed=99.0,
            source_seeds={"espn": "FFO", "her_hoop_stats": "NFO"},
        ),
    ]
    source_keys = ["espn", "her_hoop_stats"]
    source_key_to_name = {"espn": "ESPN", "her_hoop_stats": "Her Hoop Stats"}
    source_meta_rows = [
        {
            "source_key": "espn",
            "source_name": "ESPN",
            "source_url": "https://example.com/espn",
            "source_updated_at_iso": "2026-03-08T10:00:00+00:00",
            "status": "ok",
        },
        {
            "source_key": "her_hoop_stats",
            "source_name": "Her Hoop Stats",
            "source_url": "https://example.com/hhs",
            "source_updated_at_iso": "2026-03-07T10:00:00+00:00",
            "status": "ok",
        },
    ]

    render_index_html(
        matrix_rows=matrix_rows,
        source_meta_rows=source_meta_rows,
        source_keys=source_keys,
        source_key_to_name=source_key_to_name,
        generated_at_iso="2026-03-08T12:00:00+00:00",
        output_path=output_path,
    )

    html = output_path.read_text(encoding="utf-8")
    assert "Updated at " in html
    assert "<th>% Brackets</th>" in html
    assert "<th>% F4O</th>" in html
    assert "<th>% N4O</th>" in html
    assert "class=\"bracket-share share-4\">100%</td>" in html
    assert "<th title=\"ESPN\"><a href=\"https://example.com/espn\"" not in html
    assert "<td><a href=\"https://example.com/espn\" target=\"_blank\" rel=\"noopener noreferrer\">ESPN</a></td>" in html
    assert "<td><a href=\"https://example.com/hhs\" target=\"_blank\" rel=\"noopener noreferrer\">Her Hoop Stats</a></td>" in html
    assert "Bubble Team</td><td>A10</td><td>na</td><td class=\"bracket-share share-0\">0%</td><td>50%</td><td>50%</td>" in html
