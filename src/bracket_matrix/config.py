from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
LATEST_DIR = DATA_DIR / "latest"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SITE_DIR = ROOT_DIR / "site"


@dataclass(frozen=True)
class PipelinePaths:
    root_dir: Path
    config_dir: Path
    data_dir: Path
    latest_dir: Path
    snapshot_dir: Path
    site_dir: Path


def get_default_paths() -> PipelinePaths:
    return PipelinePaths(
        root_dir=ROOT_DIR,
        config_dir=CONFIG_DIR,
        data_dir=DATA_DIR,
        latest_dir=LATEST_DIR,
        snapshot_dir=SNAPSHOT_DIR,
        site_dir=SITE_DIR,
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_sources(paths: PipelinePaths | None = None) -> list[dict[str, Any]]:
    active_paths = paths or get_default_paths()
    config = load_json(active_paths.config_dir / "sources.json")
    return list(config.get("sources", []))


def load_settings(paths: PipelinePaths | None = None) -> dict[str, Any]:
    active_paths = paths or get_default_paths()
    return load_json(active_paths.config_dir / "settings.json")
