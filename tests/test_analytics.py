from pathlib import Path

from bracket_matrix.analytics import (
    assign_greedy_cross_source_matches,
    combine_ncaa_wab_and_net_rows,
    merge_analytics_rows,
    parse_ncaa_auto_bids_table,
    parse_bart_power_table,
    parse_ncaa_net_table,
    parse_ncaa_wab_table,
    suggest_cross_source_matches,
)


def test_parse_ncaa_wab_table_extracts_rankings():
    html = """
    <table>
      <thead>
        <tr><th>Rank</th><th>School</th><th>Conf</th><th>WAB</th></tr>
      </thead>
      <tbody>
        <tr><td>1</td><td>UCLA</td><td>Big Ten</td><td>17.07</td></tr>
      </tbody>
    </table>
    """
    rows = parse_ncaa_wab_table(html)
    assert rows == [{"team": "UCLA", "conference": "Big Ten", "wab_rank": "1", "wab": "17.07"}]


def test_parse_ncaa_net_table_extracts_records():
    html = """
    <table>
      <thead>
        <tr>
          <th>Rank</th><th>School</th><th>Record</th><th>Conf</th><th>Road</th><th>Neutral</th><th>Home</th><th>Non-Div I</th><th>Prev</th><th>Quad 1</th><th>Quad 2</th><th>Quad 3</th><th>Quad 4</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>8</td><td>Duke</td><td>27-7</td><td>ACC</td><td>9-4</td><td>5-1</td><td>13-2</td><td>0-0</td><td>7</td><td>5-3</td><td>6-1</td><td>8-0</td><td>10-0</td>
        </tr>
      </tbody>
    </table>
    """
    rows = parse_ncaa_net_table(html)
    assert rows == [
        {
            "team": "Duke",
            "conference": "ACC",
            "net_rank": "8",
            "q1_w": "5",
            "q1_l": "3",
            "q2_w": "6",
            "q2_l": "1",
            "q3_w": "8",
            "q3_l": "0",
            "q4_w": "10",
            "q4_l": "0",
        }
    ]


def test_parse_ncaa_auto_bids_table_extracts_non_empty_automatic_bids():
    html = """
    <table>
      <thead>
        <tr><th>Conference</th><th>Schedule</th><th>Automatic Bid</th><th>Location</th></tr>
      </thead>
      <tbody>
        <tr><td>ACC</td><td>...</td><td>Duke</td><td>Greensboro</td></tr>
        <tr><td>SEC</td><td>...</td><td></td><td>Greenville</td></tr>
      </tbody>
    </table>
    """
    rows = parse_ncaa_auto_bids_table(html)
    assert rows == [{"conference": "ACC", "team": "Duke"}]


def test_combine_ncaa_wab_and_net_rows_merges_by_team(tmp_path: Path):
    aliases_path = tmp_path / "aliases.csv"
    aliases_path.write_text(
        "alias,canonical_slug,team_display,ncaa_id,espn_id\n"
        "Connecticut,uconn,UConn,,\n"
        "UConn,uconn,UConn,,\n",
        encoding="utf-8",
    )

    wab_rows = [
        {"team": "Connecticut", "conference": "Big East", "wab_rank": "2", "wab": "14.0"},
    ]
    net_rows = [
        {
            "team": "UConn",
            "conference": "Big East",
            "net_rank": "1",
            "q1_w": "9",
            "q1_l": "0",
            "q2_w": "5",
            "q2_l": "0",
            "q3_w": "8",
            "q3_l": "0",
            "q4_w": "12",
            "q4_l": "0",
        }
    ]

    combined_rows, mapping_issues = combine_ncaa_wab_and_net_rows(
        wab_rows=wab_rows,
        net_rows=net_rows,
        aliases_path=aliases_path,
        fuzzy_threshold=94,
        fuzzy_review_threshold=86,
        fuzzy_ambiguous_margin=3,
    )

    assert combined_rows == [
        {
            "team": "UConn",
            "conference": "Big East",
            "net_rank": "1",
            "wab_rank": "2",
            "wab": "14.0",
            "q1_w": "9",
            "q1_l": "0",
            "q2_w": "5",
            "q2_l": "0",
            "q3_w": "8",
            "q3_l": "0",
            "q4_w": "12",
            "q4_l": "0",
        }
    ]
    assert mapping_issues == []


def test_parse_bart_power_table_extracts_rank_team_conf_barthag():
    html = """
    <table>
      <tr><th>Rk</th><th>Team</th><th>Conf</th><th>Barthag</th></tr>
      <tr><td>1</td><td>Connecticut</td><td>BE</td><td>.9996 1</td></tr>
      <tr><td>2</td><td>UCLA</td><td>B10</td><td>.9991 2</td></tr>
    </table>
    """
    rows = parse_bart_power_table(html)
    assert rows == [
        {"team": "Connecticut", "conference": "BE", "bart_rank": "1", "barthag": ".9996"},
        {"team": "UCLA", "conference": "B10", "bart_rank": "2", "barthag": ".9991"},
    ]


def test_merge_analytics_rows_outputs_superset_and_missing_flags(tmp_path: Path):
    aliases_path = tmp_path / "aliases.csv"
    aliases_path.write_text(
        "alias,canonical_slug,team_display,ncaa_id,espn_id\n"
        "Connecticut,uconn,UConn,,\n"
        "Duke,duke,Duke,,\n",
        encoding="utf-8",
    )

    ncaa_rows = [
        {
            "team": "Duke",
            "conference": "ACC",
            "net_rank": "8",
            "wab_rank": "5",
            "wab": "7.2",
            "q1_w": "5",
            "q1_l": "3",
            "q2_w": "6",
            "q2_l": "1",
            "q3_w": "8",
            "q3_l": "0",
            "q4_w": "10",
            "q4_l": "0",
        }
    ]
    bart_rows = [
        {"team": "Connecticut", "conference": "BE", "bart_rank": "1", "barthag": ".9996"},
    ]

    merged_rows, mapping_issues = merge_analytics_rows(
        ncaa_rows=ncaa_rows,
        bart_rows=bart_rows,
        aliases_path=aliases_path,
        fuzzy_threshold=94,
        fuzzy_review_threshold=86,
        fuzzy_ambiguous_margin=3,
    )

    assert {row["canonical_slug"] for row in merged_rows} == {"duke", "uconn"}
    assert any(row["canonical_slug"] == "duke" and row["present_in_bart"] == "0" for row in merged_rows)
    assert any(row["canonical_slug"] == "uconn" and row["present_in_ncaa"] == "0" for row in merged_rows)
    assert any(issue["issue_type"] == "missing_in_bart" for issue in mapping_issues)
    assert any(issue["issue_type"] == "missing_in_ncaa" for issue in mapping_issues)


def test_suggest_cross_source_matches_returns_top_candidates():
    merged_rows = [
        {
            "canonical_slug": "kansas-state",
            "team_display": "Kansas State",
            "conference": "B12",
            "present_in_ncaa": "1",
            "present_in_bart": "0",
        },
        {
            "canonical_slug": "kansas",
            "team_display": "Kansas",
            "conference": "B12",
            "present_in_ncaa": "0",
            "present_in_bart": "1",
        },
        {
            "canonical_slug": "kansas-state-alt",
            "team_display": "Kansas St.",
            "conference": "B12",
            "present_in_ncaa": "0",
            "present_in_bart": "1",
        },
    ]

    suggestions = suggest_cross_source_matches(merged_rows)
    assert len(suggestions) == 2
    top = suggestions[0]
    assert top["ncaa_team"] == "Kansas State"
    assert top["bart_team_candidate"] == "Kansas St."
    assert top["candidate_rank"] == "1"


def test_assign_greedy_cross_source_matches_is_one_to_one():
    merged_rows = [
        {
            "canonical_slug": "ncaa-a",
            "team_display": "Central Mich.",
            "conference": "MAC",
            "present_in_ncaa": "1",
            "present_in_bart": "0",
        },
        {
            "canonical_slug": "ncaa-b",
            "team_display": "Eastern Mich.",
            "conference": "MAC",
            "present_in_ncaa": "1",
            "present_in_bart": "0",
        },
        {
            "canonical_slug": "bart-a",
            "team_display": "Central Michigan",
            "conference": "MAC",
            "present_in_ncaa": "0",
            "present_in_bart": "1",
        },
        {
            "canonical_slug": "bart-b",
            "team_display": "Eastern Michigan",
            "conference": "MAC",
            "present_in_ncaa": "0",
            "present_in_bart": "1",
        },
    ]

    assignments = assign_greedy_cross_source_matches(merged_rows)
    assert len(assignments) == 2
    assert {row["ncaa_canonical_slug"] for row in assignments} == {"ncaa-a", "ncaa-b"}
    assert {row["bart_canonical_slug"] for row in assignments} == {"bart-a", "bart-b"}
