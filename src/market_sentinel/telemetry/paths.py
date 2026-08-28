from __future__ import annotations

import os
from pathlib import Path

DATA_DIR_ENV = "MARKET_SENTINEL_DATA_DIR"


def resolve_data_dir(override: Path | None = None) -> Path:
    """Market Sentinel local data directory. Never the repo, workspace, or cwd."""
    if override is not None:
        return override
    raw = os.environ.get(DATA_DIR_ENV, "").strip()
    if raw:
        return Path(raw)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", "").strip()
        if base:
            return Path(base) / "MarketSentinel"
        return Path.home() / "AppData" / "Local" / "MarketSentinel"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / "market-sentinel"
    return Path.home() / ".local" / "share" / "market-sentinel"


def telemetry_jsonl_path(data_dir: Path) -> Path:
    return data_dir / "telemetry.jsonl"


def feedback_jsonl_path(data_dir: Path) -> Path:
    """Explicit UserFeedback JSONL. Separate from telemetry.jsonl."""
    return data_dir / "feedback.jsonl"
