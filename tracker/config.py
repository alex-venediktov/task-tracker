"""Настройки службы из окружения, префикс TT_."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    public_url: str
    git: bool
    port: int
    host: str = "127.0.0.1"


def load() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("TT_DATA_DIR", "data")),
        public_url=os.environ.get("TT_PUBLIC_URL", "").rstrip("/"),
        git=os.environ.get("TT_GIT", "1").strip().lower() not in ("0", "false", "no", "off"),
        port=int(os.environ.get("TT_PORT", "8113")),
        host=os.environ.get("TT_HOST", "127.0.0.1").strip() or "127.0.0.1",
    )
