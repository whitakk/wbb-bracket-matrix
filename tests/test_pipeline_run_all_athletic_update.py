import json

from bracket_matrix.config import PipelinePaths
from bracket_matrix import pipeline


def test_run_all_triggers_athletic_update_check_when_source_enabled(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    latest_dir = data_dir / "latest"
    snapshot_dir = data_dir / "snapshots"
    site_dir = tmp_path / "site"

    for path in [config_dir, data_dir, latest_dir, snapshot_dir, site_dir]:
        path.mkdir(parents=True, exist_ok=True)

    (config_dir / "sources.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_key": "the_athletic",
                        "source_name": "The Athletic",
                        "source_url": "https://www.nytimes.com/athletic/tag/bracketcentral/",
                        "parser": "theathletic",
                        "use_playwright_fallback": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "settings.json").write_text(
        json.dumps(
            {
                "retention_days": 365,
                "request_timeout_seconds": 20,
                "fuzzy_threshold": 94,
                "fuzzy_review_threshold": 86,
                "fuzzy_ambiguous_margin": 3,
                "user_agent": "test-agent",
            }
        ),
        encoding="utf-8",
    )

    paths = PipelinePaths(
        root_dir=tmp_path,
        config_dir=config_dir,
        data_dir=data_dir,
        latest_dir=latest_dir,
        snapshot_dir=snapshot_dir,
        site_dir=site_dir,
    )

    monkeypatch.setattr(pipeline, "run_scrape", lambda **kwargs: {})
    monkeypatch.setattr(pipeline, "run_build", lambda **kwargs: {})
    monkeypatch.setattr(pipeline, "run_publish", lambda **kwargs: {"site_index": site_dir / "index.html"})

    invoked: dict[str, str] = {}

    def fake_check_for_new_athletic_update(*, notify_email: str, use_playwright: bool):
        invoked["notify_email"] = notify_email
        invoked["use_playwright"] = str(use_playwright)
        return {
            "status": "no_change",
            "latest_url": "https://www.nytimes.com/athletic/7092398/2026/03/06/women-ncaa-tournament-bracket-watch-uconn-ucla/",
            "previous_url": "",
            "state_file": str(data_dir / "latest" / "the_athletic_last_seen_url.txt"),
        }

    monkeypatch.setattr(
        "bracket_matrix.athletic_updates.check_for_new_athletic_update",
        fake_check_for_new_athletic_update,
    )

    monkeypatch.setenv("GMAIL_TO", "me@example.com")
    monkeypatch.setenv("BRACKET_MATRIX_CHECK_ATHLETIC_USE_PLAYWRIGHT", "true")

    pipeline.run_all(paths=paths, enable_playwright_fallback=True, retention_days=365)

    assert invoked["notify_email"] == "me@example.com"
    assert invoked["use_playwright"] == "True"
