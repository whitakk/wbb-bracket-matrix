import json

from bracket_matrix.config import PipelinePaths
from bracket_matrix import pipeline


def test_run_refresh_conferences_writes_static_csv(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    latest_dir = data_dir / "latest"
    snapshot_dir = data_dir / "snapshots"
    site_dir = tmp_path / "site"

    for d in [config_dir, data_dir, latest_dir, snapshot_dir, site_dir]:
        d.mkdir(parents=True, exist_ok=True)

    settings = {
        "retention_days": 365,
        "request_timeout_seconds": 20,
        "fuzzy_threshold": 94,
        "fuzzy_review_threshold": 86,
        "fuzzy_ambiguous_margin": 3,
        "user_agent": "test-agent",
    }
    (config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    (data_dir / "aliases.csv").write_text(
        "alias,canonical_slug,team_display,ncaa_id,espn_id\n"
        "Connecticut,uconn,UConn,,\n",
        encoding="utf-8",
    )

    def fake_fetch_bart_team_results_csv(*, season: int, timeout_seconds: int, user_agent: str) -> str:
        assert season == 2026
        return "rank,team,conf\n1,Connecticut,BE\n"

    monkeypatch.setattr(pipeline, "fetch_bart_team_results_csv", fake_fetch_bart_team_results_csv)

    paths = PipelinePaths(
        root_dir=tmp_path,
        config_dir=config_dir,
        data_dir=data_dir,
        latest_dir=latest_dir,
        snapshot_dir=snapshot_dir,
        site_dir=site_dir,
    )

    output_path = pipeline.run_refresh_conferences(paths=paths, season=2026)
    assert output_path == data_dir / "team_conferences.csv"
    output = output_path.read_text(encoding="utf-8")
    assert "canonical_slug,team_display,conference,source_team,source_conference" in output
    assert "uconn,UConn,BE,Connecticut,BE" in output
