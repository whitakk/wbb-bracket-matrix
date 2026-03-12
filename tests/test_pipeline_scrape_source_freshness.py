import csv
import json

from bracket_matrix import pipeline
from bracket_matrix.config import PipelinePaths
from bracket_matrix.types import ScrapeResult, SourceProjectionRow


def test_run_scrape_keeps_previous_rows_when_source_not_newer(tmp_path, monkeypatch):
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
                        "source_key": "ncaa",
                        "source_name": "NCAA",
                        "source_url": "https://example.com/search",
                        "parser": "fake_ncaa",
                        "use_playwright_fallback": False,
                        "require_newer_than_previous": True,
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

    with (latest_dir / "source_rows_latest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=pipeline.DEFAULT_RAW_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "source_key": "ncaa",
                "source_name": "NCAA",
                "source_url": "https://www.ncaa.com/news/basketball-women/article/2026-03-10/sample",
                "source_updated_at_raw": "2026-03-10T14:15:00Z",
                "source_updated_at_iso": "2026-03-10T14:15:00+00:00",
                "team_raw": "Old Team",
                "seed": 5,
                "is_play_in": False,
                "scraped_at_iso": "2026-03-10T20:00:00+00:00",
            }
        )

    with (latest_dir / "source_status_latest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=pipeline.DEFAULT_META_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "source_key": "ncaa",
                "source_name": "NCAA",
                "source_url": "https://example.com/search",
                "source_updated_at_raw": "2026-03-10T14:15:00Z",
                "source_updated_at_iso": "2026-03-10T14:15:00+00:00",
                "scraped_at_iso": "2026-03-10T20:00:00+00:00",
                "status": "ok",
                "error_message": "",
                "row_count": 1,
            }
        )

    def fake_parser(*, source_key: str, source_name: str, source_url: str, html: str, scraped_at_iso: str) -> ScrapeResult:
        return ScrapeResult(
            rows=[
                SourceProjectionRow(
                    source_key=source_key,
                    source_name=source_name,
                    source_url="https://www.ncaa.com/news/basketball-women/article/2026-03-09/newer-look",
                    source_updated_at_raw="2026-03-09T10:00:00Z",
                    source_updated_at_iso="2026-03-09T10:00:00+00:00",
                    team_raw="New Team",
                    seed=1,
                    is_play_in=False,
                    scraped_at_iso=scraped_at_iso,
                )
            ],
            updated_at_raw="2026-03-09T10:00:00Z",
            updated_at_iso="2026-03-09T10:00:00+00:00",
        )

    monkeypatch.setitem(pipeline.PARSERS, "fake_ncaa", fake_parser)

    paths = PipelinePaths(
        root_dir=tmp_path,
        config_dir=config_dir,
        data_dir=data_dir,
        latest_dir=latest_dir,
        snapshot_dir=snapshot_dir,
        site_dir=site_dir,
    )

    pipeline.run_scrape(paths=paths, fetcher=lambda *_args, **_kwargs: "<html></html>", enable_playwright_fallback=False)

    with (latest_dir / "source_rows_latest.csv").open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    with (latest_dir / "source_status_latest.csv").open("r", newline="", encoding="utf-8") as handle:
        meta_rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["team_raw"] == "Old Team"
    assert meta_rows[0]["source_updated_at_iso"] == "2026-03-10T14:15:00+00:00"
