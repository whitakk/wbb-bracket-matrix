from __future__ import annotations

import argparse

from bracket_matrix.pipeline import run_all, run_build, run_publish, run_scrape


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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scrape":
        run_scrape(enable_playwright_fallback=not args.disable_playwright_fallback)
    elif args.command == "build":
        run_build()
    elif args.command == "publish":
        run_publish()
    elif args.command == "run-all":
        run_all(
            enable_playwright_fallback=not args.disable_playwright_fallback,
            retention_days=args.retention_days,
        )
    else:  # pragma: no cover
        parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
