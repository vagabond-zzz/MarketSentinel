from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest
from tests.unit.events.helpers import make_features
from tests.unit.ipc.helpers import command, make_engine, parse_stdout

from market_sentinel.clock import FakeClock
from market_sentinel.ipc.daemon import MarketDaemon
from market_sentinel.ipc.protocol import PROTOCOL_VERSION
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.contract import (
    FEEDBACK_ALLOWLIST,
    TELEMETRY_DENYLIST,
    FeedbackLabel,
    TelemetryName,
    UserFeedback,
)
from market_sentinel.telemetry.factory import jsonl_telemetry_runtime
from market_sentinel.telemetry.jsonl import JsonlTelemetrySink, read_jsonl, rotated_paths
from market_sentinel.telemetry.paths import feedback_jsonl_path, telemetry_jsonl_path
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.telemetry.user_feedback import parse_user_feedback


class InMemoryFeedbackCollector:
    def __init__(self) -> None:
        self.records: list[UserFeedback] = []

    def record(self, feedback: UserFeedback) -> None:
        self.records.append(feedback)


class BoomFeedbackCollector:
    def record(self, feedback: UserFeedback) -> None:
        del feedback
        raise OSError("disk full")


def _command_body(signal_id: str = "sig-1", feedback_type: str = "useful", **extra: object) -> dict:
    payload: dict[str, object] = {
        "protocol_version": 1,
        "type": "user_feedback",
        "request_id": "r1",
        "signal_id": signal_id,
        "feedback_type": feedback_type,
        "created_timestamp": 1.5,
    }
    payload.update(extra)
    return payload


def test_feedback_taxonomy_accepts_only_frozen_labels() -> None:
    for label in FeedbackLabel:
        parsed = parse_user_feedback(_command_body(feedback_type=label.value))
        assert not isinstance(parsed, str)
        assert parsed.label is label
    error = parse_user_feedback(_command_body(feedback_type="helpful"))
    assert isinstance(error, str)
    assert "feedback_type" in error
    with pytest.raises(ValueError, match="FeedbackLabel"):
        UserFeedback(
            feedback_id="f1",
            created_timestamp=1.0,
            run_id="run-1",
            label="helpful",  # type: ignore[arg-type]
            signal_id="sig-1",
        )


def test_user_feedback_requires_signal_id() -> None:
    with pytest.raises(ValueError, match="signal_id"):
        UserFeedback(
            feedback_id="f1",
            created_timestamp=1.0,
            run_id="run-1",
            label=FeedbackLabel.USEFUL,
        )
    missing = parse_user_feedback(
        {
            "protocol_version": 1,
            "type": "user_feedback",
            "request_id": "r1",
            "feedback_type": "useful",
            "created_timestamp": 1.0,
        }
    )
    assert isinstance(missing, str)
    assert "signal_id" in missing


def test_parse_user_feedback_rejects_free_text_and_workspace() -> None:
    for extra in (
        {"comment": "too late because of code"},
        {"notes": "n"},
        {"reason": "because"},
        {"title": "alert title"},
        {"summary": "summary"},
        {"workspace": "/secret"},
        {"prompt": "why"},
    ):
        error = parse_user_feedback(_command_body(**extra))
        assert isinstance(error, str)


def test_parse_user_feedback_keeps_protocol_version_one() -> None:
    parsed = parse_user_feedback(_command_body())
    assert not isinstance(parsed, str)
    assert PROTOCOL_VERSION == 1


def test_explicit_actions_only_create_feedback() -> None:
    clock = FakeClock()
    memory = InMemoryTelemetryCollector()
    feedback = InMemoryFeedbackCollector()
    runtime = TelemetryRuntime(clock, memory, feedback=feedback)
    runtime.emit(TelemetryName.ALERT_PRESENTED, signal_id="sig-1", host_action="presented")
    runtime.emit(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread")
    runtime.emit(TelemetryName.INTELLIGENCE_SUCCEEDED, signal_id="sig-1")
    assert feedback.records == []
    written = runtime.record_feedback(
        signal_id="sig-1",
        label=FeedbackLabel.USEFUL,
        created_timestamp=3.0,
    )
    assert len(feedback.records) == 1
    assert feedback.records[0] is written
    assert written.label is FeedbackLabel.USEFUL
    assert written.signal_id == "sig-1"
    assert written.run_id == runtime.run_id
    assert memory.events[-1].name is TelemetryName.INTELLIGENCE_SUCCEEDED


@pytest.mark.asyncio
async def test_host_interaction_does_not_write_feedback() -> None:
    memory = InMemoryTelemetryCollector()
    feedback = InMemoryFeedbackCollector()
    clock, _, engine = make_engine()
    engine.telemetry.close()
    engine.telemetry = TelemetryRuntime(
        clock, memory, feedback=feedback, run_id=engine.telemetry.run_id
    )
    stdin = io.StringIO(
        "".join(
            [
                command("hello", "h1"),
                command(
                    "host_interaction",
                    "p1",
                    action="alert_presented",
                    signal_id="sig-1",
                    created_timestamp=1.5,
                ),
                command(
                    "host_interaction",
                    "r1",
                    action="alert_badge_reset",
                    created_timestamp=2.0,
                ),
                command("shutdown", "x"),
            ]
        )
    )
    stdout = io.StringIO()
    await asyncio.wait_for(MarketDaemon(engine, stdin=stdin, stdout=stdout).run(), timeout=5)
    assert feedback.records == []
    assert [item.name for item in memory.events]


@pytest.mark.asyncio
async def test_user_feedback_command_appends_one_record() -> None:
    feedback = InMemoryFeedbackCollector()
    clock, _, engine = make_engine()
    engine.telemetry.close()
    engine.telemetry = TelemetryRuntime(clock, feedback=feedback, run_id="run-core")
    stdin = io.StringIO(
        "".join(
            [
                command("hello", "h1"),
                command(
                    "user_feedback",
                    "f1",
                    signal_id="sig-9",
                    feedback_type="too_late",
                    created_timestamp=4.0,
                ),
                command("shutdown", "x"),
            ]
        )
    )
    stdout = io.StringIO()
    await asyncio.wait_for(MarketDaemon(engine, stdin=stdin, stdout=stdout).run(), timeout=5)
    messages = parse_stdout(stdout.getvalue())
    ack = next(item for item in messages if item.get("request_id") == "f1")
    assert ack["type"] == "ack"
    assert ack["protocol_version"] == 1
    assert len(feedback.records) == 1
    item = feedback.records[0]
    assert item.signal_id == "sig-9"
    assert item.label is FeedbackLabel.TOO_LATE
    assert item.run_id == "run-core"
    assert item.created_timestamp == 4.0
    assert item.symbol is None
    assert item.event_id is None


@pytest.mark.asyncio
async def test_user_feedback_rejects_invalid_enum_and_keeps_old_commands() -> None:
    feedback = InMemoryFeedbackCollector()
    clock, _, engine = make_engine()
    engine.telemetry.close()
    engine.telemetry = TelemetryRuntime(clock, feedback=feedback)
    stdin = io.StringIO(
        "".join(
            [
                command("hello", "h1"),
                command(
                    "user_feedback",
                    "bad",
                    signal_id="sig-1",
                    feedback_type="meh",
                    created_timestamp=1.0,
                ),
                command(
                    "host_interaction",
                    "ok",
                    action="alert_badge_reset",
                    created_timestamp=2.0,
                ),
                command("shutdown", "x"),
            ]
        )
    )
    stdout = io.StringIO()
    await asyncio.wait_for(MarketDaemon(engine, stdin=stdin, stdout=stdout).run(), timeout=5)
    messages = parse_stdout(stdout.getvalue())
    error = next(item for item in messages if item.get("request_id") == "bad")
    assert error["type"] == "error"
    assert error["code"] == "invalid_payload"
    assert error["protocol_version"] == 1
    ack = next(item for item in messages if item.get("request_id") == "ok")
    assert ack["type"] == "ack"
    assert feedback.records == []


def test_duplicate_feedback_is_append_only() -> None:
    clock = FakeClock()
    feedback = InMemoryFeedbackCollector()
    runtime = TelemetryRuntime(clock, feedback=feedback, run_id="run-1")
    runtime.record_feedback(signal_id="sig-1", label=FeedbackLabel.USEFUL, created_timestamp=1.0)
    runtime.record_feedback(signal_id="sig-1", label=FeedbackLabel.TOO_NOISY, created_timestamp=2.0)
    assert [item.label for item in feedback.records] == [
        FeedbackLabel.USEFUL,
        FeedbackLabel.TOO_NOISY,
    ]
    assert feedback.records[0].feedback_id != feedback.records[1].feedback_id


def test_feedback_jsonl_separated_from_telemetry(tmp_path: Path) -> None:
    runtime = jsonl_telemetry_runtime(FakeClock(), data_dir=tmp_path)
    runtime.emit(TelemetryName.ALERT_PRESENTED, signal_id="sig-1", host_action="presented")
    assert telemetry_jsonl_path(tmp_path).is_file()
    assert not feedback_jsonl_path(tmp_path).exists()
    runtime.record_feedback(signal_id="sig-1", label=FeedbackLabel.USEFUL, created_timestamp=1.0)
    runtime.close()
    feedback_path = feedback_jsonl_path(tmp_path)
    assert feedback_path.is_file()
    tel = [json.loads(line) for line in telemetry_jsonl_path(tmp_path).read_text().splitlines()]
    fb = [json.loads(line) for line in feedback_path.read_text(encoding="utf-8").splitlines()]
    assert all("name" in row for row in tel)
    assert all(row.get("label") == "useful" for row in fb)
    assert all("name" not in row for row in fb)
    raw = feedback_path.read_text(encoding="utf-8")
    for denied in TELEMETRY_DENYLIST:
        assert f'"{denied}"' not in raw
    assert set(fb[0]) <= FEEDBACK_ALLOWLIST
    assert "comment" not in raw
    assert "title" not in raw


def test_feedback_jsonl_restart_append_rotation_and_corruption(tmp_path: Path) -> None:
    path = feedback_jsonl_path(tmp_path)
    first = JsonlTelemetrySink(path, allowlist=FEEDBACK_ALLOWLIST, max_bytes=10_000)
    runtime = TelemetryRuntime(
        FakeClock(),
        feedback=_sink_feedback(first),
        run_id="run-1",
    )
    runtime.record_feedback(signal_id="sig-1", label=FeedbackLabel.USEFUL, created_timestamp=1.0)
    runtime.close()
    second = JsonlTelemetrySink(path, allowlist=FEEDBACK_ALLOWLIST, max_bytes=10_000)
    TelemetryRuntime(
        FakeClock(),
        feedback=_sink_feedback(second),
        run_id="run-1",
    ).record_feedback(signal_id="sig-1", label=FeedbackLabel.TOO_NOISY, created_timestamp=2.0)
    second.close()
    labels = [row["label"] for row in read_jsonl(path).records]
    assert labels == ["useful", "too_noisy"]

    rotating = JsonlTelemetrySink(path, allowlist=FEEDBACK_ALLOWLIST, max_bytes=180, backup_count=2)
    collector = _sink_feedback(rotating)
    clock = FakeClock()
    busy = TelemetryRuntime(clock, feedback=collector, run_id="run-1")
    for index in range(30):
        busy.record_feedback(
            signal_id=f"sig-{index}",
            label=FeedbackLabel.NOT_USEFUL,
            created_timestamp=float(index),
        )
    busy.close()
    files = list(tmp_path.glob("feedback.jsonl*"))
    backups = [item for item in files if item.name != "feedback.jsonl"]
    assert len(backups) <= 2
    ordered = rotated_paths(path, backup_count=2)
    assert ordered[-1] == path

    current = feedback_jsonl_path(tmp_path / "corrupt")
    sink = JsonlTelemetrySink(current, allowlist=FEEDBACK_ALLOWLIST)
    TelemetryRuntime(FakeClock(), feedback=_sink_feedback(sink), run_id="run-1").record_feedback(
        signal_id="a", label=FeedbackLabel.USEFUL, created_timestamp=1.0
    )
    sink.close()
    current.write_bytes(current.read_bytes() + b'{"partial":')
    trailing = read_jsonl(current)
    assert trailing.skipped_trailing_partial is True
    assert trailing.healthy is True
    repaired = JsonlTelemetrySink(current, allowlist=FEEDBACK_ALLOWLIST)
    TelemetryRuntime(
        FakeClock(), feedback=_sink_feedback(repaired), run_id="run-1"
    ).record_feedback(signal_id="b", label=FeedbackLabel.TOO_LATE, created_timestamp=2.0)
    repaired.close()
    assert [row["signal_id"] for row in read_jsonl(current).records] == ["a", "b"]

    middle = feedback_jsonl_path(tmp_path / "middle")
    JsonlTelemetrySink(middle, allowlist=FEEDBACK_ALLOWLIST).close()
    middle.write_bytes(
        b'{"feedback_id":"a","created_timestamp":1,"run_id":"r","label":"useful",'
        b'"signal_id":"s1"}\n{not-json}\n{"feedback_id":"b","created_timestamp":2,'
        b'"run_id":"r","label":"useful","signal_id":"s2"}\n'
    )
    bad = read_jsonl(middle)
    assert bad.healthy is False
    assert bad.malformed_complete_lines == 1
    utf = feedback_jsonl_path(tmp_path / "utf")
    utf.parent.mkdir(parents=True, exist_ok=True)
    utf.write_bytes(
        b'{"feedback_id":"a","created_timestamp":1,"run_id":"r","label":"useful",'
        b'"signal_id":"s1"}\n\xff\n{"feedback_id":"b","created_timestamp":2,'
        b'"run_id":"r","label":"useful","signal_id":"s2"}\n'
    )
    utf_result = read_jsonl(utf)
    assert utf_result.healthy is False
    assert utf_result.malformed_complete_lines == 1


def test_feedback_write_rejects_denylist_and_strips_unknown(tmp_path: Path) -> None:
    path = feedback_jsonl_path(tmp_path)
    sink = JsonlTelemetrySink(path, allowlist=FEEDBACK_ALLOWLIST)
    record = UserFeedback(
        feedback_id="f1",
        created_timestamp=1.0,
        run_id="run-1",
        label=FeedbackLabel.USEFUL,
        signal_id="sig-1",
    ).to_record()
    extra = dict(record)
    extra["extra_field"] = "nope"
    sink.write(extra)
    denied = dict(record)
    denied["workspace"] = "/secret"
    with pytest.raises(ValueError, match="denied"):
        sink.write(denied)
    sink.close()
    parsed = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert "extra_field" not in parsed
    assert set(parsed) <= FEEDBACK_ALLOWLIST


def test_feedback_storage_failure_does_not_break_pipeline(capsys) -> None:
    clock = FakeClock(wall=10.0, monotonic=0.0)
    runtime = TelemetryRuntime(clock, feedback=BoomFeedbackCollector())
    with pytest.raises(OSError, match="disk full"):
        runtime.record_feedback(
            signal_id="sig-1", label=FeedbackLabel.USEFUL, created_timestamp=1.0
        )
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    assert pipeline.process(previous, current).alert_candidates
    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.asyncio
async def test_feedback_command_failure_does_not_crash_daemon_or_pollute_stdout() -> None:
    clock, _, engine = make_engine()
    engine.telemetry.close()
    engine.telemetry = TelemetryRuntime(clock, feedback=BoomFeedbackCollector())
    stdin = io.StringIO(
        "".join(
            [
                command("hello", "h1"),
                command("start", "s1"),
                command(
                    "user_feedback",
                    "f1",
                    signal_id="sig-1",
                    feedback_type="useful",
                    created_timestamp=1.0,
                ),
                command("get_state", "g1"),
                command("shutdown", "x"),
            ]
        )
    )
    stdout = io.StringIO()
    await asyncio.wait_for(MarketDaemon(engine, stdin=stdin, stdout=stdout).run(), timeout=5)
    messages = parse_stdout(stdout.getvalue())
    failed = next(item for item in messages if item.get("request_id") == "f1")
    assert failed["type"] == "error"
    state = next(item for item in messages if item.get("request_id") == "g1")
    assert state["type"] == "state"
    for line in stdout.getvalue().splitlines():
        if line.strip():
            json.loads(line)


def _sink_feedback(sink: JsonlTelemetrySink):
    from market_sentinel.telemetry.collector import SinkFeedbackCollector

    return SinkFeedbackCollector(sink)
