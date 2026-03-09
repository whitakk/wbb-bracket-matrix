import json
from pathlib import Path

from bracket_matrix.config import PipelinePaths
from bracket_matrix import pipeline


def test_run_all_writes_expected_outputs_with_espn_fallback(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    latest_dir = data_dir / "latest"
    snapshot_dir = data_dir / "snapshots"
    site_dir = tmp_path / "site"

    for d in [config_dir, data_dir, latest_dir, snapshot_dir, site_dir]:
        d.mkdir(parents=True, exist_ok=True)

    (data_dir / "aliases.csv").write_text(
        "alias,canonical_slug,team_display,ncaa_id,espn_id\nN.C. State,north-carolina-state,NC State,,\n",
        encoding="utf-8",
    )
    (data_dir / "team_conferences.csv").write_text(
        "canonical_slug,team_display,conference,source_team,source_conference\n"
        "north-carolina-state,NC State,ACC,NC State,ACC\n",
        encoding="utf-8",
    )

    sources = {
        "sources": [
            {
                "source_key": "her_hoop_stats",
                "source_name": "Her Hoop Stats",
                "source_url": "https://herhoopstats.com/bracketology/",
                "parser": "herhoopstats",
                "use_playwright_fallback": False,
            },
            {
                "source_key": "espn",
                "source_name": "ESPN",
                "source_url": "https://www.espn.com/story",
                "parser": "espn",
                "use_playwright_fallback": True,
            },
        ]
    }
    settings = {
        "retention_days": 365,
        "request_timeout_seconds": 20,
        "fuzzy_threshold": 94,
        "fuzzy_review_threshold": 86,
        "fuzzy_ambiguous_margin": 3,
        "user_agent": "test-agent",
    }
    (config_dir / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    (config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    fixture_dir = Path(__file__).parent / "fixtures"
    her_html = (fixture_dir / "herhoopstats.html").read_text(encoding="utf-8")
    espn_blocked = (fixture_dir / "espn_blocked.html").read_text(encoding="utf-8")
    espn_real = (fixture_dir / "espn.html").read_text(encoding="utf-8")

    def fake_fetcher(url: str, timeout_seconds: int, user_agent: str) -> str:
        if "espn" in url:
            return espn_blocked
        return her_html

    def fake_playwright_fetcher(url: str, timeout_seconds: int) -> str:
        return espn_real

    original_run_scrape = pipeline.run_scrape

    def patched_run_scrape(*, paths=None, enable_playwright_fallback=True):
        return original_run_scrape(
            paths=paths,
            enable_playwright_fallback=enable_playwright_fallback,
            fetcher=fake_fetcher,
            playwright_fetcher=fake_playwright_fetcher,
        )

    monkeypatch.setattr(pipeline, "run_scrape", patched_run_scrape)

    paths = PipelinePaths(
        root_dir=tmp_path,
        config_dir=config_dir,
        data_dir=data_dir,
        latest_dir=latest_dir,
        snapshot_dir=snapshot_dir,
        site_dir=site_dir,
    )

    pipeline.run_all(paths=paths, enable_playwright_fallback=True, retention_days=365)

    assert (latest_dir / "source_rows_latest.csv").exists()
    assert (latest_dir / "matrix_latest.csv").exists()
    assert (latest_dir / "unresolved_matches_latest.csv").exists()
    assert (site_dir / "index.html").exists()
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "WBB Bracket Matrix" in index_html
    assert "ESPN" in index_html
    assert "Conf" in index_html

    matrix_csv = (latest_dir / "matrix_latest.csv").read_text(encoding="utf-8")
    assert "conference" in matrix_csv.splitlines()[0].lower()
