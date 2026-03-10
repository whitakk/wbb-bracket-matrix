from __future__ import annotations

import re
from urllib.parse import urljoin

import requests

from bracket_matrix.scrapers.common import (
    extract_out_teams,
    extract_seed_team_pairs,
    find_updated_date_raw,
    normalize_ws,
    parse_datetime_iso,
    rows_from_pairs,
    split_team_group,
    to_soup,
)
from bracket_matrix.types import ScrapeResult


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; WBBBracketMatrix/0.1; +https://github.com/)"


def _fetch_html_response(url: str) -> tuple[str, str]:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": DEFAULT_USER_AGENT})
    response.raise_for_status()
    return response.url, response.text


def _score_bracketology_link(text: str, href: str) -> int:
    text_lower = text.lower()
    href_lower = href.lower()
    score = 0
    if "bracketology" in text_lower:
        score += 10
    if "women" in text_lower:
        score += 4
    if text_lower in {"bracketology", "women's bracketology", "womens bracketology"}:
        score += 6
    if "bracketology" in href_lower:
        score += 8
    if "womens-college-basketball" in href_lower:
        score += 4
    if "/news/womens-bracketology" in href_lower:
        score += 2
    if "/video/" in href_lower or "/photos/" in href_lower:
        score -= 8
    return score


def _find_bracketology_menu_url(page_html: str, page_url: str) -> str:
    soup = to_soup(page_html)
    best_url = ""
    best_score = -999

    selectors = [
        "header a[href]",
        "nav a[href]",
        "[class*='nav'] a[href]",
        "[class*='menu'] a[href]",
        "a[href]",
    ]

    for selector in selectors:
        for anchor in soup.select(selector):
            href = normalize_ws(anchor.get("href", ""))
            if not href:
                continue
            text = normalize_ws(anchor.get_text(" ", strip=True))
            score = _score_bracketology_link(text, href)
            if score <= 0:
                continue
            resolved = urljoin(page_url, href)
            if score > best_score:
                best_score = score
                best_url = resolved

        if best_url:
            return best_url

    return ""


def _looks_like_team_name(team: str) -> bool:
    cleaned = normalize_ws(team)
    if not cleaned:
        return False
    if len(cleaned) < 2 or len(cleaned) > 60:
        return False
    if len(cleaned.split()) > 6:
        return False
    if re.search(r"\d", cleaned):
        return False
    if re.search(r"\b(?:region|first four|last four|seed|projected|record)\b", cleaned, flags=re.IGNORECASE):
        return False
    return True


def _extract_seed_team_pairs_from_text(text: str) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []

    for raw_line in text.splitlines():
        line = normalize_ws(raw_line)
        if not line:
            continue

        line = re.sub(r"^[\-•*]\s*", "", line)

        leading_match = re.match(
            r"^(?:No\.\s*)?(1[0-6]|[1-9])(?:\s*(?:seed|seeds))?\s*[:\-\).]?\s+(.+)$",
            line,
            flags=re.IGNORECASE,
        )
        if leading_match:
            seed = int(leading_match.group(1))
            team_blob = normalize_ws(leading_match.group(2))
            teams = [team for team in split_team_group(team_blob) if _looks_like_team_name(team)]
            if teams:
                is_play_in = len(teams) > 1
                for team in teams:
                    pairs.append((seed, team, is_play_in))
            continue

        matchup_patterns = [
            r"(?:No\.\s*)?(1[0-6]|[1-9])\.?\s+([A-Za-z][A-Za-z&'().\-\s]{1,45})\s+vs\.?\s+(?:No\.\s*)?(1[0-6]|[1-9])\.?\s+([A-Za-z][A-Za-z&'().\-\s]{1,45})",
            r"(?:No\.\s*)?(1[0-6]|[1-9])\.?\s+([A-Za-z][A-Za-z&'().\-\s]{1,45})\s+v\.\s+(?:No\.\s*)?(1[0-6]|[1-9])\.?\s+([A-Za-z][A-Za-z&'().\-\s]{1,45})",
        ]
        for pattern in matchup_patterns:
            matchup = re.search(pattern, line, flags=re.IGNORECASE)
            if not matchup:
                continue
            first_seed = int(matchup.group(1))
            first_team = normalize_ws(matchup.group(2).strip(" ,.;:"))
            second_seed = int(matchup.group(3))
            second_team = normalize_ws(matchup.group(4).strip(" ,.;:"))
            if _looks_like_team_name(first_team):
                pairs.append((first_seed, first_team, False))
            if _looks_like_team_name(second_team):
                pairs.append((second_seed, second_team, False))
            break

    deduped: dict[tuple[int, str], tuple[int, str, bool]] = {}
    for seed, team, is_play_in in pairs:
        cleaned = normalize_ws(team)
        if not _looks_like_team_name(cleaned):
            continue
        key = (seed, cleaned.lower())
        if key not in deduped:
            deduped[key] = (seed, cleaned, is_play_in)

    return list(deduped.values())


def _extract_pairs_from_projection_table(soup) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []

    table_rows = soup.select("table.team-picks-authors tbody tr")
    if not table_rows:
        table_rows = soup.select(".ArticleContentTable table tbody tr")

    for row in table_rows:
        cells = row.select("td")
        if len(cells) < 2:
            continue

        seed_text = normalize_ws(cells[0].get_text(" ", strip=True))
        if not re.fullmatch(r"(1[0-6]|[1-9])", seed_text):
            continue
        seed = int(seed_text)

        for cell in cells[1:]:
            team_candidates = [normalize_ws(node.get_text(" ", strip=True)) for node in cell.select(".team-name")]

            if not team_candidates:
                team_candidates = [
                    normalize_ws(node.get_text(" ", strip=True))
                    for node in cell.select("a[href*='/womens-college-basketball/teams/']")
                ]

            if not team_candidates:
                raw = normalize_ws(cell.get_text(" ", strip=True)).replace("team logo", "")
                if raw:
                    team_candidates = [raw]

            teams: list[str] = []
            for candidate in team_candidates:
                teams.extend(split_team_group(candidate))

            valid_teams = [team for team in teams if _looks_like_team_name(team)]
            if not valid_teams:
                continue

            is_play_in = len(valid_teams) > 1
            for team in valid_teams:
                pairs.append((seed, team, is_play_in))

    deduped: dict[tuple[int, str], tuple[int, str, bool]] = {}
    for seed, team, is_play_in in pairs:
        cleaned = normalize_ws(team)
        if not _looks_like_team_name(cleaned):
            continue
        key = (seed, cleaned.lower())
        if key not in deduped:
            deduped[key] = (seed, cleaned, is_play_in)

    return list(deduped.values())


def parse_cbssports(
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    html: str,
    scraped_at_iso: str,
) -> ScrapeResult:
    bracketology_url = _find_bracketology_menu_url(html, source_url)
    if not bracketology_url:
        raise RuntimeError("Unable to find CBS Sports bracketology link from hub page")

    latest_url, latest_html = _fetch_html_response(bracketology_url)
    soup = to_soup(latest_html)

    pairs = _extract_pairs_from_projection_table(soup)
    if not pairs:
        pairs = extract_seed_team_pairs(soup)
    if not pairs:
        pairs = _extract_seed_team_pairs_from_text(soup.get_text("\n", strip=True))
    pairs.extend(extract_out_teams(soup))

    updated_raw = find_updated_date_raw(soup)
    updated_iso = parse_datetime_iso(updated_raw)

    rows = rows_from_pairs(
        source_key=source_key,
        source_name=source_name,
        source_url=latest_url,
        source_updated_at_raw=updated_raw,
        source_updated_at_iso=updated_iso,
        scraped_at_iso=scraped_at_iso,
        pairs=pairs,
    )
    return ScrapeResult(rows=rows, updated_at_raw=updated_raw, updated_at_iso=updated_iso)
