from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from market_sentinel.telemetry.contract import TuningSource
from market_sentinel.tuning.compare import compare_artifacts
from market_sentinel.tuning.config import (
    OFFLINE_TUNING_CONFIG_ALLOWLIST,
    capture_baseline_config,
    tuning_parameter_inventory,
)
from market_sentinel.tuning.replay import default_fixture_dir
from market_sentinel.tuning.store import make_artifact

FIXTURES = default_fixture_dir()


@dataclass(frozen=True)
class SensitivityCase:
    parameter: str
    corpus_id: str
    candidate_value: object
    metric_section: str
    metric_name: str


SENSITIVITY_CASES: tuple[SensitivityCase, ...] = (
    SensitivityCase(
        "cluster_lookback_s",
        "tuning_cluster_lookback",
        1.0,
        "pipeline",
        "signal_episodes_created",
    ),
    SensitivityCase(
        "hot_event_severity",
        "tuning_hot_event_severity",
        5,
        "scheduler",
        "hot_tick_count",
    ),
    SensitivityCase(
        "hot_volume_ratio_5m",
        "tuning_hot_volume_ratio_5m",
        10.0,
        "scheduler",
        "hot_tick_count",
    ),
    SensitivityCase(
        "hot_change_5m",
        "tuning_hot_change_5m",
        0.008,
        "scheduler",
        "hot_tick_count",
    ),
    SensitivityCase(
        "warm_change_1m",
        "pre_signal_warm",
        0.99,
        "scheduler",
        "warm_tick_count",
    ),
    SensitivityCase(
        "warm_change_5m",
        "tuning_hot_change_5m",
        0.99,
        "scheduler",
        "warm_tick_count",
    ),
    SensitivityCase(
        "warm_volume_ratio",
        "tuning_warm_volume_ratio",
        99.0,
        "scheduler",
        "warm_tick_count",
    ),
)


def test_every_supported_parameter_has_sensitivity_evidence() -> None:
    supported = {item.name for item in tuning_parameter_inventory() if item.status == "supported"}
    evidence = {case.parameter for case in SENSITIVITY_CASES}
    names = [case.parameter for case in SENSITIVITY_CASES]
    assert supported == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)
    assert supported == evidence
    assert len(names) == len(set(names))


def _artifact(config=None, *, version: str = "baseline-0.5.0"):
    return make_artifact(
        config if config is not None else capture_baseline_config(),
        config_version=version,
        source=TuningSource.OFFLINE_EVAL,
    )


@pytest.mark.parametrize("case", SENSITIVITY_CASES, ids=lambda case: case.parameter)
async def test_supported_parameter_sensitivity_visible_in_report(
    tmp_path: Path, case: SensitivityCase
) -> None:
    candidate = replace(capture_baseline_config(), **{case.parameter: case.candidate_value})
    report = await compare_artifacts(
        _artifact(),
        _artifact(candidate, version=f"candidate-{case.parameter}"),
        corpus=(case.corpus_id,),
        fixture_dir=FIXTURES,
        work_dir=tmp_path,
    )
    record = report.to_record()
    delta = record["delta"][case.metric_section][case.metric_name]["delta"]
    assert delta != 0
    fixture = record["per_fixture"][0]
    assert fixture["delta"][case.metric_section][case.metric_name]["delta"] != 0
