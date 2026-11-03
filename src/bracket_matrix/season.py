from __future__ import annotations

import re
from datetime import date
from typing import Any

from bracket_matrix.scrapers.common import normalize_ws, parse_datetime_iso, to_soup


class SourceUnavailable(ValueError):
    """A provider has not yet supplied usable projections for this season."""


def validate_update_date(updated_iso: str, settings: dict[str, Any]) -> None:
    cutoff = str(settings.get("season_start_date", ""))
    if not cutoff:
        return
    date.fromisoformat(cutoff)
    if not updated_iso:
        raise SourceUnavailable("Cannot verify a current-season update date")
    if updated_iso[:10] < cutoff:
        raise SourceUnavailable(f"Previous-season data ({updated_iso[:10]}; season starts {cutoff})")


def validate_ncaa_rankings_date(html: str, settings: dict[str, Any]) -> None:
    if not settings.get("season_start_date"):
        return
    text = normalize_ws(to_soup(html).get_text(" ", strip=True))
    match = re.search(r"Through Games\s+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})", text, flags=re.IGNORECASE)
    validate_update_date(parse_datetime_iso(match.group(1)) if match else "", settings)
