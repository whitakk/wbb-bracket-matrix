from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from bracket_matrix.types import MatrixRow


def _format_seed(seed: int | None) -> str:
    return "" if seed is None else str(int(seed))


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


def _bracket_share_heat_class(appearances: int, source_count: int) -> str:
    if source_count <= 0:
        return "share-0"
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


def _best_inclusion_recency_rank(row: MatrixRow, ordered_source_keys: list[str]) -> int:
    for recency_rank, source_key in enumerate(ordered_source_keys):
        if row.source_seeds.get(source_key) is not None:
            return recency_rank
    return len(ordered_source_keys)


def split_projected_field(
    matrix_rows: list[MatrixRow],
    source_keys_by_recency: list[str] | None = None,
    field_size: int = 68,
) -> tuple[list[MatrixRow], list[MatrixRow]]:
    ordered_source_keys = source_keys_by_recency or []

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
    for row in matrix_rows:
        conference = row.conference.strip()
        if not conference:
            continue
        rows_by_conference.setdefault(conference, []).append(row)

    for conference in sorted(rows_by_conference):
        candidates = rows_by_conference[conference]
        winner = min(candidates, key=_inclusion_sort_key)
        conference_winners.append(winner)
        winner_slugs.add(winner.canonical_slug)

    remaining = [row for row in matrix_rows if row.canonical_slug not in winner_slugs]
    remaining.sort(key=_inclusion_sort_key)

    projected = conference_winners[:field_size]
    remaining_slots = max(0, field_size - len(projected))
    projected.extend(remaining[:remaining_slots])

    projected_slugs = {row.canonical_slug for row in projected}
    other_candidates = [row for row in matrix_rows if row.canonical_slug not in projected_slugs]

    projected.sort(key=lambda item: (item.avg_seed, item.team_display.lower()))
    other_candidates.sort(key=lambda item: (item.avg_seed, item.team_display.lower()))
    return projected, other_candidates


def render_index_html(
    *,
    matrix_rows: list[MatrixRow],
    source_meta_rows: list[dict[str, str]],
    source_keys: list[str],
    source_key_to_name: dict[str, str],
    generated_at_iso: str,
    output_path: Path,
) -> None:
    source_meta_lookup = {row["source_key"]: row for row in source_meta_rows}
    ordered_source_keys = _order_source_keys_by_recency(source_keys, source_meta_lookup)

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

    table_header = ""
    for key in ordered_source_keys:
        source_name = source_key_to_name.get(key, key)
        source_url = (source_meta_lookup.get(key, {}).get("source_url", "") or "").strip()
        source_label = escape(_abbrev_source_label(source_name))
        if source_url:
            source_label = (
                f"<a href=\"{escape(source_url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{source_label}</a>"
            )
        table_header += f"<th title=\"{escape(source_name)}\">{source_label}</th>"

    source_colgroup = "".join("<col class=\"source-col\" />" for _ in ordered_source_keys)
    source_count = len(ordered_source_keys)

    projected_field, other_candidates = split_projected_field(
        matrix_rows,
        source_keys_by_recency=ordered_source_keys,
    )

    projected_rows_html = ""
    for idx, row in enumerate(projected_field, start=1):
        source_cells = "".join(
            f"<td>{_format_seed(row.source_seeds.get(source_key))}</td>" for source_key in ordered_source_keys
        )
        bracket_share = _format_bracket_share(row.appearances, source_count)
        bracket_share_class = _bracket_share_heat_class(row.appearances, source_count)
        projected_rows_html += (
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(row.team_display)}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{row.avg_seed:.1f}</td>"
            f"<td class=\"bracket-share {bracket_share_class}\">{bracket_share}</td>"
            f"{source_cells}"
            "</tr>"
        )

    other_rows_html = ""
    for idx, row in enumerate(other_candidates, start=1):
        source_cells = "".join(
            f"<td>{_format_seed(row.source_seeds.get(source_key))}</td>" for source_key in ordered_source_keys
        )
        bracket_share = _format_bracket_share(row.appearances, source_count)
        bracket_share_class = _bracket_share_heat_class(row.appearances, source_count)
        other_rows_html += (
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(row.team_display)}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{row.avg_seed:.1f}</td>"
            f"<td class=\"bracket-share {bracket_share_class}\">{bracket_share}</td>"
            f"{source_cells}"
            "</tr>"
        )

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>WBB Bracket Matrix</title>
  <style>
    :root {{
      --bg: #f5f7f2;
      --paper: #ffffff;
      --ink: #1f2a1d;
      --muted: #5f6b5d;
      --line: #ced6c9;
      --accent: #2f5d3a;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Source Sans 3", "Segoe UI", sans-serif; background: radial-gradient(circle at top right, #e9f2e6, var(--bg)); color: var(--ink); }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 2rem; letter-spacing: 0.02em; }}
    h2 {{ margin: 18px 0 10px; font-size: 1.2rem; letter-spacing: 0.01em; }}
    .meta {{ color: var(--muted); margin: 0 0 16px; }}
    .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 12px; overflow-x: auto; box-shadow: 0 8px 30px rgba(0,0,0,0.05); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    th {{ background: #eef3ea; font-weight: 700; }}
    .matrix thead th {{ position: sticky; top: 0; z-index: 2; }}
    .matrix tbody tr:nth-child(odd) {{ background: #fbfdf9; }}
    .matrix tbody tr:hover {{ background: #f0f6eb; }}
    td:nth-child(2), th:nth-child(2) {{ text-align: left; min-width: 200px; }}
    .matrix td:nth-child(4), .matrix th:nth-child(4), .matrix td:nth-child(5), .matrix th:nth-child(5) {{ font-weight: 700; }}
    .matrix {{ table-layout: fixed; }}
    .matrix col.rank-col {{ width: 56px; }}
    .matrix col.team-col {{ width: 190px; }}
    .matrix col.conf-col {{ width: 90px; }}
    .matrix col.avg-col {{ width: 86px; }}
    .matrix col.app-col {{ width: 96px; }}
    .matrix col.source-col {{ width: 68px; }}
    .sources {{ margin-bottom: 14px; }}
    .sources td:first-child {{ text-align: left; }}
    .bracket-share.share-0 {{ background: #f3f6f1; }}
    .bracket-share.share-1 {{ background: #e6f0df; }}
    .bracket-share.share-2 {{ background: #d7e9ce; }}
    .bracket-share.share-3 {{ background: #c4ddb9; }}
    .bracket-share.share-4 {{ background: #afcf9f; }}
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
      .matrix col.app-col {{ width: 88px; }}
      .matrix col.source-col {{ width: 62px; }}
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
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>WBB Bracket Matrix</h1>
    <p class=\"meta\">Updated at {escape(_format_generated_at_et(generated_at_iso))}</p>

    <div class=\"card\" style=\"margin-top:14px;\">
      <h2>Projected Field</h2>
      <table class=\"matrix\">
        <colgroup>
          <col class=\"rank-col\" />
          <col class=\"team-col\" />
          <col class=\"conf-col\" />
          <col class=\"avg-col\" />
          <col class=\"app-col\" />
          {source_colgroup}
        </colgroup>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th>Conf</th>
            <th>Avg Seed</th>
            <th>% Brackets</th>
            {table_header}
          </tr>
        </thead>
        <tbody>
          {projected_rows_html}
        </tbody>
      </table>

      <hr class=\"divider\" />
      <h2>Other Candidates</h2>
      <table class=\"matrix\">
        <colgroup>
          <col class=\"rank-col\" />
          <col class=\"team-col\" />
          <col class=\"conf-col\" />
          <col class=\"avg-col\" />
          <col class=\"app-col\" />
          {source_colgroup}
        </colgroup>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th>Conf</th>
            <th>Avg Seed</th>
            <th>% Brackets</th>
            {table_header}
          </tr>
        </thead>
        <tbody>
          {other_rows_html}
        </tbody>
      </table>
    </div>

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
  </div>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
