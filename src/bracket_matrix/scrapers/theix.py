from __future__ import annotations

import io
import json
import os
import re
from collections import Counter
from urllib.parse import urljoin

import requests

from bracket_matrix.scrapers.common import find_updated_date_raw, normalize_ws, parse_datetime_iso, rows_from_pairs, to_soup
from bracket_matrix.types import ScrapeResult


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; WBBBracketMatrix/0.1; +https://github.com/)"
DEFAULT_OPENAI_MODEL = "gpt-4.1"
OPENAI_FALLBACK_MODELS = ["gpt-4.1", "gpt-4o", "gpt-4o-mini"]
MIN_ROWS_REQUIRED = 64
MAX_ROWS_ALLOWED = 68
TEAM_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z&'().\-\s]{1,45}$")


def _fetch_html(url: str) -> str:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": DEFAULT_USER_AGENT})
    response.raise_for_status()
    return response.text


def _fetch_image_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": DEFAULT_USER_AGENT})
    response.raise_for_status()
    return response.content


def _find_latest_article_url(category_html: str, category_url: str) -> str:
    soup = to_soup(category_html)

    selectors = [
        "article h2 a[href]",
        "article h3 a[href]",
        "article a[href]",
        "a[href*='/bracketology/']",
    ]
    for selector in selectors:
        for anchor in soup.select(selector):
            href = normalize_ws(anchor.get("href", ""))
            if not href:
                continue
            label = normalize_ws(anchor.get_text(" ", strip=True)).lower()
            href_lower = href.lower()
            if "/category/" in href_lower:
                continue
            if "bracketology" not in href_lower and "bracketology" not in label:
                continue
            return urljoin(category_url, href)
    return ""


def _find_primary_image_urls(article_html: str, article_url: str) -> list[str]:
    soup = to_soup(article_html)

    def _image_sources_from_img_tag(image_tag) -> list[tuple[str, int]]:
        src = normalize_ws(image_tag.get("src", ""))
        sources: list[tuple[str, int]] = []
        if src:
            sources.append((urljoin(article_url, src), 0))

        srcset = normalize_ws(image_tag.get("srcset", ""))
        if not srcset:
            return sources

        for item in srcset.split(","):
            pieces = item.strip().split()
            if len(pieces) < 2 or not pieces[1].endswith("w"):
                continue
            try:
                width = int(pieces[1][:-1])
            except ValueError:
                continue
            sources.append((urljoin(article_url, pieces[0]), width))
        return sources

    def _score_candidate(src: str, alt: str, classes: str, width: int) -> int:
        lowered_src = src.lower()
        lowered_alt = alt.lower()
        lowered_classes = classes.lower()
        score = 0
        if "bracket" in lowered_src or "bracket" in lowered_alt:
            score += 8
        if "featured" in lowered_classes or "wp-post-image" in lowered_classes:
            score += 4
        if re.search(r"-\d+x\d+\.[a-z]+$", lowered_src):
            score -= 2
        else:
            score += 2
        if width >= 1000:
            score += 3
        elif width >= 700:
            score += 1
        if "logo" in lowered_src or "avatar" in lowered_src or "icon" in lowered_src:
            score -= 10
        return score

    candidates: list[tuple[str, int]] = []
    best_inline_score = -999
    for image in soup.select("article img[src], main img[src], img[src]"):
        alt = normalize_ws(image.get("alt", ""))
        classes = " ".join(image.get("class", []))
        for resolved, width in _image_sources_from_img_tag(image):
            if not resolved:
                continue
            score = _score_candidate(resolved, alt, classes, width)
            candidates.append((resolved, score))
            if score > best_inline_score:
                best_inline_score = score

    og_image = soup.select_one("meta[property='og:image'][content]")
    if og_image:
        content = normalize_ws(og_image.get("content", ""))
        if content:
            og_url = urljoin(article_url, content)
            og_score = _score_candidate(og_url, "", "", 1200)
            if best_inline_score < 8:
                candidates.append((og_url, og_score))

    ordered: list[str] = []
    seen: set[str] = set()
    for url, _ in sorted(candidates, key=lambda item: item[1], reverse=True):
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _find_primary_image_url(article_html: str, article_url: str) -> str:
    ordered = _find_primary_image_urls(article_html, article_url)
    return ordered[0] if ordered else ""


def _ocr_image_text(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError as exc:
        raise RuntimeError("The IX scraper requires pillow and pytesseract for OCR") from exc

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    grayscale = ImageOps.grayscale(image)
    enlarged = grayscale.resize((grayscale.width * 2, grayscale.height * 2))

    variants = [
        enlarged,
        ImageEnhance.Contrast(enlarged).enhance(2.0),
        ImageEnhance.Sharpness(enlarged).enhance(2.0),
    ]
    configs = ["--oem 3 --psm 11", "--oem 3 --psm 12", "--oem 3 --psm 6"]

    best_text = ""
    best_score = -1
    for variant in variants:
        for config in configs:
            text = pytesseract.image_to_string(variant, config=config)
            score = len(_extract_pairs_from_ocr_text(text))
            if score > best_score:
                best_text = text
                best_score = score

    return best_text


def _looks_like_team_name(team_text: str) -> bool:
    cleaned = normalize_ws(team_text)
    if not cleaned:
        return False
    if re.search(r"\d", cleaned):
        return False
    if len(cleaned.split()) > 6:
        return False
    return bool(TEAM_NAME_PATTERN.match(cleaned))


def _clean_team_name(team_text: str) -> str:
    cleaned = normalize_ws(team_text)
    cleaned = cleaned.replace("lowa", "Iowa")
    cleaned = re.sub(r"\s+I$", "", cleaned)

    known_suffix_noise = ["Storrs", "Austin", "Norman", "Nashville", "Sacramento", "Columbus"]
    for suffix in known_suffix_noise:
        if cleaned.endswith(f" {suffix}"):
            cleaned = cleaned[: -(len(suffix) + 1)]

    return normalize_ws(cleaned)


def _extract_pairs_from_ocr_text(ocr_text: str) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []
    seen: set[tuple[int, str]] = set()

    for raw_line in ocr_text.splitlines():
        line = normalize_ws(raw_line)
        if not line:
            continue

        line = re.sub(r"\b(?:Seed|Region|Bracket|First Four|Last Four In|Last Four Byes)\b", "", line, flags=re.IGNORECASE)
        line = normalize_ws(line)
        if not line:
            continue

        for match in re.finditer(r"(?<!\d)(1[0-6]|[1-9])\s+([A-Za-z][A-Za-z&'().\-\s]{1,45}?)(?=\s+(?:1[0-6]|[1-9])\s+|$)", line):
            seed = int(match.group(1))
            team = _clean_team_name(match.group(2).strip(" -:.;,|_"))
            if not _looks_like_team_name(team):
                continue
            key = (seed, team.lower())
            if key in seen:
                continue
            seen.add(key)
            pairs.append((seed, team, False))

    return pairs


def _extract_json_array_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped
    fenced = re.search(r"```(?:json)?\s*(\[.*\])\s*```", stripped, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    bracketed = re.search(r"(\[.*\])", stripped, flags=re.DOTALL)
    if bracketed:
        return bracketed.group(1)
    return stripped


def _pairs_from_openai_content(content: str) -> list[tuple[int, str, bool]]:
    json_text = _extract_json_array_text(content)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI returned invalid JSON for The IX extraction") from exc

    if isinstance(payload, dict):
        payload = payload.get("entries", [])

    if not isinstance(payload, list):
        raise RuntimeError("OpenAI response payload is not a list")

    pairs: list[tuple[int, str, bool]] = []
    seen: set[tuple[int, str]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue

        seed_value = item.get("seed")
        team_value = item.get("team")
        play_in_value = item.get("is_play_in", False)

        if isinstance(seed_value, str):
            seed_parsed = int(seed_value) if seed_value.isdigit() else -1
        elif isinstance(seed_value, int):
            seed_parsed = seed_value
        else:
            seed_parsed = -1

        if seed_parsed < 1 or seed_parsed > 16:
            continue
        if not isinstance(team_value, str):
            continue

        cleaned_team = _clean_team_name(team_value)
        if not _looks_like_team_name(cleaned_team):
            continue

        dedupe_key = (seed_parsed, cleaned_team.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        pairs.append((seed_parsed, cleaned_team, bool(play_in_value)))

    return pairs


def _extract_pairs_with_openai(image_url: str, api_key: str, model: str) -> list[tuple[int, str, bool]]:
    base_prompt = (
        "Extract all NCAA women's bracket entries visible in this image. "
        "Return a JSON object with an `entries` array only, where each object contains: "
        "seed (int 1-16), team (string), is_play_in (boolean). "
        "Do not include regions, locations, or commentary in team names."
    )
    strict_prompt = (
        "Return between 64 and 68 total entries. Include seeds 1 through 16 with at least four entries per seed. "
        "If unsure, still provide your best team guess for each visible seed line."
    )

    model_attempts = [model]
    for fallback_model in OPENAI_FALLBACK_MODELS:
        if fallback_model not in model_attempts:
            model_attempts.append(fallback_model)

    best_pairs: list[tuple[int, str, bool]] = []
    for model_name in model_attempts:
        for prompt_suffix in ["", f" {strict_prompt}"]:
            prompt = f"{base_prompt}{prompt_suffix}"
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise data extraction assistant. Output only valid JSON.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "the_ix_bracket_entries",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "entries": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "seed": {"type": "integer", "minimum": 1, "maximum": 16},
                                            "team": {"type": "string"},
                                            "is_play_in": {"type": "boolean"},
                                        },
                                        "required": ["seed", "team", "is_play_in"],
                                        "additionalProperties": False,
                                    },
                                }
                            },
                            "required": ["entries"],
                            "additionalProperties": False,
                        },
                    },
                },
                "temperature": 0,
            }

            try:
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()
                body = response.json()
                choices = body.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                message = choices[0].get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    text_chunks = [part.get("text", "") for part in content if isinstance(part, dict)]
                    content = "\n".join(chunk for chunk in text_chunks if chunk)
                if not isinstance(content, str) or not content.strip():
                    continue
                pairs = _pairs_from_openai_content(content)
            except Exception:  # noqa: BLE001
                continue

            if len(pairs) > len(best_pairs):
                best_pairs = pairs
            try:
                _validate_bracket_quality(pairs)
                return pairs
            except RuntimeError:
                continue

    return best_pairs


def _validate_bracket_quality(pairs: list[tuple[int, str, bool]]) -> None:
    if len(pairs) > MAX_ROWS_ALLOWED:
        raise RuntimeError(f"The IX parser returned too many rows ({len(pairs)} > {MAX_ROWS_ALLOWED})")

    seed_counts = Counter(seed for seed, _, _ in pairs)
    for seed in range(1, 17):
        if seed_counts.get(seed, 0) < 4:
            raise RuntimeError(f"The IX parser returned too few teams for seed {seed}")


def _apply_the_ix_known_corrections(pairs: list[tuple[int, str, bool]]) -> list[tuple[int, str, bool]]:
    """Apply temporary source-specific fixes for known model misreads.

    TODO: Replace these hardcoded corrections with a more robust image extraction
    strategy (higher-fidelity parsing and/or structured post-processing) so this
    function can be removed.
    """
    has_nc_state = any(team == "NC State" for _, team, _ in pairs)

    corrected: list[tuple[int, str, bool]] = []
    seen: set[tuple[int, str]] = set()

    for seed, team, is_play_in in pairs:
        corrected_team = team
        if team == "Illinois State":
            corrected_team = "Illinois"
        if not has_nc_state and team == "North Carolina" and seed == 4:
            corrected_team = "NC State"

        dedupe_key = (seed, corrected_team.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        corrected.append((seed, corrected_team, is_play_in))

    return corrected


def parse_the_ix(
    *,
    source_key: str,
    source_name: str,
    source_url: str,
    html: str,
    scraped_at_iso: str,
) -> ScrapeResult:
    latest_article_url = _find_latest_article_url(html, source_url)
    if not latest_article_url:
        raise RuntimeError("Unable to find latest The IX bracketology article URL")

    article_html = _fetch_html(latest_article_url)
    image_urls = _find_primary_image_urls(article_html, latest_article_url)
    if not image_urls:
        raise RuntimeError("Unable to find bracket image URL in latest The IX article")
    image_url = image_urls[0]

    pairs: list[tuple[int, str, bool]] = []
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_api_key:
        openai_model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
        for candidate_image_url in image_urls[:3]:
            try:
                candidate_pairs = _extract_pairs_with_openai(
                    image_url=candidate_image_url,
                    api_key=openai_api_key,
                    model=openai_model,
                )
            except Exception:  # noqa: BLE001
                continue
            if len(candidate_pairs) > len(pairs):
                pairs = candidate_pairs
                image_url = candidate_image_url
            try:
                _validate_bracket_quality(candidate_pairs)
                pairs = candidate_pairs
                image_url = candidate_image_url
                break
            except RuntimeError:
                continue

    if len(pairs) < MIN_ROWS_REQUIRED:
        image_bytes = _fetch_image_bytes(image_url)
        ocr_text = _ocr_image_text(image_bytes)
        ocr_pairs = _extract_pairs_from_ocr_text(ocr_text)
        if len(ocr_pairs) > len(pairs):
            pairs = ocr_pairs

    if len(pairs) < MIN_ROWS_REQUIRED:
        raise RuntimeError("The IX parser returned too few seed/team rows")

    pairs = _apply_the_ix_known_corrections(pairs)
    _validate_bracket_quality(pairs)

    article_soup = to_soup(article_html)
    updated_raw = find_updated_date_raw(article_soup)
    updated_iso = parse_datetime_iso(updated_raw)

    rows = rows_from_pairs(
        source_key=source_key,
        source_name=source_name,
        source_url=latest_article_url,
        source_updated_at_raw=updated_raw,
        source_updated_at_iso=updated_iso,
        scraped_at_iso=scraped_at_iso,
        pairs=pairs,
    )
    return ScrapeResult(rows=rows, updated_at_raw=updated_raw, updated_at_iso=updated_iso)
