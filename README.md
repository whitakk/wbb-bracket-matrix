# wbb-bracket-matrix

Women's college basketball "bracket matrix" aggregator. This project scrapes public bracketology pages, normalizes team names, builds a merged seed matrix, renders a static web page, and stores timestamped snapshots.

## Sources (v1)
- Her Hoop Stats: <https://herhoopstats.com/bracketology/>
- ESPN: <https://www.espn.com/espn/feature/story/_/id/30423107/ncaa-women-bracketology-2026-women-college-basketball-projections>
- College Sports Madness: <https://www.collegesportsmadness.com/womens-basketball/bracketology>
- The IX: <https://www.theixsports.com/category/the-ix-basketball-newsroom/ncaa-basketball/bracketology/>
- CBS Sports: <https://www.cbssports.com/womens-college-basketball/>
- USA Today: <https://www.usatoday.com/sports/ncaaw/ncaa-womens-basketball-tournament/>
- The Athletic: <https://www.nytimes.com/athletic/tag/bracketcentral/>

## Requirements
- Python 3.11
- Dependencies in `requirements.txt`
- Tesseract OCR installed on system PATH (required for The IX image parsing)
- Optional: `OPENAI_API_KEY` to use OpenAI vision extraction for The IX (recommended)
- Optional: `OPENAI_MODEL` (defaults to `gpt-4.1`, then falls back to `gpt-4o` and `gpt-4o-mini`)

## Install
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium
```

To enable OpenAI extraction for The IX, copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

Note: The IX currently includes a temporary source-specific correction for one known
model misread (`Illinois State` -> `Illinois`). We should revisit this with a more
robust image extraction approach.

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
python -m bracket_matrix refresh-conferences --season 2026
python -m bracket_matrix auth-login --source the_athletic
python -m bracket_matrix check-athletic-update --notify-email you@example.com
```

Optional flags:
```bash
python -m bracket_matrix scrape --disable-playwright-fallback
python -m bracket_matrix run-all --disable-playwright-fallback --retention-days 365
```

The Athletic authentication (optional, for subscriber-only pages):
```bash
# 1) Run interactive browser login once (saves to data/the_athletic_storage_state.json by default).
# Optional: use local Chrome instead of bundled Chromium.
# export BRACKET_MATRIX_PLAYWRIGHT_CHANNEL=chrome
python -m bracket_matrix auth-login --source the_athletic

# 2) Reuse that state in scrapes.
export BRACKET_MATRIX_PLAYWRIGHT_STORAGE_STATE=data/the_athletic_storage_state.json

# Optional: run Playwright in headed mode for tougher anti-bot pages.
# export BRACKET_MATRIX_PLAYWRIGHT_HEADLESS=false
python -m bracket_matrix scrape
```

The Athletic update alert check (no full scrape required):
```bash
# First run initializes the last-seen URL state file.
python -m bracket_matrix check-athletic-update

# Later runs notify only when latest article URL changes.
python -m bracket_matrix check-athletic-update --notify-email you@example.com

# Optional: fetch tag page with Playwright instead of requests.
python -m bracket_matrix check-athletic-update --use-playwright
```

`run-all` now also performs this Athletic update check automatically when `the_athletic`
is present in `config/sources.json`.

Optional env vars for `run-all` Athletic update notifications:
- `BRACKET_MATRIX_CHECK_ATHLETIC_USE_PLAYWRIGHT` (`true`/`false` for tag page fetch mode)

Gmail env vars for email notification (simple mode):
- `GMAIL_USER` (your Gmail address)
- `GMAIL_APP_PASSWORD` (Google app password)
- `GMAIL_TO` (default recipient; optional if you pass `--notify-email`)

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
- `data/team_conferences.csv`

## Config
- Sources: `config/sources.json`
- Pipeline settings: `config/settings.json`
- Alias overrides: `data/aliases.csv`

## Conference mapping
- Team conference mapping is read from the static file `data/team_conferences.csv` during `build`.
- It is not fetched automatically in `run-all` so runs stay deterministic and fast.
- Refresh it manually at season rollover with:

```bash
python -m bracket_matrix refresh-conferences --season 2026
```

If a team is missing a conference in `matrix_latest.csv`, it is usually a naming mismatch
between source team labels and Bart Torvik names. Add/adjust aliases in `data/aliases.csv`,
then rerun:

```bash
python -m bracket_matrix refresh-conferences --season 2026
python -m bracket_matrix build
python -m bracket_matrix publish
```

## Site presentation rules
- The main table is split into `Projected Field` (68 teams) and `Other Candidates`.
- `Projected Field` selection first takes one plurality winner per conference (tiebreakers:
  lower avg seed, then alphabetical), then fills remaining spots by appearances, then avg seed.
- Both sections are displayed sorted by avg seed (ascending).
- Source columns (left-to-right) and source status rows (top-to-bottom) are ordered by most
  recent `source_updated_at_iso`.
- Source `Latest Update` is shown in compact month/day format (for example, `3/9`).

## GitHub Actions
- CI tests: `.github/workflows/ci.yml`
- Scheduled publish every 4 hours (UTC): `.github/workflows/publish.yml`

The publish workflow runs the full pipeline, commits updated snapshots/latest data, and deploys `site/` to GitHub Pages.
