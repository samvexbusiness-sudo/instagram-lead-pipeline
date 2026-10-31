"""Settings, paths and secrets. Pure Python, no network."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(os.environ.get("LEADPIPE_ROOT", Path(__file__).resolve().parents[2]))


@dataclass(frozen=True)
class Paths:
    root: Path
    data_dir: Path | None = None  # override, e.g. data/demo for the offline demo

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def data(self) -> Path:
        return self.data_dir or self.root / "data"

    @property
    def leads_db(self) -> Path:
        return self.data / "leads.json"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def ledger(self) -> Path:
        return self.data / "spend_ledger.jsonl"

    @property
    def exports(self) -> Path:
        return self.data / "exports"

    @property
    def handoff(self) -> Path:
        return self.data / "handoff"


def load_env(root: Path) -> None:
    """Read KEY=VALUE lines from .env into os.environ (doesn't override real env vars)."""
    env_file = root / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Config:
    paths: Paths
    settings: dict
    hard_filters: dict
    icp_text: str
    keywords: list[str]
    do_not_contact: set[str]

    def secret(self, name: str) -> str | None:
        value = os.environ.get(name, "").strip()
        return value or None


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def load_config(root: Path | None = None, data_dir: Path | None = None) -> Config:
    paths = Paths(Path(root) if root else ROOT, Path(data_dir) if data_dir else None)
    load_env(paths.root)
    with open(paths.config / "settings.toml", "rb") as f:
        settings = tomllib.load(f)
    with open(paths.config / "icp" / "hard_filters.toml", "rb") as f:
        hard_filters = tomllib.load(f)
    icp_text = (paths.config / "icp" / "ICP_CRITERIA.md").read_text(encoding="utf-8")
    keywords = _read_lines(paths.config / "keywords.txt")
    dnc = {x.lower().lstrip("@") for x in _read_lines(paths.config / "do_not_contact.txt")}
    for p in (paths.data, paths.raw, paths.exports, paths.handoff):
        p.mkdir(parents=True, exist_ok=True)
    return Config(paths, settings, hard_filters, icp_text, keywords, dnc)
