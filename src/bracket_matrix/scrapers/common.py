from __future__ import annotations

import os
import re
from datetime import UTC
from typing import Iterable

from bracket_matrix.types import SeedValue

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from bracket_matrix.normalize import is_placeholder_team


DATE_HINT_PATTERN = re.compile(
    r"(?i)(?:updated|last updated|as of|published|date)\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
)

OUT_INVALID_TEAM_PATTERN = re.compile(
    r"\b(?:vs?\.?|championship|conference|credit|featured|about\s+us|watch\s+for|daily|resume\s+booster|top\s+conferences|start\s+of\s+the|multi-bid|ad|related|can)\b",
    flags=re.IGNORECASE,
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


def parse_seed_value(seed_token: str) -> SeedValue | None:
    numeric = parse_seed(seed_token)
    if numeric is not None:
        return numeric
    cleaned = normalize_ws(seed_token).upper()
    if cleaned in {"FFO", "NFO"}:
        return cleaned
    return None


def split_team_group(team_text: str) -> list[str]:
    split_chunks = re.split(r"\s*/\s*|\s+vs\.?\s+|,|\s+and\s+", team_text, flags=re.IGNORECASE)
    teams = [normalize_ws(chunk) for chunk in split_chunks if normalize_ws(chunk)]
    return teams if teams else [normalize_ws(team_text)]


def _split_out_teams(team_blob: str) -> list[str]:
    chunks = re.split(r",|;|/|\s+and\s+|\s+&\s+", normalize_ws(team_blob), flags=re.IGNORECASE)
    teams = []
    for chunk in chunks:
        cleaned = normalize_ws(re.sub(r"^[\-•*\d\.)\s]+", "", chunk))
        if cleaned:
            teams.append(cleaned)
    return teams


def _looks_like_out_team(team_text: str) -> bool:
    cleaned = normalize_ws(team_text)
    if not _looks_like_valid_team(cleaned):
        return False
    if len(cleaned.split()) > 4:
        return False
    if OUT_INVALID_TEAM_PATTERN.search(cleaned):
        return False
    if ":" in cleaned:
        return False
    words = [token for token in re.split(r"\s+", cleaned) if token]
    for word in words:
        bare = re.sub(r"[^A-Za-z]", "", word)
        if not bare:
            continue
        if len(bare) == 1:
            continue
        if bare.isupper():
            continue
        if bare[0].isupper() and bare[1:].islower():
            continue
        return False
    return True


def _find_out_marker(text: str, *, strict_line_start: bool = False) -> str:
    lowered = normalize_ws(text).lower()
    first_pattern = r"^first\s*(?:four|4)\s*out\b" if strict_line_start else r"\bfirst\s*(?:four|4)\s*out\b"
    next_pattern = r"^next\s*(?:four|4)\s*out\b" if strict_line_start else r"\bnext\s*(?:four|4)\s*out\b"
    if re.search(first_pattern, lowered):
        return "FFO"
    if re.search(next_pattern, lowered):
        return "NFO"
    return ""


def _extract_out_teams_from_table(soup: BeautifulSoup) -> list[tuple[str, str, bool]]:
    pairs: list[tuple[str, str, bool]] = []
    for table in soup.find_all("table"):
        header_cells = table.select("thead th")
        if not header_cells:
            first_row = table.select_one("tr")
            header_cells = first_row.find_all("th") if first_row else []
        if not header_cells:
            continue
        col_markers: dict[int, str] = {}
        for idx, th in enumerate(header_cells):
            marker = _find_out_marker(normalize_ws(th.get_text(" ", strip=True)))
            if marker:
                col_markers[idx] = marker
        if not col_markers:
            continue
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            for idx, marker in col_markers.items():
                if idx >= len(cells):
                    continue
                team = normalize_ws(cells[idx].get_text(" ", strip=True))
                if _looks_like_out_team(team):
                    pairs.append((marker, team, False))
    return pairs


def extract_out_teams(soup: BeautifulSoup) -> list[tuple[str, str, bool]]:
    clean_soup = BeautifulSoup(str(soup), "lxml")
    for node in clean_soup.select("script,style,noscript,template"):
        node.decompose()

    text = clean_soup.get_text("\n", strip=True)
    lines = [normalize_ws(raw_line) for raw_line in text.splitlines() if normalize_ws(raw_line)]

    stop_pattern = re.compile(
        r"\b(?:last\s*(?:four|4)\s*in|first\s*(?:four|4)\s*in|region|projected\s+field|other\s+candidates|bubble|seed\s+list)\b",
        flags=re.IGNORECASE,
    )

    pairs: list[tuple[str, str, bool]] = []

    def _append_teams(marker: str, team_blob: str) -> None:
        for team in _split_out_teams(team_blob):
            if _looks_like_out_team(team):
                pairs.append((marker, team, False))

    # Prefer table-based extraction when F4O/N4O are column headers.
    table_pairs = _extract_out_teams_from_table(clean_soup)
    if table_pairs:
        return table_pairs

    # Prefer structured extraction around marker headings.
    heading_like_selectors = "h1,h2,h3,h4,h5,h6,strong,b,p"
    for node in clean_soup.select(heading_like_selectors):
        marker = _find_out_marker(node.get_text(" ", strip=True))
        if not marker:
            continue

        inline = node.get_text(" ", strip=True)
        inline = re.sub(r"(?i)\b(?:first|next)\s*(?:four|4)\s*out\b", "", inline)
        inline = normalize_ws(re.sub(r"^[\s:\-–]+", "", inline))
        if inline:
            _append_teams(marker, inline)

        sibling_budget = 8
        for sibling in node.find_next_siblings():
            if sibling_budget <= 0:
                break
            sibling_text = normalize_ws(sibling.get_text(" ", strip=True))
            if not sibling_text:
                continue
            if _find_out_marker(sibling_text):
                break
            if stop_pattern.search(sibling_text):
                break

            items = sibling.select("li")
            if items:
                for item in items:
                    _append_teams(marker, item.get_text(" ", strip=True))
            else:
                _append_teams(marker, sibling_text)
            sibling_budget -= 1

    # Fallback lightweight line scanning for pages without clean heading structure.
    if not pairs:
        active_marker = ""
        remaining_capture_lines = 0
        for line in lines:
            if len(line) > 80:
                continue
            matched_marker = _find_out_marker(line, strict_line_start=True)
            if matched_marker:
                active_marker = matched_marker
                remaining_capture_lines = 3

                inline = re.sub(r"(?i)\b(?:first|next)\s*(?:four|4)\s*out\b", "", line)
                inline = normalize_ws(re.sub(r"^[\s:\-–]+", "", inline))
                if inline:
                    _append_teams(active_marker, inline)
                continue

            if not active_marker or remaining_capture_lines <= 0:
                continue
            if stop_pattern.search(line):
                active_marker = ""
                remaining_capture_lines = 0
                continue
            _append_teams(active_marker, line)
            remaining_capture_lines -= 1

    deduped: dict[tuple[str, str], tuple[str, str, bool]] = {}
    for marker, team, is_play_in in pairs:
        key = (marker, team.lower())
        if key not in deduped:
            deduped[key] = (marker, team, is_play_in)
    return list(deduped.values())


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
    pairs: Iterable[tuple[SeedValue, str, bool]],
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
                seed=seed,
                is_play_in=bool(is_play_in),
                scraped_at_iso=scraped_at_iso,
            )
        )
    return rows
