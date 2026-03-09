import csv
import json

from bracket_matrix.config import PipelinePaths
from bracket_matrix import pipeline


def test_run_scrape_uses_manual_html_for_athletic_source(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    latest_dir = data_dir / "latest"
    snapshot_dir = data_dir / "snapshots"
    site_dir = tmp_path / "site"
    manual_dir = data_dir / "manual"

    for path in [config_dir, data_dir, latest_dir, snapshot_dir, site_dir, manual_dir]:
        path.mkdir(parents=True, exist_ok=True)

    article_url = "https://www.nytimes.com/athletic/7092398/2026/03/06/women-ncaa-tournament-bracket-watch-uconn-ucla/"
    article_html = """
    <html><body><article>
      <time datetime="2026-03-06T09:15:00-05:00">Mar 6, 2026</time>
      <p>No. 1 UConn</p>
      <p>No. 1 UCLA</p>
      <p>No. 2 South Carolina</p>
      <p>No. 11 Princeton / Villanova</p>
    </article></body></html>
    """
    (manual_dir / "the_athletic_latest.html").write_text(article_html, encoding="utf-8")
    (manual_dir / "the_athletic_latest_url.txt").write_text(f"{article_url}\n", encoding="utf-8")

    (config_dir / "sources.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_key": "the_athletic",
                        "source_name": "The Athletic",
                        "source_url": "https://www.nytimes.com/athletic/tag/bracketcentral/",
                        "parser": "theathletic",
                        "use_playwright_fallback": False,
                        "manual_html_path": "data/manual/the_athletic_latest.html",
                        "manual_article_url_path": "data/manual/the_athletic_latest_url.txt",
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

    def fail_fetcher(url: str, timeout_seconds: int, user_agent: str) -> str:
        raise AssertionError("network fetch should not be called when manual HTML exists")

    pipeline.run_scrape(paths=paths, fetcher=fail_fetcher, enable_playwright_fallback=False)

    with (latest_dir / "source_rows_latest.csv").open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert all(row["source_url"] == article_url for row in rows)
