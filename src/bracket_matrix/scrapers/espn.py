from __future__ import annotations

import re

from bracket_matrix.scrapers.common import (
    extract_seed_team_pairs,
    find_updated_date_raw,
    normalize_ws,
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

OUT_SECTION_MARKERS = {"first four out": "FFO", "next four out": "NFO"}


def _looks_like_bubble_team(line: str) -> bool:
    cleaned = normalize_ws(line)
    if not cleaned:
        return False
    if len(cleaned) > 32:
        return False
    if len(cleaned.split()) > 4:
        return False
    if re.search(r"\d", cleaned):
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z&'().\-\s]{1,31}", cleaned):
        return False
    return True


def _extract_out_teams_from_bubble_section(soup) -> list[tuple[str, str, bool]]:
    lines = [normalize_ws(line) for line in soup.get_text("\n", strip=True).splitlines() if normalize_ws(line)]
    pairs: list[tuple[str, str, bool]] = []

    for index, line in enumerate(lines):
        marker = OUT_SECTION_MARKERS.get(line.lower())
        if not marker:
            continue

        collected = 0
        cursor = index + 1
        while cursor < len(lines) and collected < 4:
            candidate = lines[cursor]
            lowered = candidate.lower()

            if lowered in OUT_SECTION_MARKERS:
                break
            if re.search(r"\b(multi-bid conferences|terms of use|privacy policy|related stories)\b", lowered):
                break
            if re.search(r"\b(teams ranked|missed the cut|last teams|to make the field|number of teams)\b", lowered):
                cursor += 1
                continue
            if _looks_like_bubble_team(candidate):
                pairs.append((marker, candidate, False))
                collected += 1
            cursor += 1

    deduped: dict[tuple[str, str], tuple[str, str, bool]] = {}
    for marker, team, is_play_in in pairs:
        key = (marker, team.lower())
        if key not in deduped:
            deduped[key] = (marker, team, is_play_in)
    return list(deduped.values())


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
    pairs.extend(_extract_out_teams_from_bubble_section(soup))

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
