from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.events.helpers import make_features

from market_sentinel.clock import FakeClock
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.telemetry.collector import (
    FailOpenTelemetryCollector,
    SinkTelemetryCollector,
)
from market_sentinel.telemetry.contract import (
    TELEMETRY_ALLOWLIST,
    TELEMETRY_DENYLIST,
    TelemetryEvent,
    TelemetryKind,
    TelemetryName,
)
from market_sentinel.telemetry.factory import jsonl_telemetry_runtime
from market_sentinel.telemetry.jsonl import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    JsonlTelemetrySink,
    read_jsonl,
    rotated_paths,
)
from market_sentinel.telemetry.paths import (
    DATA_DIR_ENV,
    feedback_jsonl_path,
    resolve_data_dir,
    telemetry_jsonl_path,
)
from market_sentinel.telemetry.runtime import TelemetryRuntime


def _event(run_id: str = "run-1", **overrides: object) -> TelemetryEvent:
    payload: dict[str, object] = {
        "telemetry_id": "t1",
        "name": TelemetryName.EVENT_GENERATED,
        "kind": TelemetryKind.PIPELINE,
        "created_timestamp": 1.0,
        "run_id": run_id,
        "symbol": "00700.HK",
        "event_id": "e1",
        "event_type": "rapid_move",
        "market_timestamp": 2.0,
    }
    payload.update(overrides)
    return TelemetryEvent(**payload)  # type: ignore[arg-type]


def test_append_order_and_utf8(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path, max_bytes=10_000, backup_count=2)
    collector = SinkTelemetryCollector(sink)
    collector.record(_event(telemetry_id="a", symbol="测试"))
    collector.record(_event(telemetry_id="b", event_id="e2"))
    collector.close()
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert "测试" in text
    result = read_jsonl(path)
    assert result.healthy
    assert [row["telemetry_id"] for row in result.records] == ["a", "b"]


def test_restart_appends_rather_than_overwrites(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    first = JsonlTelemetrySink(path)
    SinkTelemetryCollector(first).record(_event(telemetry_id="one"))
    first.close()
    second = JsonlTelemetrySink(path)
    SinkTelemetryCollector(second).record(_event(telemetry_id="two"))
    second.close()
    ids = [row["telemetry_id"] for row in read_jsonl(path).records]
    assert ids == ["one", "two"]


def test_strict_allowlist_serialization(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    sink.write(_event().to_record())
    sink.close()
    line = path.read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(line)
    assert set(parsed) <= TELEMETRY_ALLOWLIST
    assert TELEMETRY_DENYLIST.isdisjoint(parsed)


def test_rotation_and_bounded_backups(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path, max_bytes=120, backup_count=2)
    collector = SinkTelemetryCollector(sink)
    for index in range(40):
        collector.record(_event(telemetry_id=f"id{index:03d}", event_id=f"e{index}"))
    collector.close()
    files = list(tmp_path.glob("telemetry.jsonl*"))
    backups = [item for item in files if item.name != "telemetry.jsonl"]
    assert len(backups) <= 2
    assert len(files) <= 3
    ordered = rotated_paths(path, backup_count=2)
    assert ordered[-1] == path
    records: list[str] = []
    for item in ordered:
        records.extend(str(row["telemetry_id"]) for row in read_jsonl(item).records)
    assert records
    assert records == sorted(records)
    assert DEFAULT_MAX_BYTES == 1_048_576
    assert DEFAULT_BACKUP_COUNT == 5


def test_trailing_incomplete_line_recovers_prior_records(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    SinkTelemetryCollector(sink).record(_event(telemetry_id="keep-1"))
    SinkTelemetryCollector(sink).record(_event(telemetry_id="keep-2"))
    sink.close()
    path.write_bytes(path.read_bytes() + b'{"partial":')
    result = read_jsonl(path)
    assert [row["telemetry_id"] for row in result.records] == ["keep-1", "keep-2"]
    assert result.skipped_trailing_partial is True
    assert result.healthy is True
    reopened = JsonlTelemetrySink(path)
    SinkTelemetryCollector(reopened).record(_event(telemetry_id="keep-3"))
    reopened.close()
    ids = [row["telemetry_id"] for row in read_jsonl(path).records]
    assert ids == ["keep-1", "keep-2", "keep-3"]


def test_middle_corruption_is_detectable(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    SinkTelemetryCollector(sink).record(_event(telemetry_id="a"))
    SinkTelemetryCollector(sink).record(_event(telemetry_id="b"))
    sink.close()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    lines.insert(1, "{not-json}\n")
    path.write_text("".join(lines), encoding="utf-8")
    result = read_jsonl(path)
    assert result.healthy is False
    assert result.malformed_complete_lines == 1
    assert [row["telemetry_id"] for row in result.records] == ["a", "b"]


def test_storage_failure_does_not_change_pipeline_facts(tmp_path: Path) -> None:
    del tmp_path
    clock = FakeClock(wall=10.0, monotonic=0.0)

    class BoomSink:
        def write(self, record: dict[str, object]) -> None:
            raise OSError("disk full")

        def close(self) -> None:
            return None

    runtime = TelemetryRuntime(
        clock, FailOpenTelemetryCollector(SinkTelemetryCollector(BoomSink()))
    )
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    assert result.alert_candidates


def test_no_stdout_pollution(tmp_path: Path, capsys) -> None:
    runtime = jsonl_telemetry_runtime(FakeClock(), data_dir=tmp_path)
    runtime.emit(
        TelemetryName.ALERT_BADGE_RESET,
        host_action="reset_unread",
    )
    runtime.close()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert telemetry_jsonl_path(tmp_path).exists()


def test_raw_file_has_no_denylisted_fields(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    SinkTelemetryCollector(sink).record(_event())
    sink.close()
    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw.splitlines()[0])
    assert set(parsed) <= TELEMETRY_ALLOWLIST
    for denied in TELEMETRY_DENYLIST:
        assert f'"{denied}"' not in raw


def test_data_dir_override_does_not_use_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "local-data"
    assert resolve_data_dir(data) == data
    runtime = jsonl_telemetry_runtime(FakeClock(), data_dir=data)
    runtime.emit(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread")
    runtime.close()
    assert telemetry_jsonl_path(data).is_file()
    assert not (tmp_path / "telemetry.jsonl").exists()
    assert not feedback_jsonl_path(data).exists()


def test_factory_uses_env_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "from-env"
    monkeypatch.setenv(DATA_DIR_ENV, str(target))
    runtime = jsonl_telemetry_runtime(FakeClock())
    runtime.emit(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread")
    runtime.close()
    assert telemetry_jsonl_path(target).is_file()
    assert not (tmp_path / "telemetry.jsonl").exists()


def test_one_emit_writes_exactly_one_line(tmp_path: Path) -> None:
    runtime = jsonl_telemetry_runtime(FakeClock(), data_dir=tmp_path)
    runtime.emit(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread")
    runtime.close()
    lines = [
        line
        for line in telemetry_jsonl_path(tmp_path).read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(lines) == 1


def test_write_strips_unknown_keys(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    payload = dict(_event().to_record())
    payload["extra_field"] = "nope"
    sink.write(payload)
    sink.close()
    parsed = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert "extra_field" not in parsed
    assert set(parsed) <= TELEMETRY_ALLOWLIST


def test_write_rejects_denylist_keys(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    payload = dict(_event().to_record())
    payload["workspace"] = "/secret"
    with pytest.raises(ValueError, match="denied"):
        sink.write(payload)
    sink.close()


def test_valid_json_missing_newline_is_repaired(tmp_path: Path) -> None:
    path = telemetry_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path)
    SinkTelemetryCollector(sink).record(_event(telemetry_id="kept"))
    sink.close()
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    reopened = JsonlTelemetrySink(path)
    reopened.close()
    assert path.read_bytes().endswith(b"\n")
    assert [row["telemetry_id"] for row in read_jsonl(path).records] == ["kept"]


def test_jsonl_runtime_fail_open_when_sink_cannot_open(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("x", encoding="utf-8")
    runtime = jsonl_telemetry_runtime(FakeClock(), data_dir=blocked)
    runtime.emit(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread")
    runtime.close()
    clock = FakeClock(wall=10.0, monotonic=0.0)
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    assert pipeline.process(previous, current).alert_candidates
