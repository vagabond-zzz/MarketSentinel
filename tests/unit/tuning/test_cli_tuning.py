from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_sentinel.cli.main import _build_parser, _parse_corpus, main
from market_sentinel.errors import TuningConfigError
from market_sentinel.tuning.replay import default_fixture_dir


def test_tuning_snapshot_and_compare_cli(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "tuning",
                "snapshot",
                "--config-version",
                "baseline-0.5.0",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                "tuning",
                "snapshot",
                "--config-version",
                "candidate-lookback-001",
                "--config",
                str(_candidate_config(tmp_path)),
                "--source",
                "manual",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    code = main(
        [
            "tuning",
            "compare",
            "--baseline",
            first["snapshot_id"],
            "--candidate",
            second["snapshot_id"],
            "--corpus",
            "normal_market",
            "--data-dir",
            str(tmp_path),
            "--fixture-dir",
            str(default_fixture_dir()),
        ]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["corpus"] == ["normal_market"]
    assert report["schema_version"] == 2
    assert "apply" not in report
    assert report["delta"]["pipeline"]["alert_candidates"]["delta"] == 0
    assert report["delta"]["scheduler"]["processed_tick_count"]["delta"] == 0


def _candidate_config(tmp_path: Path) -> Path:
    from market_sentinel.tuning.config import capture_baseline_config

    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(capture_baseline_config().to_record()), encoding="utf-8")
    return path


def test_cli_parser_rejects_apply() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["tuning", "apply"])
    with pytest.raises(SystemExit):
        parser.parse_args(["tuning", "promote"])
    with pytest.raises(SystemExit):
        parser.parse_args(["tuning", "activate"])
    with pytest.raises(SystemExit):
        parser.parse_args(["tuning", "deploy"])


def test_parse_corpus_empty_and_duplicate_fail_closed() -> None:
    with pytest.raises(TuningConfigError, match="at least one corpus_id"):
        _parse_corpus(",,,")
    with pytest.raises(TuningConfigError, match="duplicate corpus_id"):
        _parse_corpus("rapid_move,rapid_move")


def test_cli_duplicate_corpus_exits_2(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "tuning",
                "snapshot",
                "--config-version",
                "baseline-0.5.0",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    snapshot_id = json.loads(capsys.readouterr().out)["snapshot_id"]
    code = main(
        [
            "tuning",
            "compare",
            "--baseline",
            snapshot_id,
            "--candidate",
            snapshot_id,
            "--corpus",
            "rapid_move,rapid_move",
            "--data-dir",
            str(tmp_path),
            "--fixture-dir",
            str(default_fixture_dir()),
        ]
    )
    assert code == 2


def test_cli_empty_corpus_exits_2(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "tuning",
                "snapshot",
                "--config-version",
                "baseline-0.5.0",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    snapshot_id = json.loads(capsys.readouterr().out)["snapshot_id"]
    code = main(
        [
            "tuning",
            "compare",
            "--baseline",
            snapshot_id,
            "--candidate",
            snapshot_id,
            "--corpus",
            ",,,",
            "--data-dir",
            str(tmp_path),
            "--fixture-dir",
            str(default_fixture_dir()),
        ]
    )
    assert code == 2
