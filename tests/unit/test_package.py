import tomllib
from pathlib import Path

from market_sentinel import __version__

_ROOT = Path(__file__).resolve().parents[2]


def test_package_version_matches_pyproject() -> None:
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    assert __version__ == project_version == "0.3.0"


def test_package_version_matches_uv_lock_local_package() -> None:
    with (_ROOT / "uv.lock").open("rb") as handle:
        lock = tomllib.load(handle)
    local = next(package for package in lock["package"] if package["name"] == "market-sentinel")
    assert local["version"] == __version__ == "0.3.0"
