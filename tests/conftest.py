from __future__ import annotations

from pathlib import Path

import pytest

from market_sentinel.telemetry.paths import DATA_DIR_ENV


@pytest.fixture(autouse=True)
def telemetry_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every pytest from writing telemetry into the real user data directory."""
    directory = tmp_path / "ms-data"
    monkeypatch.setenv(DATA_DIR_ENV, str(directory))
    return directory
