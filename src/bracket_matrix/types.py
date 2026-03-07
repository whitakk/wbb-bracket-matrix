from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceProjectionRow:
    source_key: str
    source_name: str
    source_url: str
    source_updated_at_raw: str
    source_updated_at_iso: str
    team_raw: str
    seed: int
    is_play_in: bool
    scraped_at_iso: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TeamIdentity:
    canonical_slug: str
    team_display: str
    ncaa_id: str = ""
    espn_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatrixRow:
    canonical_slug: str
    team_display: str
    ncaa_id: str
    espn_id: str
    appearances: int
    avg_seed: float
    source_seeds: dict[str, int | None] = field(default_factory=dict)

    def to_flat_dict(self, source_keys: list[str]) -> dict[str, Any]:
        row: dict[str, Any] = {
            "canonical_slug": self.canonical_slug,
            "team_display": self.team_display,
            "ncaa_id": self.ncaa_id,
            "espn_id": self.espn_id,
            "appearances": self.appearances,
            "avg_seed": round(self.avg_seed, 3),
        }
        for source_key in source_keys:
            seed = self.source_seeds.get(source_key)
            row[source_key] = "" if seed is None else int(seed)
        return row


@dataclass(slots=True)
class SourceMeta:
    source_key: str
    source_name: str
    source_url: str
    source_updated_at_raw: str
    source_updated_at_iso: str
    scraped_at_iso: str
    status: str
    error_message: str
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScrapeResult:
    rows: list[SourceProjectionRow]
    updated_at_raw: str
    updated_at_iso: str
