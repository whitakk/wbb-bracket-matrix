from __future__ import annotations

import argparse
from pathlib import Path

from bracket_matrix.athletic_updates import check_for_new_athletic_update, default_state_file
from bracket_matrix.auth import run_auth_login
from bracket_matrix.conferences import DEFAULT_BART_SEASON
from bracket_matrix.pipeline import run_all, run_build, run_publish, run_refresh_conferences, run_scrape


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WBB bracket matrix pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape_parser = subparsers.add_parser("scrape", help="scrape source bracketology pages")
    scrape_parser.add_argument(
        "--disable-playwright-fallback",
        action="store_true",
        help="disable Playwright fallback scraping",
    )

    subparsers.add_parser("build", help="build merged matrix from latest scrape")
    subparsers.add_parser("publish", help="render site from latest merged matrix")
    refresh_conf_parser = subparsers.add_parser(
        "refresh-conferences",
        help="refresh static team conference mappings from Bart Torvik",
    )
    refresh_conf_parser.add_argument(
        "--season",
        type=int,
        default=DEFAULT_BART_SEASON,
        help="season year for Bart Torvik team results CSV",
    )

    run_all_parser = subparsers.add_parser("run-all", help="run scrape, build, publish, and retention cleanup")
    run_all_parser.add_argument(
        "--disable-playwright-fallback",
        action="store_true",
        help="disable Playwright fallback scraping",
    )
    run_all_parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="snapshot retention window in days",
    )

    auth_parser = subparsers.add_parser(
        "auth-login",
        help="open browser login flow and save Playwright storage state",
    )
    auth_parser.add_argument(
        "--source",
        choices=["the_athletic"],
        default="the_athletic",
        help="source key to authenticate",
    )
    auth_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional output path for Playwright storage state JSON",
    )
    auth_parser.add_argument(
        "--url",
        default=None,
        help="optional URL override for login entry page",
    )

    check_athletic_parser = subparsers.add_parser(
        "check-athletic-update",
        help="check The Athletic tag page and notify on new Women's Bracket Watch article",
    )
    check_athletic_parser.add_argument(
        "--notify-email",
        default="",
        help="email address to notify when a new article is detected",
    )
    check_athletic_parser.add_argument(
        "--state-file",
        type=Path,
        default=default_state_file(),
        help="path to manual in-use Athletic article URL file",
    )
    check_athletic_parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="use Playwright to fetch the tag page",
    )

    return parser


def main() -> None:
    _load_dotenv_if_available()

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scrape":
        run_scrape(enable_playwright_fallback=not args.disable_playwright_fallback)
    elif args.command == "build":
        run_build()
    elif args.command == "publish":
        run_publish()
    elif args.command == "refresh-conferences":
        run_refresh_conferences(season=args.season)
    elif args.command == "run-all":
        run_all(
            enable_playwright_fallback=not args.disable_playwright_fallback,
            retention_days=args.retention_days,
        )
    elif args.command == "auth-login":
        output_path = run_auth_login(source_key=args.source, output_path=args.output, url=args.url)
        print(f"Saved auth state to: {output_path}")
        print(f"export BRACKET_MATRIX_PLAYWRIGHT_STORAGE_STATE={output_path}")
    elif args.command == "check-athletic-update":
        result = check_for_new_athletic_update(
            state_file=args.state_file,
            notify_email=args.notify_email,
            use_playwright=args.use_playwright,
        )
        print(f"Status: {result['status']}")
        print(f"Latest URL: {result['latest_url']}")
        if result["previous_url"]:
            print(f"Previous URL: {result['previous_url']}")
        print(f"State file: {result['state_file']}")
    else:  # pragma: no cover
        parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
