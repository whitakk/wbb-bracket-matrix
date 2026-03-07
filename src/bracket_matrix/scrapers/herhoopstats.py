from __future__ import annotations

import re

from dateutil import parser as date_parser

from bracket_matrix.scrapers.common import (
    extract_seed_team_pairs,
    find_updated_date_raw,
    normalize_ws,
    parse_datetime_iso,
    parse_seed,
    rows_from_pairs,
    to_soup,
)
from bracket_matrix.types import ScrapeResult


DATE_PATTERN = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})",
    flags=re.IGNORECASE,
)


def _infer_latest_date_from_text(text: str) -> str:
    candidates = DATE_PATTERN.findall(text)
    if not candidates:
        return ""
    parsed = []
    for candidate in candidates:
        try:
            parsed.append((date_parser.parse(candidate, fuzzy=True), candidate))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return ""
    parsed.sort(key=lambda item: item[0], reverse=True)
    return normalize_ws(parsed[0][1])


def parse_her_hoop_stats(
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    html: str,
    scraped_at_iso: str,
) -> ScrapeResult:
    soup = to_soup(html)
    updated_raw = find_updated_date_raw(soup)

    pairs: list[tuple[int, str, bool]] = []
    for td in soup.select("td"):
        seed_el = td.select_one("span.seed")
        team_link = td.select_one("a[href*='/stats/ncaa/team/']")
        if not seed_el or not team_link:
            continue
        seed_value = parse_seed(seed_el.get_text(" ", strip=True))
        team = normalize_ws(team_link.get_text(" ", strip=True))
        if seed_value is None or not team:
            continue
        is_play_in = bool(td.find_parent(class_=re.compile(r"first-4", flags=re.IGNORECASE)))
        pairs.append((seed_value, team, is_play_in))

    if not pairs:
        pairs = extract_seed_team_pairs(soup)

    if not updated_raw:
        updated_raw = _infer_latest_date_from_text(soup.get_text(" ", strip=True))

    updated_iso = parse_datetime_iso(updated_raw)
    rows = rows_from_pairs(
        source_key=source_key,
        source_name=source_name,
        source_url=source_url,
        source_updated_at_raw=updated_raw,
        source_updated_at_iso=updated_iso,
        scraped_at_iso=scraped_at_iso,
        pairs=pairs,
    )
    return ScrapeResult(rows=rows, updated_at_raw=updated_raw, updated_at_iso=updated_iso)
