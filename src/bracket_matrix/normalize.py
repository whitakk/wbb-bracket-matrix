from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bracket_matrix.io_utils import read_dict_csv
from bracket_matrix.types import TeamIdentity

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover
    fuzz = None
    process = None


ABBREV_PATTERNS = [
    (re.compile(r"\bn\.\s*c\.\b", flags=re.IGNORECASE), "north carolina"),
    (re.compile(r"\bn\s+c\b", flags=re.IGNORECASE), "north carolina"),
    (re.compile(r"\bnc\b", flags=re.IGNORECASE), "north carolina"),
    (re.compile(r"\bst\b", flags=re.IGNORECASE), "state"),
]

PLACEHOLDER_PATTERNS = [
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in [
        r"\bAQ\b",
        r"automatic bid",
        r"conference winner",
        r"\bTBD\b",
        r"play-?in winner",
        r"at-?large",
        r"^\d[\d,\s]+$",
        r"\b(?:am|pm)\s*et\b",
        r"^(atlantic 10|big east|ivy league|maac|summit league|sun belt|wcc|big sky|mac|mountain west|cusa|american|big west|mvc|ovc|southland|america east|caa|wac|horizon|asun|patriot|meac|swac|nec|big south|socon|acc|sec|big ten|big 12|pac-12|pac 12)$",
    ]
]


@dataclass(slots=True)
class AliasEntry:
    alias: str
    identity: TeamIdentity


@dataclass(slots=True)
class TeamResolution:
    identity: TeamIdentity
    method: str
    confidence: float


@dataclass(slots=True)
class UnresolvedMatch:
    team_raw: str
    normalized: str
    best_match_slug: str
    best_score: float
    second_score: float
    reason: str


def normalize_team_name(name: str) -> str:
    normalized = name.lower().replace("&", " and ")
    normalized = re.sub(r"[.,'()]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for pattern, replacement in ABBREV_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def slugify(name: str) -> str:
    normalized = normalize_team_name(name)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized)
    return slug.strip("-")


def is_placeholder_team(name: str) -> bool:
    cleaned = name.strip()
    if not cleaned:
        return True
    return any(pattern.search(cleaned) for pattern in PLACEHOLDER_PATTERNS)


def load_aliases(path: Path) -> list[AliasEntry]:
    rows = read_dict_csv(path)
    aliases: list[AliasEntry] = []
    for row in rows:
        alias = (row.get("alias") or "").strip()
        if not alias:
            continue
        identity = TeamIdentity(
            canonical_slug=(row.get("canonical_slug") or slugify(alias)).strip(),
            team_display=(row.get("team_display") or alias).strip(),
            ncaa_id=(row.get("ncaa_id") or "").strip(),
            espn_id=(row.get("espn_id") or "").strip(),
        )
        aliases.append(AliasEntry(alias=alias, identity=identity))
    return aliases


def _score_candidates(query: str, candidates: list[str]) -> tuple[float, float, int]:
    if not candidates:
        return 0.0, 0.0, -1

    if process is not None and fuzz is not None:
        matches = process.extract(query, candidates, scorer=fuzz.ratio, limit=2)
        if not matches:
            return 0.0, 0.0, -1
        best = matches[0]
        best_index = candidates.index(best[0])
        second_score = float(matches[1][1]) if len(matches) > 1 else 0.0
        return float(best[1]), second_score, best_index

    import difflib

    scores: list[tuple[float, int]] = []
    for idx, candidate in enumerate(candidates):
        score = difflib.SequenceMatcher(a=query, b=candidate).ratio() * 100
        scores.append((score, idx))
    scores.sort(reverse=True)
    best_score, best_idx = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0
    return best_score, second_score, best_idx


def resolve_team_names(
    team_names: list[str],
    aliases: list[AliasEntry],
    fuzzy_threshold: float,
    fuzzy_review_threshold: float,
    fuzzy_ambiguous_margin: float,
) -> tuple[dict[str, TeamResolution], list[UnresolvedMatch]]:
    alias_map = {normalize_team_name(entry.alias): entry.identity for entry in aliases}
    canonical_by_norm: dict[str, TeamIdentity] = {}
    canonical_norms: list[str] = []
    canonical_identities: list[TeamIdentity] = []

    for identity in alias_map.values():
        norm_display = normalize_team_name(identity.team_display)
        if norm_display not in canonical_by_norm:
            canonical_by_norm[norm_display] = identity
            canonical_norms.append(norm_display)
            canonical_identities.append(identity)

    resolved: dict[str, TeamResolution] = {}
    unresolved: list[UnresolvedMatch] = []

    for team_raw in sorted(set(team_names)):
        normalized = normalize_team_name(team_raw)

        if normalized in alias_map:
            identity = alias_map[normalized]
            resolved[team_raw] = TeamResolution(identity=identity, method="alias", confidence=100.0)
            if normalized not in canonical_by_norm:
                canonical_by_norm[normalized] = identity
                canonical_norms.append(normalized)
                canonical_identities.append(identity)
            continue

        if normalized in canonical_by_norm:
            identity = canonical_by_norm[normalized]
            resolved[team_raw] = TeamResolution(identity=identity, method="exact", confidence=100.0)
            continue

        best_score, second_score, best_index = _score_candidates(normalized, canonical_norms)
        if best_index >= 0 and best_score >= fuzzy_threshold and (best_score - second_score) >= fuzzy_ambiguous_margin:
            identity = canonical_identities[best_index]
            resolved[team_raw] = TeamResolution(identity=identity, method="fuzzy", confidence=best_score)
            canonical_by_norm[normalized] = identity
            continue

        if best_index >= 0 and (
            best_score >= fuzzy_review_threshold
            or (best_score >= fuzzy_threshold and (best_score - second_score) < fuzzy_ambiguous_margin)
        ):
            unresolved.append(
                UnresolvedMatch(
                    team_raw=team_raw,
                    normalized=normalized,
                    best_match_slug=canonical_identities[best_index].canonical_slug,
                    best_score=round(best_score, 2),
                    second_score=round(second_score, 2),
                    reason="ambiguous_or_low_confidence",
                )
            )
            continue

        identity = TeamIdentity(canonical_slug=slugify(team_raw), team_display=team_raw)
        resolved[team_raw] = TeamResolution(identity=identity, method="new", confidence=100.0)
        canonical_by_norm[normalized] = identity
        canonical_norms.append(normalized)
        canonical_identities.append(identity)

    return resolved, unresolved
