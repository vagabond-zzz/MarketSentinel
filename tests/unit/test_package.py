import tomllib
from pathlib import Path

from market_sentinel import __version__

_ROOT = Path(__file__).resolve().parents[2]


def test_package_version_matches_pyproject() -> None:
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    assert __version__ == project_version == "0.2.0"
