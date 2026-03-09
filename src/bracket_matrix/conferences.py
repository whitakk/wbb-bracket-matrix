from __future__ import annotations

import csv
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path

import requests

from bracket_matrix.normalize import load_aliases, normalize_team_name, slugify
from bracket_matrix.types import TeamIdentity


DEFAULT_BART_SEASON = 2026

TEAM_CONFERENCE_FIELDNAMES = [
    "canonical_slug",
    "team_display",
    "conference",
    "source_team",
    "source_conference",
]


def bart_results_url_for_season(season: int) -> str:
    return f"https://barttorvik.com/ncaaw/{season}_team_results.csv"


def load_team_conferences(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    by_slug: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            slug = (row.get("canonical_slug") or "").strip()
            conference = (row.get("conference") or "").strip()
            if slug and conference and slug not in by_slug:
                by_slug[slug] = conference
    return by_slug


def fetch_bart_team_results_csv(*, season: int, timeout_seconds: int, user_agent: str) -> str:
    response = requests.get(
        bart_results_url_for_season(season),
        timeout=timeout_seconds,
        headers={"User-Agent": user_agent},
    )
    response.raise_for_status()
    return response.text


def _identity_for_team_name(team_name: str, alias_identities: dict[str, TeamIdentity], canonical_identities: dict[str, TeamIdentity]) -> TeamIdentity:
    normalized = normalize_team_name(team_name)
    if normalized in alias_identities:
        return alias_identities[normalized]
    if normalized in canonical_identities:
        return canonical_identities[normalized]
    return TeamIdentity(canonical_slug=slugify(team_name), team_display=team_name)


def build_team_conference_rows_from_bart(csv_text: str, aliases_path: Path) -> list[dict[str, str]]:
    aliases = load_aliases(aliases_path)
    alias_identities = {normalize_team_name(entry.alias): entry.identity for entry in aliases}
    canonical_identities = {
        normalize_team_name(entry.identity.team_display): entry.identity for entry in aliases
    }

    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames or "team" not in reader.fieldnames or "conf" not in reader.fieldnames:
        raise ValueError("Bart CSV missing expected 'team' and 'conf' columns")

    conference_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    source_team_by_key: dict[tuple[str, str], str] = {}

    for row in reader:
        source_team = (row.get("team") or "").strip()
        source_conference = (row.get("conf") or "").strip()
        if not source_team or not source_conference:
            continue

        identity = _identity_for_team_name(source_team, alias_identities, canonical_identities)
        key = (identity.canonical_slug, identity.team_display)
        conference_counts[key][source_conference] += 1
        source_team_by_key[key] = source_team

    rows: list[dict[str, str]] = []
    for (canonical_slug, team_display), counts in sorted(conference_counts.items(), key=lambda item: item[0][1].lower()):
        conference = counts.most_common(1)[0][0]
        rows.append(
            {
                "canonical_slug": canonical_slug,
                "team_display": team_display,
                "conference": conference,
                "source_team": source_team_by_key[(canonical_slug, team_display)],
                "source_conference": conference,
            }
        )
    return rows
