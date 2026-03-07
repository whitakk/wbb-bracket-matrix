from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def utc_compact_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def ensure_dirs(paths: list[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def write_dict_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and fieldnames is None:
        raise ValueError("fieldnames are required when writing an empty csv")
    headers = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def read_dict_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def cleanup_old_csv(snapshot_dir: Path, prefix: str, retention_days: int) -> list[Path]:
    cutoff = datetime.now(UTC).timestamp() - (retention_days * 86400)
    deleted: list[Path] = []
    for candidate in snapshot_dir.glob(f"{prefix}_*.csv"):
        if candidate.stat().st_mtime < cutoff:
            candidate.unlink(missing_ok=True)
            deleted.append(candidate)
    return deleted
