from __future__ import annotations

from collections import defaultdict
from statistics import mean

from bracket_matrix.normalize import TeamResolution
from bracket_matrix.types import MatrixRow, SeedValue, SourceProjectionRow


def build_matrix_rows(
    rows: list[SourceProjectionRow],
    resolutions: dict[str, TeamResolution],
    source_keys: list[str],
) -> list[MatrixRow]:
    matrix_map: dict[str, MatrixRow] = {}
    seeds_by_team_source: dict[tuple[str, str], list[SeedValue]] = defaultdict(list)

    for row in rows:
        resolution = resolutions.get(row.team_raw)
        if resolution is None:
            continue
        identity = resolution.identity
        key = identity.canonical_slug
        if key not in matrix_map:
            matrix_map[key] = MatrixRow(
                canonical_slug=identity.canonical_slug,
                team_display=identity.team_display,
                ncaa_id=identity.ncaa_id,
                espn_id=identity.espn_id,
                appearances=0,
                avg_seed=99.0,
                source_seeds={source_key: None for source_key in source_keys},
            )
        seeds_by_team_source[(key, row.source_key)].append(row.seed)

    def _best_source_value(values: list[SeedValue]) -> SeedValue:
        numeric_values = [value for value in values if isinstance(value, int)]
        if numeric_values:
            return min(numeric_values)
        if "FFO" in values:
            return "FFO"
        return "NFO"

    for (canonical_slug, source_key), values in seeds_by_team_source.items():
        if canonical_slug not in matrix_map:
            continue
        matrix_map[canonical_slug].source_seeds[source_key] = _best_source_value(values)

    matrix_rows: list[MatrixRow] = []
    for matrix_row in matrix_map.values():
        available = [seed for seed in matrix_row.source_seeds.values() if isinstance(seed, int)]
        matrix_row.appearances = len(available)
        matrix_row.avg_seed = mean(available) if available else 99.0
        matrix_rows.append(matrix_row)

    matrix_rows.sort(key=lambda item: (item.avg_seed, -item.appearances, item.team_display.lower()))
    return matrix_rows
