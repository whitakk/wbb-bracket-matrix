from __future__ import annotations

import os
import re
from datetime import UTC
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from bracket_matrix.normalize import is_placeholder_team


DATE_HINT_PATTERN = re.compile(
    r"(?i)(?:updated|last updated|as of|published|date)\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
)
SEED_TEAM_INLINE_PATTERN = re.compile(
    r"^(?:#|No\.\s*)?(1[0-6]|[1-9])(?:\s*(?:seed|seeds))?\s*[:\-\).]?\s+([A-Za-z0-9'&().,/\-\s]{2,80})$",
    flags=re.IGNORECASE,
)


def fetch_html(url: str, timeout_seconds: int, user_agent: str) -> str:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": user_agent},
    )
    response.raise_for_status()
    return response.text


def fetch_html_playwright(url: str, timeout_seconds: int) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed") from exc

    storage_state_path = normalize_ws(os.getenv("BRACKET_MATRIX_PLAYWRIGHT_STORAGE_STATE", ""))
    channel = normalize_ws(os.getenv("BRACKET_MATRIX_PLAYWRIGHT_CHANNEL", ""))
    headless_raw = normalize_ws(os.getenv("BRACKET_MATRIX_PLAYWRIGHT_HEADLESS", "true")).lower()
    headless = headless_raw not in {"0", "false", "no", "off"}

    launch_kwargs: dict[str, object] = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if channel:
        launch_kwargs["channel"] = channel

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        if storage_state_path:
            context = browser.new_context(storage_state=storage_state_path)
        else:
            context = browser.new_context()
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.goto(url, timeout=timeout_seconds * 1000, wait_until="networkidle")
        html = page.content()
        context.close()
        browser.close()
    return html


def to_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_seed(seed_token: str) -> int | None:
    cleaned = normalize_ws(seed_token).lower().replace("seed", "").replace("no.", "").strip()
    match = re.match(r"^(1[0-6]|[1-9])", cleaned)
    if not match:
        return None
    return int(match.group(1))


def split_team_group(team_text: str) -> list[str]:
    split_chunks = re.split(r"\s*/\s*|\s+vs\.?\s+|,|\s+and\s+", team_text, flags=re.IGNORECASE)
    teams = [normalize_ws(chunk) for chunk in split_chunks if normalize_ws(chunk)]
    return teams if teams else [normalize_ws(team_text)]


def _looks_like_valid_team(team_text: str) -> bool:
    cleaned = normalize_ws(team_text)
    if not cleaned:
        return False
    if len(cleaned) < 2 or len(cleaned) > 60:
        return False
    if re.search(r"\d", cleaned):
        return False
    if len(cleaned.split()) > 6:
        return False
    if re.search(r"\b(?:am|pm)\s*et\b", cleaned, flags=re.IGNORECASE):
        return False
    if is_placeholder_team(cleaned):
        return False
    return True


def extract_seed_team_pairs(soup: BeautifulSoup) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []

    for row in soup.select("table tr"):
        cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in row.select("th,td")]
        if len(cells) < 2:
            continue

        seed_entries: list[tuple[int, int]] = []
        for idx, cell in enumerate(cells):
            parsed = parse_seed(cell)
            if parsed is not None:
                seed_entries.append((idx, parsed))

        if not seed_entries:
            continue

        seed_indices = {seed_index for seed_index, _ in seed_entries}

        for seed_index, seed_value in seed_entries:
            candidate_indices = [seed_index + 1, seed_index - 1]
            candidate_indices.extend(i for i in range(len(cells)) if i not in seed_indices and i not in candidate_indices)

            for candidate_index in candidate_indices:
                if candidate_index < 0 or candidate_index >= len(cells):
                    continue
                team_text = cells[candidate_index]
                if not team_text:
                    continue
                team_list = split_team_group(team_text)
                valid_teams = [team for team in team_list if _looks_like_valid_team(team)]
                if not valid_teams:
                    continue
                is_play_in = len(valid_teams) > 1
                for team in valid_teams:
                    pairs.append((seed_value, team, is_play_in))
                break

    # Supplemental parsing for list/prose items that look like explicit seed/team entries.
    for node in soup.select("li,p,h3,h4,span"):
        text = normalize_ws(node.get_text(" ", strip=True))
        if not text or len(text) > 100:
            continue
        inline_match = SEED_TEAM_INLINE_PATTERN.match(text)
        if not inline_match:
            continue
        seed_value = int(inline_match.group(1))
        team_text = normalize_ws(inline_match.group(2))
        teams = [team for team in split_team_group(team_text) if _looks_like_valid_team(team)]
        if not teams:
            continue
        is_play_in = len(teams) > 1
        for team in teams:
            pairs.append((seed_value, team, is_play_in))

    deduped: dict[tuple[int, str], tuple[int, str, bool]] = {}
    for seed, team, is_play_in in pairs:
        team_clean = normalize_ws(team)
        if not _looks_like_valid_team(team_clean):
            continue
        key = (seed, team_clean.lower())
        if key not in deduped:
            deduped[key] = (seed, team_clean, is_play_in)

    return list(deduped.values())


def find_updated_date_raw(soup: BeautifulSoup) -> str:
    for node in soup.select("time"):
        txt = normalize_ws(node.get_text(" ", strip=True))
        if txt:
            return txt
        attr = node.attrs.get("datetime")
        if isinstance(attr, str) and attr:
            return normalize_ws(attr)

    text = soup.get_text("\n", strip=True)
    match = DATE_HINT_PATTERN.search(text)
    if match:
        return normalize_ws(match.group(1))
    return ""


def parse_datetime_iso(raw_date: str) -> str:
    if not raw_date:
        return ""
    try:
        parsed = date_parser.parse(raw_date, fuzzy=True)
    except (ValueError, TypeError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def rows_from_pairs(
    source_key: str,
    source_name: str,
    source_url: str,
    source_updated_at_raw: str,
    source_updated_at_iso: str,
    scraped_at_iso: str,
    pairs: Iterable[tuple[int, str, bool]],
):
    from bracket_matrix.types import SourceProjectionRow

    rows: list[SourceProjectionRow] = []
    for seed, team, is_play_in in pairs:
        rows.append(
            SourceProjectionRow(
                source_key=source_key,
                source_name=source_name,
                source_url=source_url,
                source_updated_at_raw=source_updated_at_raw,
                source_updated_at_iso=source_updated_at_iso,
                team_raw=normalize_ws(team),
                seed=int(seed),
                is_play_in=bool(is_play_in),
                scraped_at_iso=scraped_at_iso,
            )
        )
    return rows
