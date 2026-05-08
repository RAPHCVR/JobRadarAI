from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(slots=True)
class AppConfig:
    root: Path
    profile: dict[str, Any]
    sources: dict[str, Any]
    markets: dict[str, Any]

    @property
    def output_dir(self) -> Path:
        configured = self.sources.get("run", {}).get("output_dir", "runs/latest")
        return (self.root / configured).resolve()


def load_config(root: Path | None = None, *, load_env: bool = True) -> AppConfig:
    root = root or PROJECT_ROOT
    if load_env:
        load_env_file(root / "config" / ".env")
    return AppConfig(
        root=root,
        profile=load_toml(root / "config" / "profile.toml"),
        sources=load_toml(root / "config" / "sources.toml"),
        markets=load_toml(root / "config" / "markets.toml"),
    )
