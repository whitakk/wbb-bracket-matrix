from bracket_matrix.merge import build_matrix_rows
from bracket_matrix.normalize import TeamResolution
from bracket_matrix.types import SourceProjectionRow, TeamIdentity


def test_matrix_sort_by_avg_seed_then_appearances():
    rows = [
        SourceProjectionRow(
            source_key="a",
            source_name="A",
            source_url="https://a",
            source_updated_at_raw="",
            source_updated_at_iso="",
            team_raw="UCLA",
            seed=1,
            is_play_in=False,
            scraped_at_iso="2026-03-06T00:00:00+00:00",
        ),
        SourceProjectionRow(
            source_key="b",
            source_name="B",
            source_url="https://b",
            source_updated_at_raw="",
            source_updated_at_iso="",
            team_raw="UCLA",
            seed=2,
            is_play_in=False,
            scraped_at_iso="2026-03-06T00:00:00+00:00",
        ),
        SourceProjectionRow(
            source_key="a",
            source_name="A",
            source_url="https://a",
            source_updated_at_raw="",
            source_updated_at_iso="",
            team_raw="Texas",
            seed=1,
            is_play_in=False,
            scraped_at_iso="2026-03-06T00:00:00+00:00",
        ),
    ]

    resolutions = {
        "UCLA": TeamResolution(TeamIdentity("ucla", "UCLA"), "exact", 100.0),
        "Texas": TeamResolution(TeamIdentity("texas", "Texas"), "exact", 100.0),
    }

    matrix = build_matrix_rows(rows, resolutions, source_keys=["a", "b"])
    assert matrix[0].team_display == "Texas"
    assert matrix[1].team_display == "UCLA"


def test_matrix_excludes_ffo_nfo_from_average_seed():
    rows = [
        SourceProjectionRow(
            source_key="a",
            source_name="A",
            source_url="https://a",
            source_updated_at_raw="",
            source_updated_at_iso="",
            team_raw="Bubble U",
            seed="FFO",
            is_play_in=False,
            scraped_at_iso="2026-03-06T00:00:00+00:00",
        ),
        SourceProjectionRow(
            source_key="b",
            source_name="B",
            source_url="https://b",
            source_updated_at_raw="",
            source_updated_at_iso="",
            team_raw="Bubble U",
            seed=11,
            is_play_in=False,
            scraped_at_iso="2026-03-06T00:00:00+00:00",
        ),
        SourceProjectionRow(
            source_key="c",
            source_name="C",
            source_url="https://c",
            source_updated_at_raw="",
            source_updated_at_iso="",
            team_raw="Bubble U",
            seed="NFO",
            is_play_in=False,
            scraped_at_iso="2026-03-06T00:00:00+00:00",
        ),
    ]

    resolutions = {
        "Bubble U": TeamResolution(TeamIdentity("bubble-u", "Bubble U"), "exact", 100.0),
    }

    matrix = build_matrix_rows(rows, resolutions, source_keys=["a", "b", "c"])
    assert len(matrix) == 1
    assert matrix[0].avg_seed == 11
    assert matrix[0].appearances == 1
    assert matrix[0].source_seeds["a"] == "FFO"
    assert matrix[0].source_seeds["c"] == "NFO"
