from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from bracket_matrix.scrapers.common import (
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


def _is_ncaa_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not host.endswith("ncaa.com"):
        return False
    return "/news/" in path and "/basketball-women/" in path and "/article/" in path


def _decode_google_result_href(href: str, search_url: str) -> str:
    cleaned = normalize_ws(href)
    if not cleaned:
        return ""

    if cleaned.startswith("/"):
        cleaned = urljoin(search_url, cleaned)

    parsed = urlparse(cleaned)
    if parsed.netloc.lower().endswith("google.com") and parsed.path == "/url":
        target = parse_qs(parsed.query).get("q", [""])[0]
        return normalize_ws(unescape(target))

    if parsed.scheme in {"http", "https"}:
        return normalize_ws(unescape(cleaned))

    return ""


def _find_first_ncaa_article_url(search_html: str, search_url: str) -> str:
    soup = to_soup(search_html)
    for anchor in soup.select("a[href]"):
        href = normalize_ws(anchor.get("href", ""))
        if not href:
            continue
        resolved = _decode_google_result_href(href, search_url)
        if resolved and _is_ncaa_article_url(resolved):
            return resolved

    for candidate in re.findall(r"https?://www\.ncaa\.com/news/basketball-women/article/[^\"'\s<]+", search_html):
        resolved = normalize_ws(unescape(candidate))
        if _is_ncaa_article_url(resolved):
            return resolved

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
    if re.search(r"\b(?:region|seed|projected|record|bracket|final\s+four|selection\s+sunday)\b", cleaned, flags=re.IGNORECASE):
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


def _extract_pairs_from_bracket_table(soup) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []

    bracket_table = None
    for table in soup.select("table"):
        header_cells = [normalize_ws(cell.get_text(" ", strip=True)).lower() for cell in table.select("tr th")]
        if not header_cells:
            continue
        has_seed_header = any(cell == "seed" for cell in header_cells)
        has_region_header = sum(1 for cell in header_cells if "region" in cell) >= 2
        if has_seed_header and has_region_header:
            bracket_table = table
            break

    if bracket_table is None:
        return []

    for row in bracket_table.select("tr"):
        cells = row.select("th,td")
        if len(cells) < 3:
            continue

        seed_text = normalize_ws(cells[0].get_text(" ", strip=True))
        if not re.fullmatch(r"1[0-6]|[1-9]", seed_text):
            continue
        seed = int(seed_text)

        for team_cell in cells[1:]:
            cell_text = normalize_ws(team_cell.get_text(" ", strip=True))
            if not cell_text:
                continue
            teams = [team for team in split_team_group(cell_text) if _looks_like_team_name(team)]
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


def _find_updated_date_raw(soup) -> str:
    for selector in [
        "meta[property='article:modified_time']",
        "meta[property='article:published_time']",
        "meta[name='parsely-pub-date']",
        "meta[name='article:published_time']",
        "meta[name='article:modified_time']",
    ]:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = normalize_ws(str(node.attrs.get("content", "")))
        if value:
            return value
    return find_updated_date_raw(soup)


def _infer_updated_date_raw_from_article_url(article_url: str) -> str:
    match = re.search(r"/article/(\d{4}-\d{2}-\d{2})/", article_url)
    if not match:
        return ""
    return match.group(1)


def parse_ncaa(
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    html: str,
    scraped_at_iso: str,
) -> ScrapeResult:
    provided_html_soup = to_soup(html)
    canonical_url = normalize_ws(
        str((provided_html_soup.select_one("link[rel='canonical']") or {}).get("href", ""))
    )

    resolved_article_url = ""
    article_html = ""

    if _is_ncaa_article_url(source_url):
        resolved_article_url = source_url
        article_html = html
    elif _is_ncaa_article_url(canonical_url):
        resolved_article_url = canonical_url
        article_html = html
    else:
        article_url = _find_first_ncaa_article_url(html, source_url)
        if article_url:
            resolved_article_url, article_html = _fetch_html_response(article_url)
        else:
            parsed_source = urlparse(source_url)
            query = parse_qs(parsed_source.query).get("q", [""])[0]
            lucky_url = ""
            if query:
                lucky_url = f"https://www.google.com/search?btnI=I&q={query}"
            if lucky_url:
                resolved_try, html_try = _fetch_html_response(lucky_url)
                if _is_ncaa_article_url(resolved_try):
                    resolved_article_url = resolved_try
                    article_html = html_try

    if not resolved_article_url or not article_html:
        return ScrapeResult(rows=[], updated_at_raw="", updated_at_iso="")

    soup = to_soup(article_html)

    pairs = _extract_pairs_from_bracket_table(soup)
    if not pairs:
        pairs = extract_seed_team_pairs(soup)
    if not pairs:
        pairs = _extract_seed_team_pairs_from_text(soup.get_text("\n", strip=True))
    if not pairs:
        raise RuntimeError("NCAA parser returned no seed/team rows")

    updated_at_raw = _find_updated_date_raw(soup)
    if not updated_at_raw:
        updated_at_raw = _infer_updated_date_raw_from_article_url(resolved_article_url)
    updated_at_iso = parse_datetime_iso(updated_at_raw)

    rows = rows_from_pairs(
        source_key=source_key,
        source_name=source_name,
        source_url=resolved_article_url,
        source_updated_at_raw=updated_at_raw,
        source_updated_at_iso=updated_at_iso,
        scraped_at_iso=scraped_at_iso,
        pairs=pairs,
    )
    return ScrapeResult(rows=rows, updated_at_raw=updated_at_raw, updated_at_iso=updated_at_iso)
