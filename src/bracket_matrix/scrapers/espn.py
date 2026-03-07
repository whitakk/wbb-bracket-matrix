from __future__ import annotations

import re

from bracket_matrix.scrapers.common import (
    extract_seed_team_pairs,
    find_updated_date_raw,
    parse_datetime_iso,
    rows_from_pairs,
    to_soup,
)
from bracket_matrix.types import ScrapeResult


BLOCKED_MARKERS = [
    "enable javascript",
    "before you continue",
    "bot detection",
    "captcha",
]


def is_probably_blocked(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in BLOCKED_MARKERS)


def parse_espn(
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    html: str,
    scraped_at_iso: str,
) -> ScrapeResult:
    soup = to_soup(html)
    updated_raw = find_updated_date_raw(soup)
    pairs = extract_seed_team_pairs(soup)

    if not pairs:
        # ESPN articles may list teams in prose sections (e.g. "No. 1 seeds: Team A ...").
        text = soup.get_text("\n", strip=True)
        for match in re.finditer(
            r"No\.\s*(1[0-6]|[1-9])\s+seeds?\s*[:\-]\s*([^\n]+)",
            text,
            flags=re.IGNORECASE,
        ):
            seed = int(match.group(1))
            teams = re.split(r",| and ", match.group(2))
            for team in teams:
                cleaned = team.strip()
                if cleaned:
                    pairs.append((seed, cleaned, False))

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
