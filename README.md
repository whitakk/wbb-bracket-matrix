# wbb-bracket-matrix

Women's college basketball "bracket matrix" aggregator. This project scrapes public bracketology pages, normalizes team names, builds a merged seed matrix, renders a static web page, and stores timestamped snapshots.

## Sources (v1)
- Her Hoop Stats: <https://herhoopstats.com/bracketology/>
- ESPN: <https://www.espn.com/espn/feature/story/_/id/30423107/ncaa-women-bracketology-2026-women-college-basketball-projections>
- College Sports Madness: <https://www.collegesportsmadness.com/womens-basketball/bracketology>

## Requirements
- Python 3.11
- Dependencies in `requirements.txt`

## Install
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

If Chromium install permissions are restricted, set a local browser path first:
```bash
export PLAYWRIGHT_BROWSERS_PATH=./data/playwright-browsers
# PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH = "./data/playwright-browsers"
python -m playwright install chromium
```

## CLI
```bash
python -m bracket_matrix scrape
python -m bracket_matrix build
python -m bracket_matrix publish
python -m bracket_matrix run-all
```

Optional flags:
```bash
python -m bracket_matrix scrape --disable-playwright-fallback
python -m bracket_matrix run-all --disable-playwright-fallback --retention-days 365
```

## Data outputs
- Latest artifacts: `data/latest/`
- Snapshot history: `data/snapshots/`
- Static site output: `site/index.html`

Key files:
- `data/latest/source_rows_latest.csv`
- `data/latest/source_status_latest.csv`
- `data/latest/resolved_rows_latest.csv`
- `data/latest/matrix_latest.csv`
- `data/latest/unresolved_matches_latest.csv`

## Config
- Sources: `config/sources.json`
- Pipeline settings: `config/settings.json`
- Alias overrides: `data/aliases.csv`

## GitHub Actions
- CI tests: `.github/workflows/ci.yml`
- Scheduled publish every 4 hours (UTC): `.github/workflows/publish.yml`

The publish workflow runs the full pipeline, commits updated snapshots/latest data, and deploys `site/` to GitHub Pages.
