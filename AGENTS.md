# Repository Guidelines

## Project Structure & Module Organization
- Core package code lives in `src/bracket_matrix/`.
- Scrapers are split by source under `src/bracket_matrix/scrapers/` (for example, `espn.py`, `herhoopstats.py`).
- Tests live in `tests/`, with HTML fixtures in `tests/fixtures/`.
- Runtime configuration is in `config/` (`sources.json`, `settings.json`).
- Data artifacts are written to `data/latest/` and timestamped history in `data/snapshots/`.
- Generated site output is `site/index.html` via the publish step.

## Build, Test, and Development Commands
- Install dependencies:
  - `python -m pip install --upgrade pip`
  - `pip install -r requirements.txt && pip install -e .`
- Install browser for fallback scraping: `python -m playwright install chromium`.
- Run commands through the CLI module:
  - `python -m bracket_matrix scrape` (collect source rows/status)
  - `python -m bracket_matrix build` (normalize + merge matrix)
  - `python -m bracket_matrix publish` (render static site)
  - `python -m bracket_matrix run-all --retention-days 365` (full pipeline + cleanup)
- Run tests: `pytest -q`.
- After making changes, run `python -m bracket_matrix publish` by default to refresh `site/index.html`.

## Coding Style & Naming Conventions
- Use Python 3.11 features and type hints where practical.
- Follow existing style: 4-space indentation, `snake_case` for functions/modules, `PascalCase` for classes.
- Keep scraper logic source-specific; put shared parsing helpers in `scrapers/common.py`.
- Prefer small, pure transformation functions for normalization/merge logic.

## Testing Guidelines
- Test framework: `pytest` (configured in `pyproject.toml` with `testpaths = ["tests"]`).
- Add tests alongside affected behavior (parsers, normalization, merge, pipeline integration).
- Name files `test_<feature>.py` and tests `test_<expected_behavior>()`.
- For parser changes, update or add fixture-driven tests in `tests/fixtures/`.

## Commit & Pull Request Guidelines
- Use concise, imperative commit messages (examples from history: `Implement bracket matrix pipeline...`, `Update bracket matrix data`).
- Keep unrelated changes in separate commits.
- Never push directly to `main`; always create/use a feature branch and open a PR.
- PRs should include: purpose, key changes, test results (`pytest -q`), and any data/schema impact.
- Include screenshots or rendered output notes when changing `publish`/HTML behavior.
- When creating/editing PR descriptions via `gh`, avoid literal `\n` escapes in `--body`; use `--body-file` (preferred) or a heredoc/ANSI-C quoted string so markdown line breaks render correctly.

## Configuration & Data Notes
- Do not hardcode source URLs; update `config/sources.json`.
- Keep alias overrides in `data/aliases.csv` and document non-obvious mappings in PR descriptions.
- Avoid deleting historical snapshots unless retention behavior is the explicit change.

## Manual Source Maintenance
- `the_athletic` may require manual HTML capture when blocked: save latest article HTML to
  `data/manual/the_athletic_latest.html`, then run `scrape`, `build`, and `publish`.
- `ncaa` currently uses a direct manual article URL in `config/sources.json` (Google discovery is
  not reliable in automation). Update the `ncaa` `source_url` to the newest NCAA article when it
  drops, then run `python -m bracket_matrix scrape`, `python -m bracket_matrix build`, and
  `python -m bracket_matrix publish`.
- For `ncaa`, expect around `68` rows after `scrape`; if not, inspect source table format drift.

## Current Pipeline Behavior Notes
- Conference mapping is static per season in `data/team_conferences.csv` and is loaded during
  `build`; it is refreshed manually via `python -m bracket_matrix refresh-conferences --season <year>`.
- When conference data is missing for a team, first fix name mapping in `data/aliases.csv`, then
  refresh conferences and rebuild artifacts.
- Site output currently splits teams into `Projected Field` and `Other Candidates`, and orders
  source columns/rows by source recency with `Latest Update` displayed as `M/D`.
