from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from bracket_matrix.types import MatrixRow


def _format_seed(seed: int | None) -> str:
    return "" if seed is None else str(int(seed))


def _abbrev_source_label(source_name: str, max_len: int = 6) -> str:
    cleaned = " ".join(source_name.split())
    if cleaned.lower() == "cbs sports":
        return "CBS"
    if cleaned.lower() == "usa today":
        return "USAT"
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


def split_projected_field(matrix_rows: list[MatrixRow], field_size: int = 68) -> tuple[list[MatrixRow], list[MatrixRow]]:
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
        winner = min(
            candidates,
            key=lambda item: (-item.appearances, item.avg_seed, item.team_display.lower()),
        )
        conference_winners.append(winner)
        winner_slugs.add(winner.canonical_slug)

    remaining = [row for row in matrix_rows if row.canonical_slug not in winner_slugs]
    remaining.sort(key=lambda item: (-item.appearances, item.avg_seed, item.team_display.lower()))

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

    table_header = "".join(
        f"<th title=\"{escape(source_key_to_name.get(key, key))}\">{escape(_abbrev_source_label(source_key_to_name.get(key, key)))}</th>"
        for key in ordered_source_keys
    )
    source_colgroup = "".join("<col class=\"source-col\" />" for _ in ordered_source_keys)

    projected_field, other_candidates = split_projected_field(matrix_rows)

    projected_rows_html = ""
    for idx, row in enumerate(projected_field, start=1):
        source_cells = "".join(
            f"<td>{_format_seed(row.source_seeds.get(source_key))}</td>" for source_key in ordered_source_keys
        )
        projected_rows_html += (
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(row.team_display)}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{row.avg_seed:.1f}</td>"
            f"<td>{row.appearances}</td>"
            f"{source_cells}"
            "</tr>"
        )

    other_rows_html = ""
    for idx, row in enumerate(other_candidates, start=1):
        source_cells = "".join(
            f"<td>{_format_seed(row.source_seeds.get(source_key))}</td>" for source_key in ordered_source_keys
        )
        other_rows_html += (
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(row.team_display)}</td>"
            f"<td>{escape(row.conference)}</td>"
            f"<td>{row.avg_seed:.1f}</td>"
            f"<td>{row.appearances}</td>"
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
    th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: center; white-space: nowrap; }}
    th {{ background: #eef3ea; font-weight: 700; }}
    td:nth-child(2), th:nth-child(2) {{ text-align: left; min-width: 200px; }}
    .matrix {{ table-layout: fixed; }}
    .matrix col.rank-col {{ width: 56px; }}
    .matrix col.team-col {{ width: 220px; }}
    .matrix col.conf-col {{ width: 90px; }}
    .matrix col.avg-col {{ width: 86px; }}
    .matrix col.app-col {{ width: 96px; }}
    .matrix col.source-col {{ width: 72px; }}
    .sources {{ margin-bottom: 14px; }}
    .sources td:first-child {{ text-align: left; }}
    .divider {{ border: 0; border-top: 2px solid var(--line); margin: 18px 0 12px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>WBB Bracket Matrix</h1>
    <p class=\"meta\">Generated at {escape(generated_at_iso)} (UTC)</p>

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
            <th>Conference</th>
            <th>Avg Seed</th>
            <th>Appearances</th>
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
            <th>Conference</th>
            <th>Avg Seed</th>
            <th>Appearances</th>
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
