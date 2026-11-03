# 2026–27 provider and path audit

Checked November 2, 2026 (Eastern time) against `origin/main` at `cf32767`.
The local `init/bracketology` branch tracked a deleted remote branch, so the update
uses `codex/season-2026-27`, based on current `origin/main`.

Tournament sizing follows the [NCAA's 76-team expansion announcement](https://www.ncaa.org/news/media-center-ncaa-reveals-new-76-team-bracket-for-di-mens-and-womens-basketball-championships/).

| Provider | Live result | Action / remaining dependency |
| --- | --- | --- |
| [Her Hoop Stats](https://herhoopstats.com/bracketology/) | 2027 bracket, October 26 update; 76 field teams + 4 first-out teams | Fixed abbreviated date / Eastern time parsing, split slots, and opening-round duplicates. |
| [ESPN](https://www.espn.com/espn/feature/story/_/id/30423107/ncaa-women-bracketology-2027-women-college-basketball-projections) | 2027 bracket, October 27 update; 76 field teams + 8 out teams | HTML is a JavaScript shell. Added parser for the public JSON feed used by the page. The CDN's `2025/25_vs_bracketology` path is still current infrastructure, not the projection season. |
| NCAA bracket predictions | Configured March 10, 2026 article was still last season | Disabled until a verified 2027 article is available. Set its URL and `enabled: true` in sources.json. |
| [College Sports Madness](https://www.collegesportsmadness.com/womens-basketball/bracketology) | HTTP 200, still displays the completed 2026 tournament | Excluded by season validation; do not relabel old projections. |
| [The IX](https://www.theixsports.com/the-ix-basketball-newsroom/2026-27-bracketology-our-first-76-team-field/) | Current 76-team article dated October 28; category discovery works | Raised parser limit/prompt to 76 and removed old image-specific team rewrites. Full image extraction could not run locally: Tesseract is absent and no API key was supplied to this check. CI already installs Tesseract. |
| [CBS Sports](https://www.cbssports.com/womens-college-basketball/) | Hub responds, but no dated current bracket was parsed | Marked unavailable instead of successful with zero rows. Recheck when projections appear. |
| [USA Today](https://www.usatoday.com/sports/ncaaw/ncaa-womens-basketball-tournament/) | HTTP 402 | Access restricted; parser not verified against a current article. |
| [The Athletic](https://www.nytimes.com/athletic/tag/bracketcentral/) | Discovery selects a March 13, 2026 women's Bracket Watch; article returns HTTP 403 | Needs a current article/manual capture and subscriber access as applicable. Old saved HTML is retained, but excluded from current-season paths. |
| [Bart Torvik 2027 CSV](https://barttorvik.com/ncaaw/2027_team_results.csv) | Available; parsed rankings and refreshed conference map | Use year-specific CSV; the HTML rankings page presents browser verification. Includes new-season conference realignment. |
| [NCAA NET](https://www.ncaa.com/rankings/basketball-women/d1/ncaa-womens-basketball-net-rankings) / [WAB](https://www.ncaa.com/rankings/basketball-women/d1/wab-ranking) | Both say “Through Games Apr. 05 2026” | Excluded until their ranking dates advance into the active season. Current-season sidebar headlines do not qualify old tables. |
| NCAA confirmed auto-bids | Old URL listed 2026 conference champions | URL cleared; leave empty until a verified 2027 tracker exists. |

## Paths and behavior

- Season settings: `config/settings.json`; source URLs: `config/sources.json`.
- Active latest outputs: `data/latest/2026-27/`; old latest files and snapshots remain intact.
- Conferences: `data/team_conferences_2027.csv`; refresh with `python -m bracket_matrix refresh-conferences`.
- Manual Athletic HTML: `data/manual/2026-27/the_athletic_latest.html`.
- Athletic update-check state: `data/manual/2026-27/the_athletic_latest_url.txt`.
- Local rendered page: `site/index.html`; CSV download copies remain directly in `site/`.
- Opening round: 12 lowest-ranked automatic qualifiers and 12 lowest-ranked at-large teams,
  paired within category. Both server-rendered and interactive analytics projections select 76
  teams and reduce to 64 first-round slots. `/OR` identifies opening-round participants.
- Publishing workflow reads the season-specific status path, refreshes conferences, and has
  its four-hour schedule restored in the edited workflow. These changes have not been deployed.

## Validation

Live scrape, build, conference refresh, and local publish completed, including a run with
browser fallback enabled. HHS and ESPN supply complete current fields. Added the explicit
`S Indiana` → Southern Indiana alias from the ESPN feed; current projection names resolve
without unresolved matches. Playwright checked the rendered 76-team aggregate and all four
analytics ranking presets: each selects 76 teams with 24 opening-round participants and no
JavaScript errors. The automated tests cover stale/missing dates, the expanded field, split
HHS cells, ESPN JSON, and current-year Bart CSV parsing.
Final regression run: `93 passed`.

Windows HTTPS requests in this environment required its system certificate store. Live checks
used `truststore` in a local audit wrapper; certificate verification stayed enabled. Git used
the Windows `schannel` backend for the fetch. Neither workaround changes application TLS policy.
