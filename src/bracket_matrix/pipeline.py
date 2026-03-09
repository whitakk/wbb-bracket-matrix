from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from bracket_matrix.conferences import (
    DEFAULT_BART_SEASON,
    TEAM_CONFERENCE_FIELDNAMES,
    build_team_conference_rows_from_bart,
    fetch_bart_team_results_csv,
    load_team_conferences,
)
from bracket_matrix.config import PipelinePaths, get_default_paths, load_settings, load_sources
from bracket_matrix.io_utils import cleanup_old_csv, ensure_dirs, read_dict_csv, utc_compact_timestamp, utc_now_iso, write_dict_csv
from bracket_matrix.merge import build_matrix_rows
from bracket_matrix.normalize import is_placeholder_team, load_aliases, resolve_team_names
from bracket_matrix.render import render_index_html
from bracket_matrix.scrapers import PARSERS
from bracket_matrix.scrapers.common import fetch_html, fetch_html_playwright
from bracket_matrix.scrapers.espn import is_probably_blocked
from bracket_matrix.types import SourceMeta, SourceProjectionRow


DEFAULT_RAW_FIELDNAMES = [
    "source_key",
    "source_name",
    "source_url",
    "source_updated_at_raw",
    "source_updated_at_iso",
    "team_raw",
    "seed",
    "is_play_in",
    "scraped_at_iso",
]

DEFAULT_META_FIELDNAMES = [
    "source_key",
    "source_name",
    "source_url",
    "source_updated_at_raw",
    "source_updated_at_iso",
    "scraped_at_iso",
    "status",
    "error_message",
    "row_count",
]


def _latest_paths(paths: PipelinePaths) -> dict[str, Path]:
    return {
        "raw": paths.latest_dir / "source_rows_latest.csv",
        "meta": paths.latest_dir / "source_status_latest.csv",
        "resolved": paths.latest_dir / "resolved_rows_latest.csv",
        "matrix": paths.latest_dir / "matrix_latest.csv",
        "unresolved": paths.latest_dir / "unresolved_matches_latest.csv",
    }


def _serialize_row(row: SourceProjectionRow) -> dict[str, str | int | bool]:
    payload = row.to_dict()
    payload["seed"] = int(payload["seed"])
    payload["is_play_in"] = bool(payload["is_play_in"])
    return payload


def _parse_raw_row(row: dict[str, str]) -> SourceProjectionRow:
    return SourceProjectionRow(
        source_key=row["source_key"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        source_updated_at_raw=row.get("source_updated_at_raw", ""),
        source_updated_at_iso=row.get("source_updated_at_iso", ""),
        team_raw=row["team_raw"],
        seed=int(row["seed"]),
        is_play_in=str(row.get("is_play_in", "")).lower() in {"1", "true", "yes"},
        scraped_at_iso=row.get("scraped_at_iso", ""),
    )


def run_scrape(
    *,
    paths: PipelinePaths | None = None,
    enable_playwright_fallback: bool = True,
    fetcher: Callable[[str, int, str], str] = fetch_html,
    playwright_fetcher: Callable[[str, int], str] = fetch_html_playwright,
) -> dict[str, Path]:
    active_paths = paths or get_default_paths()
    settings = load_settings(active_paths)
    sources = load_sources(active_paths)

    ensure_dirs([active_paths.data_dir, active_paths.latest_dir, active_paths.snapshot_dir, active_paths.site_dir])

    timestamp = utc_compact_timestamp()
    scraped_at_iso = utc_now_iso()

    all_rows: list[dict[str, str | int | bool]] = []
    all_meta: list[dict[str, str | int]] = []

    for source in sources:
        source_key = source["source_key"]
        source_name = source["source_name"]
        source_url = source["source_url"]
        parser_key = source["parser"]
        parser_fn = PARSERS[parser_key]

        source_rows: list[SourceProjectionRow] = []
        updated_at_raw = ""
        updated_at_iso = ""
        status = "ok"
        error_message = ""

        try:
            manual_html_path_raw = str(source.get("manual_html_path", "") or "").strip()
            html = ""
            parse_source_url = source_url

            if manual_html_path_raw:
                manual_html_path = Path(manual_html_path_raw)
                if not manual_html_path.is_absolute():
                    manual_html_path = active_paths.root_dir / manual_html_path

                if manual_html_path.exists():
                    html = manual_html_path.read_text(encoding="utf-8")

                    manual_article_url_path_raw = str(source.get("manual_article_url_path", "") or "").strip()
                    manual_article_url = str(source.get("manual_article_url", "") or "").strip()

                    if manual_article_url_path_raw:
                        manual_article_url_path = Path(manual_article_url_path_raw)
                        if not manual_article_url_path.is_absolute():
                            manual_article_url_path = active_paths.root_dir / manual_article_url_path
                        if manual_article_url_path.exists():
                            manual_article_url = manual_article_url_path.read_text(encoding="utf-8").strip()

                    if manual_article_url:
                        parse_source_url = manual_article_url

            if not html:
                html = fetcher(
                    source_url,
                    timeout_seconds=int(settings["request_timeout_seconds"]),
                    user_agent=str(settings["user_agent"]),
                )

            result = parser_fn(
                source_key=source_key,
                source_name=source_name,
                source_url=parse_source_url,
                html=html,
                scraped_at_iso=scraped_at_iso,
            )
            source_rows = result.rows
            updated_at_raw = result.updated_at_raw
            updated_at_iso = result.updated_at_iso

            min_rows_for_fallback = int(source.get("min_rows_for_playwright_fallback", 0) or 0)
            too_few_rows = min_rows_for_fallback > 0 and len(source_rows) < min_rows_for_fallback

            should_try_playwright = (
                enable_playwright_fallback
                and bool(source.get("use_playwright_fallback", False))
                and (not source_rows or too_few_rows or (parser_key == "espn" and is_probably_blocked(html)))
            )
            if should_try_playwright:
                html_pw = playwright_fetcher(
                    source_url,
                    timeout_seconds=int(settings["request_timeout_seconds"]),
                )
                result_pw = parser_fn(
                    source_key=source_key,
                    source_name=source_name,
                    source_url=source_url,
                    html=html_pw,
                    scraped_at_iso=scraped_at_iso,
                )
                if result_pw.rows:
                    source_rows = result_pw.rows
                    updated_at_raw = result_pw.updated_at_raw
                    updated_at_iso = result_pw.updated_at_iso
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_message = str(exc)
            print(f"[scrape] {source_key} error: {error_message}")

        all_rows.extend(_serialize_row(row) for row in source_rows)
        all_meta.append(
            asdict(
                SourceMeta(
                    source_key=source_key,
                    source_name=source_name,
                    source_url=source_url,
                    source_updated_at_raw=updated_at_raw,
                    source_updated_at_iso=updated_at_iso,
                    scraped_at_iso=scraped_at_iso,
                    status=status,
                    error_message=error_message,
                    row_count=len(source_rows),
                )
            )
        )

    latest = _latest_paths(active_paths)
    write_dict_csv(latest["raw"], all_rows, fieldnames=DEFAULT_RAW_FIELDNAMES)
    write_dict_csv(latest["meta"], all_meta, fieldnames=DEFAULT_META_FIELDNAMES)

    write_dict_csv(active_paths.snapshot_dir / f"source_rows_{timestamp}.csv", all_rows, fieldnames=DEFAULT_RAW_FIELDNAMES)
    write_dict_csv(active_paths.snapshot_dir / f"source_status_{timestamp}.csv", all_meta, fieldnames=DEFAULT_META_FIELDNAMES)

    return latest


def run_build(*, paths: PipelinePaths | None = None) -> dict[str, Path]:
    active_paths = paths or get_default_paths()
    settings = load_settings(active_paths)
    latest = _latest_paths(active_paths)
    timestamp = utc_compact_timestamp()

    raw_rows = [_parse_raw_row(row) for row in read_dict_csv(latest["raw"])]
    source_meta_rows = read_dict_csv(latest["meta"])
    source_keys = [row["source_key"] for row in source_meta_rows]

    filtered_rows = [row for row in raw_rows if not is_placeholder_team(row.team_raw)]

    aliases = load_aliases(active_paths.data_dir / "aliases.csv")
    team_names = [row.team_raw for row in filtered_rows]

    resolved, unresolved = resolve_team_names(
        team_names=team_names,
        aliases=aliases,
        fuzzy_threshold=float(settings["fuzzy_threshold"]),
        fuzzy_review_threshold=float(settings["fuzzy_review_threshold"]),
        fuzzy_ambiguous_margin=float(settings["fuzzy_ambiguous_margin"]),
    )

    matrix_input_rows = [row for row in filtered_rows if row.team_raw in resolved]
    matrix_rows = build_matrix_rows(matrix_input_rows, resolved, source_keys)
    team_conferences = load_team_conferences(active_paths.data_dir / "team_conferences.csv")

    for matrix_row in matrix_rows:
        matrix_row.conference = team_conferences.get(matrix_row.canonical_slug, "")

    resolved_rows: list[dict[str, str | int | float]] = []
    for row in matrix_input_rows:
        resolution = resolved[row.team_raw]
        resolved_rows.append(
            {
                **_serialize_row(row),
                "canonical_slug": resolution.identity.canonical_slug,
                "team_display": resolution.identity.team_display,
                "ncaa_id": resolution.identity.ncaa_id,
                "espn_id": resolution.identity.espn_id,
                "conference": team_conferences.get(resolution.identity.canonical_slug, ""),
                "resolution_method": resolution.method,
                "resolution_confidence": round(resolution.confidence, 2),
            }
        )

    matrix_flat = [row.to_flat_dict(source_keys) for row in matrix_rows]
    unresolved_rows = [
        {
            "team_raw": item.team_raw,
            "normalized": item.normalized,
            "best_match_slug": item.best_match_slug,
            "best_score": item.best_score,
            "second_score": item.second_score,
            "reason": item.reason,
        }
        for item in unresolved
    ]

    resolved_fields = DEFAULT_RAW_FIELDNAMES + [
        "canonical_slug",
        "team_display",
        "ncaa_id",
        "espn_id",
        "conference",
        "resolution_method",
        "resolution_confidence",
    ]

    matrix_fields = [
        "canonical_slug",
        "team_display",
        "ncaa_id",
        "espn_id",
        "appearances",
        "avg_seed",
        "conference",
    ] + source_keys

    unresolved_fields = [
        "team_raw",
        "normalized",
        "best_match_slug",
        "best_score",
        "second_score",
        "reason",
    ]

    write_dict_csv(latest["resolved"], resolved_rows, fieldnames=resolved_fields)
    write_dict_csv(latest["matrix"], matrix_flat, fieldnames=matrix_fields)
    write_dict_csv(latest["unresolved"], unresolved_rows, fieldnames=unresolved_fields)

    write_dict_csv(active_paths.snapshot_dir / f"resolved_rows_{timestamp}.csv", resolved_rows, fieldnames=resolved_fields)
    write_dict_csv(active_paths.snapshot_dir / f"matrix_{timestamp}.csv", matrix_flat, fieldnames=matrix_fields)
    write_dict_csv(active_paths.snapshot_dir / f"unresolved_matches_{timestamp}.csv", unresolved_rows, fieldnames=unresolved_fields)

    return latest


def run_publish(*, paths: PipelinePaths | None = None) -> dict[str, Path]:
    active_paths = paths or get_default_paths()
    latest = _latest_paths(active_paths)

    matrix_rows_raw = read_dict_csv(latest["matrix"])
    source_meta_rows = read_dict_csv(latest["meta"])

    source_keys = [row["source_key"] for row in source_meta_rows]
    source_key_to_name = {row["source_key"]: row["source_name"] for row in source_meta_rows}

    matrix_rows = []
    for row in matrix_rows_raw:
        source_seeds = {
            source_key: int(row[source_key]) if row.get(source_key) else None
            for source_key in source_keys
        }
        from bracket_matrix.types import MatrixRow

        matrix_rows.append(
            MatrixRow(
                canonical_slug=row["canonical_slug"],
                team_display=row["team_display"],
                ncaa_id=row.get("ncaa_id", ""),
                espn_id=row.get("espn_id", ""),
                appearances=int(row.get("appearances", 0)),
                avg_seed=float(row.get("avg_seed", 99)),
                conference=row.get("conference", ""),
                source_seeds=source_seeds,
            )
        )

    render_index_html(
        matrix_rows=matrix_rows,
        source_meta_rows=source_meta_rows,
        source_keys=source_keys,
        source_key_to_name=source_key_to_name,
        generated_at_iso=utc_now_iso(),
        output_path=active_paths.site_dir / "index.html",
    )

    # Copy latest CSV artifacts into site output for download.
    for key in ["matrix", "resolved", "unresolved", "meta"]:
        src = latest[key]
        dst = active_paths.site_dir / src.name
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    return {"site_index": active_paths.site_dir / "index.html"}


def run_refresh_conferences(
    *,
    paths: PipelinePaths | None = None,
    season: int = DEFAULT_BART_SEASON,
) -> Path:
    active_paths = paths or get_default_paths()
    settings = load_settings(active_paths)

    csv_text = fetch_bart_team_results_csv(
        season=season,
        timeout_seconds=int(settings["request_timeout_seconds"]),
        user_agent=str(settings["user_agent"]),
    )
    rows = build_team_conference_rows_from_bart(
        csv_text,
        aliases_path=active_paths.data_dir / "aliases.csv",
    )

    output_path = active_paths.data_dir / "team_conferences.csv"
    write_dict_csv(output_path, rows, fieldnames=TEAM_CONFERENCE_FIELDNAMES)
    return output_path


def run_all(
    *,
    paths: PipelinePaths | None = None,
    enable_playwright_fallback: bool = True,
    retention_days: int | None = None,
) -> dict[str, Path]:
    active_paths = paths or get_default_paths()
    settings = load_settings(active_paths)
    sources = load_sources(active_paths)

    run_scrape(paths=active_paths, enable_playwright_fallback=enable_playwright_fallback)
    run_build(paths=active_paths)
    output = run_publish(paths=active_paths)

    has_athletic_source = any(source.get("source_key") == "the_athletic" for source in sources)
    if has_athletic_source:
        notify_email = os.getenv("GMAIL_TO", "")
        use_playwright_check = os.getenv("BRACKET_MATRIX_CHECK_ATHLETIC_USE_PLAYWRIGHT", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        try:
            from bracket_matrix.athletic_updates import check_for_new_athletic_update

            check_result = check_for_new_athletic_update(
                notify_email=notify_email,
                use_playwright=use_playwright_check,
            )
            print(
                "[athletic-update] "
                f"status={check_result['status']} "
                f"latest_url={check_result['latest_url']}"
            )
            if check_result.get("status") == "missing_manual_url":
                print(
                    "[athletic-update] manual url file missing/empty; "
                    f"set {check_result['state_file']}"
                )
            if check_result.get("status") == "updated" and not notify_email:
                print("[athletic-update] update detected but email skipped (GMAIL_TO not set)")
        except Exception as exc:  # noqa: BLE001
            print(f"[athletic-update] check failed: {exc}")

    days = retention_days if retention_days is not None else int(settings["retention_days"])
    for prefix in [
        "source_rows",
        "source_status",
        "resolved_rows",
        "matrix",
        "unresolved_matches",
    ]:
        cleanup_old_csv(active_paths.snapshot_dir, prefix=prefix, retention_days=days)

    return output
