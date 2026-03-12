from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from bracket_matrix.types import MatrixRow, SeedValue


def _format_seed(seed: SeedValue | None) -> str:
    if seed is None:
        return ""
    if isinstance(seed, int):
        return str(int(seed))
    return seed


def _format_avg_seed(avg_seed: float) -> str:
    if avg_seed >= 99:
        return "na"
    rounded = round(avg_seed, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _abbrev_source_label(source_name: str, max_len: int = 6) -> str:
    cleaned = " ".join(source_name.split())
    if cleaned.lower() == "cbs sports":
        return "CBS"
    if cleaned.lower() == "usa today":
        return "USAT"
    if cleaned.lower() == "the athletic":
        return "ATH"
    if len(cleaned) <= max_len:
        return cleaned

    words = [token for token in cleaned.replace("-", " ").split() if token]
    initials = "".join(token[0] for token in words if token[0].isalnum()).upper()
    if 2 <= len(initials) <= max_len:
        return initials

    compact = "".join(ch for ch in cleaned if ch.isalnum())
    if len(compact) <= max_len:
        return compact
    return compact[:max_len].upper()


def _parse_source_updated_at_iso(row: dict[str, str]) -> datetime | None:
    updated_iso = (row.get("source_updated_at_iso") or "").strip()
    if not updated_iso:
        return None
    try:
        return datetime.fromisoformat(updated_iso)
    except ValueError:
        return None


def _order_source_keys_by_recency(source_keys: list[str], source_meta_lookup: dict[str, dict[str, str]]) -> list[str]:
    def _sort_key(source_key: str) -> tuple[int, datetime, str]:
        row = source_meta_lookup.get(source_key, {})
        parsed = _parse_source_updated_at_iso(row)
        if parsed is None:
            return (0, datetime.min, source_key)
        return (1, parsed, source_key)

    ordered = sorted(source_keys, key=_sort_key, reverse=True)
    return ordered


def _format_source_update_date(row: dict[str, str]) -> str:
    parsed = _parse_source_updated_at_iso(row)
    if parsed is not None:
        return f"{parsed.month}/{parsed.day}"
    return ""


def _format_bracket_share(appearances: int, source_count: int) -> str:
    if source_count <= 0:
        return "0%"
    return f"{(appearances / source_count) * 100:.0f}%"


def _format_out_share(row: MatrixRow, marker: str, source_count: int) -> str:
    if source_count <= 0:
        return "0%"
    out_mentions = _count_out_mentions(row, marker)
    return f"{(out_mentions / source_count) * 100:.0f}%"


def _bracket_share_heat_class(appearances: int, source_count: int) -> str:
    if source_count <= 0:
        return "share-0"
    if appearances == source_count:
        return "share-5"
    percent = (appearances / source_count) * 100
    if percent >= 85:
        return "share-4"
    if percent >= 70:
        return "share-3"
    if percent >= 50:
        return "share-2"
    if percent >= 30:
        return "share-1"
    return "share-0"


def _format_generated_at_et(generated_at_iso: str) -> str:
    try:
        generated_at = datetime.fromisoformat(generated_at_iso)
    except ValueError:
        return generated_at_iso

    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=ZoneInfo("UTC"))
    generated_at_et = generated_at.astimezone(ZoneInfo("America/New_York"))
    return f"{generated_at_et:%m/%d %H:%M} ET"


def _parse_rank_value(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _format_ebs_score(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _json_for_script(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")


def _seed_extremes(row: MatrixRow) -> tuple[str, str]:
    seeded_entries = [seed for seed in row.source_seeds.values() if isinstance(seed, int)]
    if not seeded_entries:
        return "na", "na"
    return str(min(seeded_entries)), str(max(seeded_entries))


def _build_ebs_rankings(
    analytics_rows: list[dict[str, str]],
    matrix_rows: list[MatrixRow],
) -> list[dict[str, str | float | int]]:
    _ = matrix_rows

    ranking_rows: list[dict[str, str | float | int]] = []
    for row in analytics_rows:
        bart_rank = _parse_rank_value(row.get("bart_rank", ""))
        wab_rank = _parse_rank_value(row.get("wab_rank", ""))
        net_rank = _parse_rank_value(row.get("net_rank", ""))
        if bart_rank is None or wab_rank is None or net_rank is None:
            continue

        canonical_slug = row.get("canonical_slug", "").strip()
        team_display = row.get("team_display", "").strip()
        if not canonical_slug or not team_display:
            continue

        conference = row.get("bart_conference", "").strip() or row.get("conference", "").strip()
        ebs_score = (bart_rank + wab_rank) / 2
        ranking_rows.append(
            {
                "canonical_slug": canonical_slug,
                "team_display": team_display,
                "conference": conference,
                "bart_rank": bart_rank,
                "wab_rank": wab_rank,
                "net_rank": net_rank,
                "ebs_score": ebs_score,
            }
        )

    ranking_rows.sort(
        key=lambda item: (
            float(item["ebs_score"]),
            int(item["wab_rank"]),
            int(item["bart_rank"]),
            str(item["team_display"]).lower(),
        )
    )
    for index, item in enumerate(ranking_rows, start=1):
        item["ebs_rank"] = index
    return ranking_rows


def _split_ebs_projected_and_bubble(
    ebs_rankings: list[dict[str, str | float | int]],
    forced_autobid_slugs: set[str] | None = None,
    field_size: int = 68,
    bubble_size: int = 16,
) -> tuple[list[dict[str, str | float | int]], list[dict[str, str | float | int]], set[str]]:
    forced_slugs = forced_autobid_slugs or set()
    by_conference: dict[str, list[dict[str, str | float | int]]] = {}
    for row in ebs_rankings:
        conference = str(row.get("conference", "")).strip()
        if not conference:
            continue
        by_conference.setdefault(conference, []).append(row)

    autobids: list[dict[str, str | float | int]] = []
    autobid_slugs: set[str] = set()
    for conference in sorted(by_conference):
        conference_rows = by_conference[conference]
        forced_candidates = [
            item for item in conference_rows if str(item.get("canonical_slug", "")) in forced_slugs
        ]
        if forced_candidates:
            winner = min(
                forced_candidates,
                key=lambda item: (
                    float(item["ebs_score"]),
                    int(item["wab_rank"]),
                    int(item["bart_rank"]),
                    str(item["team_display"]).lower(),
                ),
            )
        else:
            winner = min(
                conference_rows,
                key=lambda item: (
                    float(item["ebs_score"]),
                    int(item["wab_rank"]),
                    int(item["bart_rank"]),
                    str(item["team_display"]).lower(),
                ),
            )
        autobids.append(winner)
        autobid_slugs.add(str(winner["canonical_slug"]))

    remaining = [row for row in ebs_rankings if str(row["canonical_slug"]) not in autobid_slugs]
    projected = autobids[:field_size]
    projected.extend(remaining[: max(0, field_size - len(projected))])

    projected_slugs = {str(row["canonical_slug"]) for row in projected}
    non_projected = [row for row in ebs_rankings if str(row["canonical_slug"]) not in projected_slugs]
    bubble = non_projected[:bubble_size]

    projected.sort(
        key=lambda item: (
            float(item["ebs_score"]),
            int(item["wab_rank"]),
            int(item["bart_rank"]),
            str(item["team_display"]).lower(),
        )
    )
    return projected, bubble, autobid_slugs


def _render_analytics_ebs_html(
    analytics_rows: list[dict[str, str]],
    matrix_rows: list[MatrixRow],
    forced_autobid_slugs: set[str] | None = None,
) -> str:
    ebs_rankings = _build_ebs_rankings(analytics_rows, matrix_rows)
    if not ebs_rankings:
        return """
      <div class=\"card\" style=\"margin-top:14px;\">
        <h2>EBS Projection</h2>
        <p class=\"section-note\">No analytics data available.</p>
      </div>
        """

    projected, bubble, autobid_slugs = _split_ebs_projected_and_bubble(
        ebs_rankings,
        forced_autobid_slugs=forced_autobid_slugs,
    )
    projected_matrix_rows = [
        MatrixRow(
            canonical_slug=str(row["canonical_slug"]),
            team_display=str(row["team_display"]),
            ncaa_id="",
            espn_id="",
            appearances=0,
            avg_seed=float(row["ebs_score"]),
            conference=str(row.get("conference", "")),
            source_seeds={},
        )
        for row in projected
    ]
    projected_seeds = _projected_seed_numbers(projected_matrix_rows, autobid_slugs)

    projected_rows_html = ""
    for index, row in enumerate(projected):
        team_display = escape(str(row["team_display"]))
        if str(row["canonical_slug"]) in autobid_slugs:
            team_display = f"<strong>{team_display}</strong>"
        projected_rows_html += (
            "<tr>"
            f"<td>{projected_seeds[index]}</td>"
            f"<td>{team_display}</td>"
            f"<td>{escape(str(row.get('conference', '')))}</td>"
            f"<td>{_format_ebs_score(float(row['ebs_score']))}</td>"
            "</tr>"
        )

    bubble_rows_html = ""
    for index, row in enumerate(bubble, start=1):
        bubble_rows_html += (
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(str(row['team_display']))}</td>"
            f"<td>{escape(str(row.get('conference', '')))}</td>"
            f"<td>{_format_ebs_score(float(row['ebs_score']))}</td>"
            "</tr>"
        )

    client_rows = [
        {
            "canonical_slug": str(row["canonical_slug"]),
            "team_display": str(row["team_display"]),
            "conference": str(row.get("conference", "")),
            "wab_rank": int(row["wab_rank"]),
            "bart_rank": int(row["bart_rank"]),
            "net_rank": int(row["net_rank"]),
        }
        for row in ebs_rankings
    ]
    analytics_payload = _json_for_script(
        {
            "rows": client_rows,
            "forced_autobid_slugs": sorted(forced_autobid_slugs or set()),
            "field_size": 68,
            "bubble_size": 16,
        }
    )

    return f"""
      <div class=\"card\" style=\"margin-top:14px;\">
        <div class=\"controls analytics-controls\">
          <label for=\"analytics-preset\">Ranking Formula:</label>
          <select id=\"analytics-preset\">
            <option value=\"ebs\" selected>EBS</option>
            <option value=\"wab\">WAB</option>
            <option value=\"bart\">T-Rank</option>
            <option value=\"net\">NET</option>
            <option value=\"custom\">Custom</option>
          </select>
          <div id=\"analytics-custom-controls\" style=\"display:none;\">
            <label for=\"analytics-weight-wab\">WAB %</label>
            <input id=\"analytics-weight-wab\" type=\"number\" min=\"0\" max=\"100\" step=\"1\" value=\"50\" />
            <label for=\"analytics-weight-bart\">T-Rank %</label>
            <input id=\"analytics-weight-bart\" type=\"number\" min=\"0\" max=\"100\" step=\"1\" value=\"50\" />
            <label for=\"analytics-weight-net\">NET %</label>
            <input id=\"analytics-weight-net\" type=\"number\" min=\"0\" max=\"100\" step=\"1\" value=\"0\" />
          </div>
          <span id=\"analytics-weight-status\" class=\"section-note\" style=\"margin:0;\"></span>
        </div>
        <p class=\"section-note\" id=\"analytics-formula-note\"><a href=\"https://www.ncaa.com/rankings/basketball-women/d1/wab-ranking\" target=\"_blank\" rel=\"noopener noreferrer\">WAB</a> = Wins Above Bubble. <a href=\"https://barttorvik.com/ncaaw/#\" target=\"_blank\" rel=\"noopener noreferrer\">T-Rank</a> = Bart Torvik's predictive rating. <a href=\"https://kaleidoscopemind.substack.com/i/142652355/one-metric-to-rule-them-all\" target=\"_blank\" rel=\"noopener noreferrer\">EBS (Easy Bubble Solver)</a> = 50% WAB + 50% T-Rank.</p>
        <h2>Projected Field</h2>
        <table class=\"matrix analytics-table\">
          <colgroup>
            <col class=\"rank-col\" />
            <col class=\"team-col\" />
            <col class=\"conf-col\" />
            <col class=\"avg-col\" />
            <col class=\"analytics-component-col\" />
            <col class=\"analytics-component-col\" />
            <col class=\"analytics-component-col\" />
          </colgroup>
          <thead>
            <tr>
              <th>Seed</th>
              <th>Team</th>
              <th>Conf</th>
              <th class=\"analytics-score-header\">EBS Score</th>
              <th class=\"analytics-component-header\" data-component-col=\"wab\" style=\"display:none;\">WAB</th>
              <th class=\"analytics-component-header\" data-component-col=\"bart\" style=\"display:none;\">T-Rank</th>
              <th class=\"analytics-component-header\" data-component-col=\"net\" style=\"display:none;\">NET</th>
            </tr>
          </thead>
          <tbody id=\"analytics-projected-body\">
            {projected_rows_html}
          </tbody>
        </table>
        <p class=\"section-note\" id=\"analytics-autobids-note\">Autobids in bold.</p>

        <hr class=\"divider\" />
        <h2>Bubble Candidates</h2>
        <table class=\"matrix analytics-table\">
          <colgroup>
            <col class=\"rank-col\" />
            <col class=\"team-col\" />
            <col class=\"conf-col\" />
            <col class=\"avg-col\" />
            <col class=\"analytics-component-col\" />
            <col class=\"analytics-component-col\" />
            <col class=\"analytics-component-col\" />
          </colgroup>
          <thead>
            <tr>
              <th>Next Out</th>
              <th>Team</th>
              <th>Conf</th>
              <th class=\"analytics-score-header\">EBS Score</th>
              <th class=\"analytics-component-header\" data-component-col=\"wab\" style=\"display:none;\">WAB</th>
              <th class=\"analytics-component-header\" data-component-col=\"bart\" style=\"display:none;\">T-Rank</th>
              <th class=\"analytics-component-header\" data-component-col=\"net\" style=\"display:none;\">NET</th>
            </tr>
          </thead>
          <tbody id=\"analytics-bubble-body\">
            {bubble_rows_html}
          </tbody>
        </table>
        <script id=\"analytics-data\" type=\"application/json\">{analytics_payload}</script>
      </div>
    """


def _best_inclusion_recency_rank(row: MatrixRow, ordered_source_keys: list[str]) -> int:
    for recency_rank, source_key in enumerate(ordered_source_keys):
        if isinstance(row.source_seeds.get(source_key), int):
            return recency_rank
    return len(ordered_source_keys)


def _count_out_mentions(row: MatrixRow, marker: str) -> int:
    return sum(1 for seed in row.source_seeds.values() if seed == marker)


def _has_out_marker(row: MatrixRow) -> bool:
    return any(seed in {"FFO", "NFO"} for seed in row.source_seeds.values())


def split_other_candidates(other_candidates: list[MatrixRow]) -> tuple[list[MatrixRow], list[MatrixRow]]:
    bubble_candidates = [row for row in other_candidates if _has_out_marker(row)]
    auto_bid_candidates = [row for row in other_candidates if not _has_out_marker(row)]

    bubble_candidates.sort(
        key=lambda item: (
            -item.appearances,
            -_count_out_mentions(item, "FFO"),
            -_count_out_mentions(item, "NFO"),
            item.avg_seed,
            item.team_display.lower(),
        )
    )
    auto_bid_candidates.sort(key=lambda item: (item.avg_seed, item.team_display.lower()))
    return bubble_candidates, auto_bid_candidates


def split_projected_field(
    matrix_rows: list[MatrixRow],
    source_keys_by_recency: list[str] | None = None,
    forced_autobid_slugs: set[str] | None = None,
    field_size: int = 68,
) -> tuple[list[MatrixRow], list[MatrixRow]]:
    ordered_source_keys = source_keys_by_recency or []
    forced_slugs = forced_autobid_slugs or set()
    eligible_rows = [row for row in matrix_rows if row.appearances > 0]

    def _inclusion_sort_key(item: MatrixRow) -> tuple[int, int, float, str]:
        return (
            -item.appearances,
            _best_inclusion_recency_rank(item, ordered_source_keys),
            item.avg_seed,
            item.team_display.lower(),
        )

    conference_winners: list[MatrixRow] = []
    winner_slugs: set[str] = set()

    rows_by_conference: dict[str, list[MatrixRow]] = {}
    for row in eligible_rows:
        conference = row.conference.strip()
        if not conference:
            continue
        rows_by_conference.setdefault(conference, []).append(row)

    for conference in sorted(rows_by_conference):
        candidates = rows_by_conference[conference]
        forced_candidates = [row for row in candidates if row.canonical_slug in forced_slugs]
        if forced_candidates:
            winner = min(forced_candidates, key=_inclusion_sort_key)
        else:
            winner = min(candidates, key=_inclusion_sort_key)
        conference_winners.append(winner)
        winner_slugs.add(winner.canonical_slug)

    remaining = [row for row in eligible_rows if row.canonical_slug not in winner_slugs]
    remaining.sort(key=_inclusion_sort_key)

    projected = conference_winners[:field_size]
    remaining_slots = max(0, field_size - len(projected))
    projected.extend(remaining[:remaining_slots])

    projected_slugs = {row.canonical_slug for row in projected}
    other_candidates = [row for row in matrix_rows if row.canonical_slug not in projected_slugs]

    projected.sort(key=lambda item: (item.avg_seed, item.team_display.lower()))
    other_candidates.sort(key=lambda item: (item.avg_seed, item.team_display.lower()))
    return projected, other_candidates


def _autobid_winner_slugs(
    matrix_rows: list[MatrixRow],
    source_keys_by_recency: list[str] | None = None,
    forced_autobid_slugs: set[str] | None = None,
) -> set[str]:
    ordered_source_keys = source_keys_by_recency or []
    forced_slugs = forced_autobid_slugs or set()
    eligible_rows = [row for row in matrix_rows if row.appearances > 0]

    def _inclusion_sort_key(item: MatrixRow) -> tuple[int, int, float, str]:
        return (
            -item.appearances,
            _best_inclusion_recency_rank(item, ordered_source_keys),
            item.avg_seed,
            item.team_display.lower(),
        )

    rows_by_conference: dict[str, list[MatrixRow]] = {}
    for row in eligible_rows:
        conference = row.conference.strip()
        if not conference:
            continue
        rows_by_conference.setdefault(conference, []).append(row)

    winner_slugs: set[str] = set()
    for conference in sorted(rows_by_conference):
        candidates = rows_by_conference[conference]
        forced_candidates = [row for row in candidates if row.canonical_slug in forced_slugs]
        if forced_candidates:
            winner = min(forced_candidates, key=_inclusion_sort_key)
        else:
            winner = min(candidates, key=_inclusion_sort_key)
        winner_slugs.add(winner.canonical_slug)
    return winner_slugs


def _projected_seed_numbers(projected_field: list[MatrixRow], autobid_slugs: set[str]) -> list[int | str]:
    if not projected_field:
        return []

    non_autobid_indices = [
        idx for idx, row in enumerate(projected_field) if row.canonical_slug not in autobid_slugs
    ]
    last_four_non_autobid = non_autobid_indices[-4:]
    special_pairs: list[tuple[int, int]] = []
    if len(last_four_non_autobid) == 4:
        special_pairs = [
            (last_four_non_autobid[0], last_four_non_autobid[1]),
            (last_four_non_autobid[2], last_four_non_autobid[3]),
        ]

    pair_starts = {first: second for first, second in special_pairs}
    pair_seconds = {second for _, second in special_pairs}

    seeds: list[int] = [1] * len(projected_field)
    effective_counter = 0
    index = 0
    while index < len(projected_field):
        if index in pair_starts:
            seed = min(16, (effective_counter // 4) + 1)
            second = pair_starts[index]
            seeds[index] = seed
            seeds[second] = seed
            effective_counter += 1
            index += 1
        elif index in pair_seconds:
            index += 1
        else:
            seed = min(16, (effective_counter // 4) + 1)
            seeds[index] = seed
            effective_counter += 1
            index += 1

    for idx in range(max(0, len(projected_field) - 6), len(projected_field)):
        seeds[idx] = 16

    ff_indices: set[int] = set(last_four_non_autobid)
    sixteen_indices = [idx for idx, seed in enumerate(seeds) if seed == 16]
    ff_indices.update(sixteen_indices[-4:])

    display_seeds: list[int | str] = []
    for idx, seed in enumerate(seeds):
        if idx in ff_indices:
            display_seeds.append(f"{seed}/FF")
        else:
            display_seeds.append(seed)
    return display_seeds


def _source_updated_date_iso(row: dict[str, str]) -> str | None:
    parsed = _parse_source_updated_at_iso(row)
    if parsed is None:
        return None
    return parsed.date().isoformat()


def _build_date_filter_options(
    ordered_source_keys: list[str], source_meta_lookup: dict[str, dict[str, str]]
) -> list[str]:
    date_counts: dict[str, int] = {}
    for source_key in ordered_source_keys:
        row = source_meta_lookup.get(source_key, {})
        updated_date = _source_updated_date_iso(row)
        if not updated_date:
            continue
        date_counts[updated_date] = date_counts.get(updated_date, 0) + 1

    options = sorted(date_counts)
    if len(options) > 1 and date_counts.get(options[-1], 0) == 1:
        options = options[:-1]
    return options


def _source_keys_since_date(
    ordered_source_keys: list[str],
    source_meta_lookup: dict[str, dict[str, str]],
    threshold_date_iso: str,
) -> list[str]:
    included: list[str] = []
    for source_key in ordered_source_keys:
        row = source_meta_lookup.get(source_key, {})
        updated_date = _source_updated_date_iso(row)
        if not updated_date:
            continue
        if updated_date >= threshold_date_iso:
            included.append(source_key)
    return included


def _format_filter_date_label(date_iso: str) -> str:
    year, month, day = date_iso.split("-")
    _ = year
    return f"{int(month)}/{int(day)}"


def _filter_matrix_rows_for_sources(matrix_rows: list[MatrixRow], source_keys: list[str]) -> list[MatrixRow]:
    filtered_rows: list[MatrixRow] = []
    for row in matrix_rows:
        filtered_source_seeds: dict[str, SeedValue | None] = {}
        included_int_seeds: list[int] = []
        for source_key in source_keys:
            seed = row.source_seeds.get(source_key)
            if seed is None:
                continue
            filtered_source_seeds[source_key] = seed
            if isinstance(seed, int):
                included_int_seeds.append(seed)

        appearances = len(included_int_seeds)
        avg_seed = 99.0
        if included_int_seeds:
            avg_seed = sum(included_int_seeds) / appearances

        filtered_rows.append(
            MatrixRow(
                canonical_slug=row.canonical_slug,
                team_display=row.team_display,
                ncaa_id=row.ncaa_id,
                espn_id=row.espn_id,
                appearances=appearances,
                avg_seed=avg_seed,
                conference=row.conference,
                source_seeds=filtered_source_seeds,
            )
        )
    return filtered_rows


def _render_matrix_sections_html(
    matrix_rows: list[MatrixRow],
    ordered_source_keys: list[str],
    forced_aggregate_autobid_slugs: set[str] | None = None,
) -> str:
    source_count = len(ordered_source_keys)
    projected_field, other_candidates = split_projected_field(
        matrix_rows,
        source_keys_by_recency=ordered_source_keys,
        forced_autobid_slugs=forced_aggregate_autobid_slugs,
    )
    autobid_slugs = _autobid_winner_slugs(
        matrix_rows,
        source_keys_by_recency=ordered_source_keys,
        forced_autobid_slugs=forced_aggregate_autobid_slugs,
    )
    projected_seeds = _projected_seed_numbers(projected_field, autobid_slugs)
    bubble_candidates, auto_bid_candidates = split_other_candidates(other_candidates)

    projected_rows_html = ""
    for idx, row in enumerate(projected_field):
        bracket_share = _format_bracket_share(row.appearances, source_count)
        bracket_share_class = _bracket_share_heat_class(row.appearances, source_count)
        highest_seed, lowest_seed = _seed_extremes(row)
        team_display = escape(row.team_display)
        if row.canonical_slug in autobid_slugs:
            team_display = f"<strong>{team_display}</strong>"
        projected_rows_html += (
            "<tr>"
            f"<td>{projected_seeds[idx]}</td>"
            f"<td>{team_display}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{_format_avg_seed(row.avg_seed)}</td>"
            f"<td class=\"bracket-share {bracket_share_class}\">{bracket_share}</td>"
            f"<td>{highest_seed}</td>"
            f"<td>{lowest_seed}</td>"
            "</tr>"
        )

    bubble_rows_html = ""
    for idx, row in enumerate(bubble_candidates, start=1):
        bracket_share = _format_bracket_share(row.appearances, source_count)
        bracket_share_class = _bracket_share_heat_class(row.appearances, source_count)
        ffo_share = _format_out_share(row, "FFO", source_count)
        nfo_share = _format_out_share(row, "NFO", source_count)
        bubble_rows_html += (
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(row.team_display)}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{_format_avg_seed(row.avg_seed)}</td>"
            f"<td class=\"bracket-share {bracket_share_class}\">{bracket_share}</td>"
            f"<td>{ffo_share}</td>"
            f"<td>{nfo_share}</td>"
            "</tr>"
        )

    auto_bid_rows_html = ""
    for idx, row in enumerate(auto_bid_candidates, start=1):
        bracket_share = _format_bracket_share(row.appearances, source_count)
        bracket_share_class = _bracket_share_heat_class(row.appearances, source_count)
        highest_seed, lowest_seed = _seed_extremes(row)
        auto_bid_rows_html += (
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(row.team_display)}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{_format_avg_seed(row.avg_seed)}</td>"
            f"<td class=\"bracket-share {bracket_share_class}\">{bracket_share}</td>"
            f"<td>{highest_seed}</td>"
            f"<td>{lowest_seed}</td>"
            "</tr>"
        )

    return f"""
    <div class=\"card\" style=\"margin-top:14px;\">
      <h2>Projected Field</h2>
      <table class=\"matrix\">
        <colgroup>
          <col class=\"rank-col\" />
          <col class=\"team-col\" />
          <col class=\"conf-col\" />
          <col class=\"avg-col\" />
          <col class=\"seed-range-col\" />
          <col class=\"seed-range-col\" />
          <col class=\"app-col\" />
        </colgroup>
        <thead>
          <tr>
            <th>Seed</th>
            <th>Team</th>
            <th>Conf</th>
            <th>Avg Seed</th>
            <th>% Brackets</th>
            <th>High</th>
            <th>Low</th>
          </tr>
        </thead>
        <tbody>
          {projected_rows_html}
        </tbody>
      </table>
      <p class=\"section-note\">Autobids in bold.</p>

      <hr class=\"divider\" />
      <h2>Bubble Candidates</h2>
      <p class=\"section-note\">Note: not all brackets publish first four out / next four out.</p>
      <table class=\"matrix\">
        <colgroup>
          <col class=\"rank-col\" />
          <col class=\"team-col\" />
          <col class=\"conf-col\" />
          <col class=\"avg-col\" />
          <col class=\"app-col\" />
          <col class=\"app-col\" />
          <col class=\"app-col\" />
        </colgroup>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th>Conf</th>
            <th>Avg Seed</th>
            <th>% Brackets</th>
            <th>% F4O</th>
            <th>% N4O</th>
          </tr>
        </thead>
        <tbody>
          {bubble_rows_html}
        </tbody>
      </table>

      <hr class=\"divider\" />
      <h2>Auto-Bid Candidates</h2>
      <table class=\"matrix\">
        <colgroup>
          <col class=\"rank-col\" />
          <col class=\"team-col\" />
          <col class=\"conf-col\" />
          <col class=\"avg-col\" />
          <col class=\"seed-range-col\" />
          <col class=\"seed-range-col\" />
          <col class=\"app-col\" />
        </colgroup>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th>Conf</th>
            <th>Avg Seed</th>
            <th>% Brackets</th>
            <th>High</th>
            <th>Low</th>
          </tr>
        </thead>
        <tbody>
          {auto_bid_rows_html}
        </tbody>
      </table>
    </div>
    """


def _render_source_table_html(
    ordered_source_keys: list[str],
    source_meta_lookup: dict[str, dict[str, str]],
    source_key_to_name: dict[str, str],
) -> str:
    source_header_html = ""
    for source_key in ordered_source_keys:
        row = source_meta_lookup.get(source_key, {})
        source_name = escape(row.get("source_name") or source_key_to_name.get(source_key, source_key))
        source_url = escape(row.get("source_url", ""))
        updated = escape(_format_source_update_date(row))
        status = escape(row.get("status", "unknown"))
        source_header_html += (
            f"<tr><td><a href=\"{source_url}\" target=\"_blank\" rel=\"noopener noreferrer\">{source_name}</a></td>"
            f"<td>{updated}</td><td>{status}</td></tr>"
        )

    return f"""
    <div class=\"card\" style=\"margin-top:14px;\">
      <table class=\"sources\">
        <thead>
          <tr><th>Source</th><th>Latest Update</th><th>Status</th></tr>
        </thead>
        <tbody>
          {source_header_html}
        </tbody>
      </table>
    </div>
    """


def render_index_html(
    *,
    matrix_rows: list[MatrixRow],
    source_meta_rows: list[dict[str, str]],
    source_keys: list[str],
    source_key_to_name: dict[str, str],
    generated_at_iso: str,
    analytics_rows: list[dict[str, str]] | None = None,
    forced_aggregate_autobid_slugs: set[str] | None = None,
    forced_ebs_autobid_slugs: set[str] | None = None,
    output_path: Path,
) -> None:
    source_meta_lookup = {row["source_key"]: row for row in source_meta_rows}
    ordered_source_keys = _order_source_keys_by_recency(source_keys, source_meta_lookup)

    date_filter_options = _build_date_filter_options(ordered_source_keys, source_meta_lookup)
    if date_filter_options:
        default_threshold = date_filter_options[0]
    else:
        default_threshold = "all"

    views_html = ""
    if date_filter_options:
        for threshold in date_filter_options:
            filtered_source_keys = _source_keys_since_date(
                ordered_source_keys,
                source_meta_lookup,
                threshold,
            )
            filtered_matrix_rows = _filter_matrix_rows_for_sources(matrix_rows, filtered_source_keys)
            matrix_sections_html = _render_matrix_sections_html(
                filtered_matrix_rows,
                filtered_source_keys,
                forced_aggregate_autobid_slugs=forced_aggregate_autobid_slugs,
            )
            source_table_html = _render_source_table_html(
                filtered_source_keys,
                source_meta_lookup,
                source_key_to_name,
            )
            views_html += (
                f"<section data-filter-view=\"{escape(threshold)}\""
                f" style=\"display:{'block' if threshold == default_threshold else 'none'};\">"
                f"{matrix_sections_html}{source_table_html}</section>"
            )
    else:
        matrix_sections_html = _render_matrix_sections_html(
            matrix_rows,
            ordered_source_keys,
            forced_aggregate_autobid_slugs=forced_aggregate_autobid_slugs,
        )
        source_table_html = _render_source_table_html(
            ordered_source_keys,
            source_meta_lookup,
            source_key_to_name,
        )
        views_html = f"<section data-filter-view=\"all\">{matrix_sections_html}{source_table_html}</section>"

    filter_controls_html = ""
    if date_filter_options:
        option_tags = ""
        for threshold in date_filter_options:
            selected_attr = " selected" if threshold == default_threshold else ""
            option_tags += (
                f"<option value=\"{escape(threshold)}\"{selected_attr}>"
                f"{escape(_format_filter_date_label(threshold))}</option>"
            )
        filter_controls_html = f"""
    <div class=\"card controls\" style=\"margin-top:14px;\">
      <label for=\"source-date-filter\">Show brackets updated since:</label>
      <select id=\"source-date-filter\">{option_tags}</select>
    </div>
        """

    analytics_tab_html = _render_analytics_ebs_html(
        analytics_rows or [],
        matrix_rows,
        forced_autobid_slugs=forced_ebs_autobid_slugs,
    )

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>WBB Aggregate Bracketology</title>
  <style>
    :root {{
      --bg: #f5f7f2;
      --paper: #ffffff;
      --ink: #1f2a1d;
      --muted: #5f6b5d;
      --line: #ced6c9;
      --accent: #2f5d3a;
      --sticky-header-top: 0px;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Source Sans 3", "Segoe UI", sans-serif; background: radial-gradient(circle at top right, #e9f2e6, var(--bg)); color: var(--ink); }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 2rem; letter-spacing: 0.02em; }}
    h2 {{ margin: 18px 0 10px; font-size: 1.2rem; letter-spacing: 0.01em; }}
    .meta {{ color: var(--muted); margin: 0 0 16px; }}
    .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.05); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    th {{ background: #eef3ea; font-weight: 700; }}
    thead th {{ position: sticky; top: var(--sticky-header-top); z-index: 2; }}
    .matrix tbody tr:nth-child(odd) {{ background: #fbfdf9; }}
    .matrix tbody tr:hover {{ background: #f0f6eb; }}
    td:nth-child(2), th:nth-child(2) {{ text-align: left; min-width: 200px; }}
    .matrix:not(.analytics-table) td:nth-child(4), .matrix:not(.analytics-table) th:nth-child(4), .matrix:not(.analytics-table) td:nth-child(5), .matrix:not(.analytics-table) th:nth-child(5) {{ font-weight: 700; }}
    .analytics-table td:nth-child(1), .analytics-table th:nth-child(1) {{ font-weight: 700; }}
    .analytics-table td:nth-child(4) {{ font-weight: 400; }}
    .analytics-component-col {{ width: 74px; }}
    .analytics-component-header, .analytics-component-cell {{ color: var(--muted); font-size: 0.9rem; font-weight: 500; }}
    .matrix {{ table-layout: fixed; }}
    .matrix col.rank-col {{ width: 56px; }}
    .matrix col.team-col {{ width: 190px; }}
    .matrix col.conf-col {{ width: 90px; }}
    .matrix col.avg-col {{ width: 86px; }}
    .matrix col.seed-range-col {{ width: 102px; }}
    .matrix col.app-col {{ width: 96px; }}
    .sources {{ margin-bottom: 14px; }}
    .sources td:first-child {{ text-align: left; }}
    .controls {{ display: flex; align-items: center; gap: 10px; }}
    .controls label {{ font-weight: 600; }}
    .controls select {{ border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; background: #fff; color: var(--ink); }}
    .analytics-controls {{ flex-wrap: wrap; row-gap: 8px; column-gap: 12px; margin-bottom: 6px; }}
    .analytics-controls > label {{ margin-right: 2px; }}
    #analytics-preset {{ min-width: 118px; }}
    #analytics-custom-controls {{ display: inline-flex; align-items: center; gap: 8px; }}
    #analytics-custom-controls label {{ font-weight: 500; color: var(--muted); }}
    #analytics-custom-controls input {{ width: 58px; border: 1px solid var(--line); border-radius: 6px; padding: 5px 6px; }}
    #analytics-weight-status {{ min-height: 1em; font-size: 0.9rem; }}
    #analytics-weight-status.is-error {{ color: #b42318; font-weight: 600; }}
    #analytics-weight-status.is-ok {{ color: var(--muted); }}
    #analytics-formula-note {{ margin-top: 2px; }}
    #analytics-autobids-note {{ margin: 8px 0 2px; }}
    #analytics-preset:focus, #analytics-custom-controls input:focus {{ outline: 2px solid rgba(43, 116, 66, 0.35); outline-offset: 1px; }}
    .tabs {{ display: flex; gap: 8px; margin: 10px 0 14px; flex-wrap: wrap; }}
    .tab-btn {{ border: 1px solid var(--line); background: #eef3ea; color: var(--ink); border-radius: 999px; padding: 6px 12px; font-weight: 600; cursor: pointer; }}
    .tab-btn.is-active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .section-note {{ margin: 0 0 10px; color: var(--muted); font-size: 0.95rem; }}
    .bracket-share.share-0 {{ background: #f3f6f1; }}
    .bracket-share.share-1 {{ background: #e6f0df; }}
    .bracket-share.share-2 {{ background: #d7e9ce; }}
    .bracket-share.share-3 {{ background: #c4ddb9; }}
    .bracket-share.share-4 {{ background: #afcf9f; }}
    .bracket-share.share-5 {{ background: #7abf7a; }}
    .divider {{ border: 0; border-top: 2px solid var(--line); margin: 18px 0 12px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    @media (max-width: 900px) {{
      .wrap {{ padding: 18px 10px 28px; }}
      h1 {{ font-size: 1.7rem; }}
      h2 {{ margin: 14px 0 8px; }}
      .meta {{ margin: 0 0 12px; font-size: 0.92rem; }}
      .card {{ padding: 8px; border-radius: 10px; }}
      th, td {{ padding: 5px 6px; font-size: 0.9rem; }}
      .matrix col.team-col {{ width: 170px; }}
      .matrix col.conf-col {{ width: 80px; }}
      .matrix col.avg-col {{ width: 78px; }}
      .matrix col.seed-range-col {{ width: 96px; }}
      .matrix col.app-col {{ width: 88px; }}
      .matrix th:nth-child(1), .matrix td:nth-child(1) {{
        position: sticky;
        left: 0;
        z-index: 3;
        background: #eef3ea;
      }}
      .matrix th:nth-child(2), .matrix td:nth-child(2) {{
        position: sticky;
        left: 56px;
        z-index: 3;
        background: #f8fbf6;
        box-shadow: 3px 0 0 rgba(206, 214, 201, 0.85);
      }}
      .matrix td:nth-child(1) {{ background: #f4f8f2; }}
      .matrix tbody tr:nth-child(odd) td:nth-child(2) {{ background: #f2f7ee; }}
      .analytics-controls {{ align-items: flex-start; }}
      #analytics-custom-controls {{ flex-wrap: wrap; }}
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>WBB Aggregate Bracketology</h1>
    <p class=\"meta\">Updated at {escape(_format_generated_at_et(generated_at_iso))}</p>
    <p class=\"meta\">Feedback: <a href=\"https://x.com/whitakk\" target=\"_blank\" rel=\"noopener noreferrer\">@whitakk</a></p>
    <div class=\"tabs\" role=\"tablist\" aria-label=\"Main views\">
      <button class=\"tab-btn is-active\" type=\"button\" data-tab-target=\"aggregate\" role=\"tab\" aria-selected=\"true\">Aggregate</button>
      <button class=\"tab-btn\" type=\"button\" data-tab-target=\"matrix\" role=\"tab\" aria-selected=\"false\">Matrix</button>
      <button class=\"tab-btn\" type=\"button\" data-tab-target=\"analytics\" role=\"tab\" aria-selected=\"false\">Analytics</button>
    </div>
    <section data-tab-view=\"aggregate\">
      {filter_controls_html}
      {views_html}
    </section>
    <section data-tab-view=\"matrix\" style=\"display:none;\">
      <div class=\"card\" style=\"margin-top:14px;\">
        <h2>Matrix</h2>
        <p class=\"section-note\">Coming soon.</p>
      </div>
    </section>
    <section data-tab-view=\"analytics\" style=\"display:none;\">
      {analytics_tab_html}
    </section>
  </div>
  <script>
    (() => {{
      const escapeHtml = (value) => String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

      const select = document.getElementById("source-date-filter");
      if (select) {{
        const views = document.querySelectorAll("[data-filter-view]");
        const showView = (value) => {{
          views.forEach((view) => {{
            view.style.display = view.getAttribute("data-filter-view") === value ? "block" : "none";
          }});
        }};
        showView(select.value);
        select.addEventListener("change", () => showView(select.value));
      }}

      const tabButtons = document.querySelectorAll("[data-tab-target]");
      const tabViews = document.querySelectorAll("[data-tab-view]");
      if (!tabButtons.length || !tabViews.length) return;

      const showTab = (target) => {{
        tabViews.forEach((view) => {{
          view.style.display = view.getAttribute("data-tab-view") === target ? "block" : "none";
        }});
        tabButtons.forEach((button) => {{
          const active = button.getAttribute("data-tab-target") === target;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-selected", active ? "true" : "false");
        }});
      }};

      tabButtons.forEach((button) => {{
        button.addEventListener("click", () => showTab(button.getAttribute("data-tab-target") || "aggregate"));
      }});
      showTab("aggregate");

      const analyticsDataElement = document.getElementById("analytics-data");
      if (!analyticsDataElement) return;

      let analyticsPayload = null;
      try {{
        analyticsPayload = JSON.parse(analyticsDataElement.textContent || "{{}}");
      }} catch (_error) {{
        return;
      }}

      const presetSelect = document.getElementById("analytics-preset");
      const customControls = document.getElementById("analytics-custom-controls");
      const wabInput = document.getElementById("analytics-weight-wab");
      const bartInput = document.getElementById("analytics-weight-bart");
      const netInput = document.getElementById("analytics-weight-net");
      const weightStatus = document.getElementById("analytics-weight-status");
      const projectedBody = document.getElementById("analytics-projected-body");
      const bubbleBody = document.getElementById("analytics-bubble-body");
      const scoreHeaders = document.querySelectorAll(".analytics-score-header");
      const componentHeaders = document.querySelectorAll(".analytics-component-header");
      if (!presetSelect || !customControls || !wabInput || !bartInput || !netInput) return;
      if (!weightStatus || !projectedBody || !bubbleBody || !scoreHeaders.length || !componentHeaders.length) return;

      const analyticsRows = Array.isArray(analyticsPayload.rows) ? analyticsPayload.rows : [];
      const forcedAutobidSlugs = new Set(Array.isArray(analyticsPayload.forced_autobid_slugs) ? analyticsPayload.forced_autobid_slugs : []);
      const fieldSize = Number(analyticsPayload.field_size) || 68;
      const bubbleSize = Number(analyticsPayload.bubble_size) || 16;
      const presetWeights = {{
        ebs: {{ wab: 50, bart: 50, net: 0 }},
        wab: {{ wab: 100, bart: 0, net: 0 }},
        bart: {{ wab: 0, bart: 100, net: 0 }},
        net: {{ wab: 0, bart: 0, net: 100 }},
      }};
      const presetLabel = {{
        ebs: "EBS Score",
        wab: "WAB Rank",
        bart: "T-Rank",
        net: "NET Rank",
        custom: "Custom Rank",
      }};
      const storagePresetKey = "analyticsPreset";
      const storageWeightsKey = "analyticsCustomWeights";

      const clampWeight = (value) => {{
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return 0;
        return Math.max(0, Math.min(100, Math.round(parsed)));
      }};

      const readCustomWeights = () => ({{
        wab: clampWeight(wabInput.value),
        bart: clampWeight(bartInput.value),
        net: clampWeight(netInput.value),
      }});

      const setCustomInputs = (weights) => {{
        wabInput.value = String(weights.wab);
        bartInput.value = String(weights.bart);
        netInput.value = String(weights.net);
      }};

      const formatScore = (value) => {{
        const rounded = Math.round(value * 10) / 10;
        if (Number.isInteger(rounded)) return String(rounded);
        return rounded.toFixed(1);
      }};

      const componentOrder = ["wab", "bart", "net"];
      const componentCells = (row, activeComponents, showComponents) => {{
        return componentOrder.map((componentKey) => {{
          const visible = showComponents && activeComponents.includes(componentKey);
          const rankValue = componentKey === "wab"
            ? row.wab_rank
            : componentKey === "bart"
              ? row.bart_rank
              : row.net_rank;
          const display = visible ? "table-cell" : "none";
          return `<td class=\"analytics-component-cell\" style=\"display:${{display}};\">${{rankValue}}</td>`;
        }}).join("");
      }};

      const scoreRow = (row, weights) => {{
        const wabRank = Number(row.wab_rank);
        const bartRank = Number(row.bart_rank);
        const netRank = Number(row.net_rank);
        if ((weights.wab > 0 && !Number.isFinite(wabRank)) || (weights.bart > 0 && !Number.isFinite(bartRank)) || (weights.net > 0 && !Number.isFinite(netRank))) {{
          return null;
        }}
        const score = ((weights.wab * wabRank) + (weights.bart * bartRank) + (weights.net * netRank)) / 100;
        return {{
          canonical_slug: String(row.canonical_slug || ""),
          team_display: String(row.team_display || ""),
          conference: String(row.conference || ""),
          wab_rank: wabRank,
          bart_rank: bartRank,
          net_rank: netRank,
          score,
          rank: 0,
        }};
      }};

      const sortRankings = (rows) => {{
        rows.sort((a, b) => {{
          if (a.score !== b.score) return a.score - b.score;
          if (a.wab_rank !== b.wab_rank) return a.wab_rank - b.wab_rank;
          if (a.bart_rank !== b.bart_rank) return a.bart_rank - b.bart_rank;
          return a.team_display.localeCompare(b.team_display);
        }});
        rows.forEach((row, index) => {{
          row.rank = index + 1;
        }});
      }};

      const splitProjectedAndBubble = (rankings) => {{
        const byConference = new Map();
        rankings.forEach((row) => {{
          if (!row.conference) return;
          const bucket = byConference.get(row.conference) || [];
          bucket.push(row);
          byConference.set(row.conference, bucket);
        }});

        const conferences = Array.from(byConference.keys()).sort((a, b) => a.localeCompare(b));
        const autobids = [];
        const autobidSlugs = new Set();
        conferences.forEach((conference) => {{
          const conferenceRows = byConference.get(conference) || [];
          const forcedRows = conferenceRows.filter((row) => forcedAutobidSlugs.has(row.canonical_slug));
          const candidates = forcedRows.length ? forcedRows : conferenceRows;
          if (!candidates.length) return;
          const winner = candidates.reduce((best, candidate) => {{
            if (!best) return candidate;
            if (candidate.score < best.score) return candidate;
            if (candidate.score > best.score) return best;
            if (candidate.wab_rank < best.wab_rank) return candidate;
            if (candidate.wab_rank > best.wab_rank) return best;
            if (candidate.bart_rank < best.bart_rank) return candidate;
            if (candidate.bart_rank > best.bart_rank) return best;
            return candidate.team_display.localeCompare(best.team_display) < 0 ? candidate : best;
          }}, null);
          if (!winner) return;
          autobids.push(winner);
          autobidSlugs.add(winner.canonical_slug);
        }});

        const remaining = rankings.filter((row) => !autobidSlugs.has(row.canonical_slug));
        const projected = autobids.slice(0, fieldSize);
        projected.push(...remaining.slice(0, Math.max(0, fieldSize - projected.length)));
        sortRankings(projected);

        const projectedSlugs = new Set(projected.map((row) => row.canonical_slug));
        const nonProjected = rankings.filter((row) => !projectedSlugs.has(row.canonical_slug));
        const bubble = nonProjected.slice(0, bubbleSize);
        return {{ projected, bubble, autobidSlugs }};
      }};

      const projectedSeedNumbers = (projectedRows, autobidSlugs) => {{
        if (!projectedRows.length) return [];
        const nonAutobidIndices = projectedRows
          .map((row, index) => (autobidSlugs.has(row.canonical_slug) ? -1 : index))
          .filter((index) => index >= 0);
        const lastFourNonAutobid = nonAutobidIndices.slice(-4);

        let specialPairs = [];
        if (lastFourNonAutobid.length === 4) {{
          specialPairs = [
            [lastFourNonAutobid[0], lastFourNonAutobid[1]],
            [lastFourNonAutobid[2], lastFourNonAutobid[3]],
          ];
        }}

        const pairStarts = new Map(specialPairs.map(([first, second]) => [first, second]));
        const pairSeconds = new Set(specialPairs.map(([, second]) => second));
        const seeds = Array(projectedRows.length).fill(1);
        let effectiveCounter = 0;
        let index = 0;
        while (index < projectedRows.length) {{
          if (pairStarts.has(index)) {{
            const seed = Math.min(16, Math.floor(effectiveCounter / 4) + 1);
            const second = pairStarts.get(index);
            seeds[index] = seed;
            if (typeof second === "number") seeds[second] = seed;
            effectiveCounter += 1;
            index += 1;
          }} else if (pairSeconds.has(index)) {{
            index += 1;
          }} else {{
            const seed = Math.min(16, Math.floor(effectiveCounter / 4) + 1);
            seeds[index] = seed;
            effectiveCounter += 1;
            index += 1;
          }}
        }}

        for (let idx = Math.max(0, projectedRows.length - 6); idx < projectedRows.length; idx += 1) {{
          seeds[idx] = 16;
        }}

        const ffIndices = new Set(lastFourNonAutobid);
        const sixteenIndices = seeds
          .map((seed, idx) => (seed === 16 ? idx : -1))
          .filter((idx) => idx >= 0);
        sixteenIndices.slice(-4).forEach((idx) => ffIndices.add(idx));

        return seeds.map((seed, idx) => (ffIndices.has(idx) ? `${{seed}}/FF` : seed));
      }};

      const renderRankings = (weights, preset) => {{
        const total = weights.wab + weights.bart + weights.net;
        const customSelected = preset === "custom";
        const activeComponents = componentOrder.filter((componentKey) => weights[componentKey] > 0);
        const showComponents = activeComponents.length > 1;
        customControls.style.display = customSelected ? "inline-flex" : "none";
        componentHeaders.forEach((header) => {{
          const key = header.getAttribute("data-component-col");
          const visible = Boolean(key && showComponents && activeComponents.includes(key));
          header.style.display = visible ? "table-cell" : "none";
        }});
        weightStatus.classList.remove("is-error", "is-ok");
        if (customSelected && total !== 100) {{
          weightStatus.textContent = `Custom weights must total 100% (currently ${{total}}%).`;
          weightStatus.classList.add("is-error");
          return;
        }}
        weightStatus.textContent = customSelected ? `Total: ${{total}}%` : "";
        if (customSelected) weightStatus.classList.add("is-ok");

        const rankings = analyticsRows
          .map((row) => scoreRow(row, weights))
          .filter((row) => row && row.canonical_slug && row.team_display);
        sortRankings(rankings);

        const {{ projected, bubble, autobidSlugs }} = splitProjectedAndBubble(rankings);
        const seeds = projectedSeedNumbers(projected, autobidSlugs);
        const projectedHtml = projected.map((row, index) => {{
          const team = autobidSlugs.has(row.canonical_slug)
            ? `<strong>${{escapeHtml(row.team_display)}}</strong>`
            : escapeHtml(row.team_display);
          return `<tr><td>${{seeds[index] || ""}}</td><td>${{team}}</td><td>${{escapeHtml(row.conference)}}</td><td>${{formatScore(row.score)}}</td>${{componentCells(row, activeComponents, showComponents)}}</tr>`;
        }}).join("");

        const bubbleHtml = bubble.map((row, index) => (
          `<tr><td>${{index + 1}}</td><td>${{escapeHtml(row.team_display)}}</td><td>${{escapeHtml(row.conference)}}</td><td>${{formatScore(row.score)}}</td>${{componentCells(row, activeComponents, showComponents)}}</tr>`
        )).join("");

        projectedBody.innerHTML = projectedHtml;
        bubbleBody.innerHTML = bubbleHtml;
        scoreHeaders.forEach((header) => {{
          header.textContent = presetLabel[preset] || "Score";
        }});
      }};

      let savedWeights = presetWeights.ebs;
      try {{
        const stored = localStorage.getItem(storageWeightsKey);
        if (stored) {{
          const parsed = JSON.parse(stored);
          if (parsed && typeof parsed === "object") {{
            savedWeights = {{
              wab: clampWeight(parsed.wab),
              bart: clampWeight(parsed.bart),
              net: clampWeight(parsed.net),
            }};
          }}
        }}
      }} catch (_error) {{
        savedWeights = presetWeights.ebs;
      }}
      setCustomInputs(savedWeights);

      const applyState = () => {{
        const preset = presetSelect.value;
        const weights = preset === "custom" ? readCustomWeights() : (presetWeights[preset] || presetWeights.ebs);
        if (preset !== "custom") setCustomInputs(weights);
        renderRankings(weights, preset);
      }};

      const savedPreset = localStorage.getItem(storagePresetKey);
      if (savedPreset && ["ebs", "wab", "bart", "net", "custom"].includes(savedPreset)) {{
        presetSelect.value = savedPreset;
      }}

      presetSelect.addEventListener("change", () => {{
        localStorage.setItem(storagePresetKey, presetSelect.value);
        applyState();
      }});

      [wabInput, bartInput, netInput].forEach((input) => {{
        input.addEventListener("input", () => {{
          const weights = readCustomWeights();
          localStorage.setItem(storageWeightsKey, JSON.stringify(weights));
          if (presetSelect.value === "custom") applyState();
        }});
      }});

      applyState();
    }})();
  </script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
