from pathlib import Path

from bracket_matrix.conferences import build_team_conference_rows_from_bart, load_team_conferences


def test_build_team_conference_rows_uses_alias_identity(tmp_path: Path):
    aliases_path = tmp_path / "aliases.csv"
    aliases_path.write_text(
        "alias,canonical_slug,team_display,ncaa_id,espn_id\n"
        "Connecticut,uconn,UConn,,\n",
        encoding="utf-8",
    )
    bart_csv = "rank,team,conf\n1,Connecticut,BE\n2,South Carolina,SEC\n"

    rows = build_team_conference_rows_from_bart(bart_csv, aliases_path)
    rows_by_slug = {row["canonical_slug"]: row for row in rows}

    assert rows_by_slug["uconn"]["conference"] == "BE"
    assert rows_by_slug["uconn"]["team_display"] == "UConn"
    assert rows_by_slug["south-carolina"]["conference"] == "SEC"


def test_load_team_conferences_returns_slug_lookup(tmp_path: Path):
    conferences_path = tmp_path / "team_conferences.csv"
    conferences_path.write_text(
        "canonical_slug,team_display,conference,source_team,source_conference\n"
        "uconn,UConn,BE,Connecticut,BE\n",
        encoding="utf-8",
    )

    conferences = load_team_conferences(conferences_path)
    assert conferences == {"uconn": "BE"}
