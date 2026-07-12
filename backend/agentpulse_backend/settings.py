"""Backend settings from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    db_path: str = "./data/agentpulse.db"
    public_base_url: str = "http://localhost:8000"


def load_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("AGENTPULSE_BACKEND_DB", "./data/agentpulse.db"),
        public_base_url=os.environ.get(
            "AGENTPULSE_PUBLIC_BASE_URL", "http://localhost:8000"
        ),
    )
