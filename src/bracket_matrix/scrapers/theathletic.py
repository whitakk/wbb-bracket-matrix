from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests

from bracket_matrix.scrapers.common import (
    extract_seed_team_pairs,
    fetch_html_playwright,
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
PLAYWRIGHT_STORAGE_STATE_ENV = "BRACKET_MATRIX_PLAYWRIGHT_STORAGE_STATE"


def _updated_from_article_url(url: str) -> tuple[str, str]:
    match = re.search(r"/athletic/\d+/(\d{4})/(\d{2})/(\d{2})/", normalize_ws(url))
    if not match:
        return "", ""

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    try:
        parsed = datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return "", ""

    return f"{month}/{day}/{year}", parsed.replace(microsecond=0).isoformat()


def _uses_authenticated_playwright() -> bool:
    return bool(normalize_ws(os.getenv(PLAYWRIGHT_STORAGE_STATE_ENV, "")))


def _fetch_html_response(url: str) -> tuple[str, str]:
    if _uses_authenticated_playwright():
        html = fetch_html_playwright(url, timeout_seconds=DEFAULT_TIMEOUT_SECONDS)
        return url, html

    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": DEFAULT_USER_AGENT})
    response.raise_for_status()
    return response.url, response.text


def _contains_womens_bracket_watch(text: str) -> bool:
    lowered = normalize_ws(text).lower()
    women_match = "women" in lowered
    bracket_watch_match = "bracket watch" in lowered or "bracket-watch" in lowered
    return women_match and bracket_watch_match


def _score_article_link(label: str, href: str) -> int:
    label_lower = normalize_ws(label).lower()
    href_lower = normalize_ws(href).lower()
    score = 0

    if _contains_womens_bracket_watch(label_lower):
        score += 12
    if _contains_womens_bracket_watch(href_lower):
        score += 9
    if "athletic" in href_lower:
        score += 4
    if re.search(r"/athletic/\d+", href_lower):
        score += 3
    if "men" in label_lower or "men" in href_lower:
        score -= 8

    return score


def _find_latest_bracket_watch_article_url(hub_html: str, hub_url: str) -> str:
    soup = to_soup(hub_html)
    best_url = ""
    best_score = -999

    selectors = [
        "article a[href]",
        "main a[href]",
        "a[href*='/athletic/']",
        "a[href]",
    ]

    for selector in selectors:
        for anchor in soup.select(selector):
            href = normalize_ws(anchor.get("href", ""))
            if not href:
                continue

            label = normalize_ws(anchor.get_text(" ", strip=True))
            if not label:
                label = normalize_ws(anchor.get("aria-label", ""))
            if not label:
                label = normalize_ws(anchor.get("title", ""))

            score = _score_article_link(label, href)
            if score <= 0:
                continue

            if not _contains_womens_bracket_watch(f"{label} {href}"):
                continue

            resolved = urljoin(hub_url, href)
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
    if re.search(r"\b(?:region|first four|last four|seed|projected|record|bracket watch)\b", cleaned, flags=re.IGNORECASE):
        return False
    return True


def _extract_seed_team_pairs_from_text(text: str) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []

    for raw_line in text.splitlines():
        line = normalize_ws(raw_line)
        if not line:
            continue

        leading_match = re.match(
            r"^(?:No\.\s*)?(1[0-6]|[1-9])(?:\s*(?:seed|seeds))?\s*[:\-\).]?\s+(.+)$",
            line,
            flags=re.IGNORECASE,
        )
        if not leading_match:
            continue

        seed = int(leading_match.group(1))
        team_blob = normalize_ws(leading_match.group(2).strip(" ,.;:"))
        teams = [team for team in split_team_group(team_blob) if _looks_like_team_name(team)]
        if not teams:
            continue

        is_play_in = len(teams) > 1
        for team in teams:
            pairs.append((seed, team, is_play_in))

    deduped: dict[tuple[int, str], tuple[int, str, bool]] = {}
    for seed, team, is_play_in in pairs:
        cleaned = normalize_ws(team)
        key = (seed, cleaned.lower())
        if key not in deduped:
            deduped[key] = (seed, cleaned, is_play_in)

    return list(deduped.values())


def _extract_seed_team_pairs_from_bracket_canvas(html: str) -> list[tuple[int, str, bool]]:
    soup = to_soup(html)
    pairs: list[tuple[int, str, bool]] = []

    for container in soup.select(".bracket-canvas .seed-team-container"):
        seed_node = container.select_one(".seed")
        team_name_node = container.select_one(".team-name")
        if seed_node is None or team_name_node is None:
            continue

        seed_text = normalize_ws(seed_node.get_text(" ", strip=True))
        seed_match = re.search(r"^(1[0-6]|[1-9])\b", seed_text)
        if not seed_match:
            continue
        seed = int(seed_match.group(1))

        team_candidates: list[str] = []
        child_divs = team_name_node.find_all("div", recursive=False)
        if child_divs:
            team_candidates.extend(normalize_ws(div.get_text(" ", strip=True)) for div in child_divs)
        else:
            team_candidates.append(normalize_ws(team_name_node.get_text(" ", strip=True)))

        teams: list[str] = []
        for candidate in team_candidates:
            if not candidate:
                continue
            for split_team in split_team_group(candidate):
                if _looks_like_team_name(split_team):
                    teams.append(split_team)

        unique_teams = list(dict.fromkeys(teams))
        if not unique_teams:
            continue

        is_play_in = len(unique_teams) > 1
        for team in unique_teams:
            pairs.append((seed, team, is_play_in))

    deduped: dict[tuple[int, str], tuple[int, str, bool]] = {}
    for seed, team, is_play_in in pairs:
        cleaned = normalize_ws(team)
        key = (seed, cleaned.lower())
        if key not in deduped:
            deduped[key] = (seed, cleaned, is_play_in)

    return list(deduped.values())


def parse_the_athletic(
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    html: str,
    scraped_at_iso: str,
) -> ScrapeResult:
    direct_soup = to_soup(html)
    direct_pairs = _extract_seed_team_pairs_from_bracket_canvas(html)
    if not direct_pairs:
        direct_pairs = extract_seed_team_pairs(direct_soup)
    if not direct_pairs:
        direct_pairs = _extract_seed_team_pairs_from_text(direct_soup.get_text("\n", strip=True))
    if direct_pairs:
        direct_updated_raw, direct_updated_iso = _updated_from_article_url(source_url)
        if not direct_updated_iso:
            direct_updated_raw = find_updated_date_raw(direct_soup)
            direct_updated_iso = parse_datetime_iso(direct_updated_raw)
        direct_rows = rows_from_pairs(
            source_key=source_key,
            source_name=source_name,
            source_url=source_url,
            source_updated_at_raw=direct_updated_raw,
            source_updated_at_iso=direct_updated_iso,
            scraped_at_iso=scraped_at_iso,
            pairs=direct_pairs,
        )
        return ScrapeResult(rows=direct_rows, updated_at_raw=direct_updated_raw, updated_at_iso=direct_updated_iso)

    latest_article_url = _find_latest_bracket_watch_article_url(html, source_url)

    if not latest_article_url and _uses_authenticated_playwright():
        hub_html = fetch_html_playwright(source_url, timeout_seconds=DEFAULT_TIMEOUT_SECONDS)
        latest_article_url = _find_latest_bracket_watch_article_url(hub_html, source_url)

    if not latest_article_url:
        return ScrapeResult(rows=[], updated_at_raw="", updated_at_iso="")

    resolved_article_url, article_html = _fetch_html_response(latest_article_url)
    soup = to_soup(article_html)

    pairs = _extract_seed_team_pairs_from_bracket_canvas(article_html)
    if not pairs:
        pairs = extract_seed_team_pairs(soup)
    if not pairs:
        pairs = _extract_seed_team_pairs_from_text(soup.get_text("\n", strip=True))
    if not pairs:
        raise RuntimeError("The Athletic parser returned no seed/team rows")

    updated_raw, updated_iso = _updated_from_article_url(resolved_article_url)
    if not updated_iso:
        updated_raw = find_updated_date_raw(soup)
        updated_iso = parse_datetime_iso(updated_raw)

    rows = rows_from_pairs(
        source_key=source_key,
        source_name=source_name,
        source_url=resolved_article_url,
        source_updated_at_raw=updated_raw,
        source_updated_at_iso=updated_iso,
        scraped_at_iso=scraped_at_iso,
        pairs=pairs,
    )
    return ScrapeResult(rows=rows, updated_at_raw=updated_raw, updated_at_iso=updated_iso)
