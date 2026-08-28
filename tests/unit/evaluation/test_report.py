from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from market_sentinel.cli.main import main
from market_sentinel.evaluation.aggregate import evaluate
from market_sentinel.evaluation.reader import LoadedTelemetry, TelemetryReader
from market_sentinel.evaluation.render import render_text
from market_sentinel.evaluation.report import (
    EVALUATION_ALLOWLIST,
    UNAVAILABLE_MARKET_SCOPE,
    UNAVAILABLE_MARKET_TIME,
    UNAVAILABLE_NO_USAGE,
    UNAVAILABLE_PRODUCER,
    sanitize_report,
)
from market_sentinel.telemetry.contract import (
    FEEDBACK_ALLOWLIST,
    TELEMETRY_DENYLIST,
    DecisionReason,
    FeedbackLabel,
    LatencyStage,
    SuppressionReason,
    TelemetryEvent,
    TelemetryKind,
    TelemetryName,
    UserFeedback,
)
from market_sentinel.telemetry.jsonl import DEFAULT_BACKUP_COUNT, JsonlTelemetrySink

CST = timezone(timedelta(hours=8))
ASHARE = "600519.SH"
HK = "00700.HK"


def _ts(hour: int, minute: int = 0, day: int = 15) -> float:
    return datetime(2024, 1, day, hour, minute, tzinfo=CST).timestamp()


def _event(name: TelemetryName, **fields: object) -> dict[str, object]:
    kind = {
        TelemetryName.EVENT_GENERATED: TelemetryKind.PIPELINE,
        TelemetryName.EVENT_DEDUPED: TelemetryKind.PIPELINE,
        TelemetryName.EVENT_CLUSTERED: TelemetryKind.PIPELINE,
        TelemetryName.SIGNAL_EPISODE_CREATED: TelemetryKind.PIPELINE,
        TelemetryName.SIGNAL_ESCALATED: TelemetryKind.PIPELINE,
        TelemetryName.ALERT_CANDIDATE: TelemetryKind.PIPELINE,
        TelemetryName.ALERT_SUPPRESSED: TelemetryKind.PIPELINE,
        TelemetryName.ALERT_PRESENTED: TelemetryKind.HOST,
        TelemetryName.ALERT_BADGE_RESET: TelemetryKind.HOST,
        TelemetryName.SIGNAL_OPENED: TelemetryKind.HOST,
        TelemetryName.INTELLIGENCE_ROUTED: TelemetryKind.INTELLIGENCE,
        TelemetryName.INTELLIGENCE_SKIPPED: TelemetryKind.INTELLIGENCE,
        TelemetryName.INTELLIGENCE_SUCCEEDED: TelemetryKind.INTELLIGENCE,
        TelemetryName.INTELLIGENCE_FALLBACK: TelemetryKind.INTELLIGENCE,
        TelemetryName.INTELLIGENCE_LATENCY: TelemetryKind.INTELLIGENCE,
        TelemetryName.INTELLIGENCE_TOKEN_USAGE: TelemetryKind.INTELLIGENCE,
    }[name]
    payload: dict[str, object] = {
        "telemetry_id": str(fields.pop("telemetry_id", "t1")),
        "name": name,
        "kind": kind,
        "created_timestamp": float(fields.pop("created_timestamp", 1.0)),
        "run_id": str(fields.pop("run_id", "run-1")),
    }
    payload.update(fields)
    return TelemetryEvent(**payload).to_record()  # type: ignore[arg-type]


def _loaded(
    records: list[dict[str, object]], *, malformed: int = 0, skipped: bool = False
) -> LoadedTelemetry:
    return LoadedTelemetry(
        records=tuple(records),
        input_files=("memory",),
        records_read=len(records),
        malformed_complete_lines=malformed,
        skipped_trailing_partial=skipped,
        healthy=malformed == 0,
    )


def test_funnel_counts() -> None:
    records = [
        _event(TelemetryName.EVENT_GENERATED, event_id="e1", symbol="00700.HK"),
        _event(TelemetryName.EVENT_GENERATED, event_id="e2", symbol="00700.HK", telemetry_id="t2"),
        _event(TelemetryName.EVENT_DEDUPED, event_id="e2", symbol="00700.HK", telemetry_id="t3"),
        _event(
            TelemetryName.SIGNAL_EPISODE_CREATED,
            signal_id="s1",
            symbol="00700.HK",
            telemetry_id="t4",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol="00700.HK",
            telemetry_id="t5",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_PRESENTED,
            signal_id="s1",
            telemetry_id="t6",
        ),
    ]
    report = evaluate(_loaded(records)).to_record()
    pipe = report["pipeline"]
    assert pipe["events_generated"] == 2
    assert pipe["events_deduped"] == 1
    assert pipe["signal_episodes_created"] == 1
    assert pipe["alert_candidates"] == 1
    assert pipe["alerts_presented"] == 1
    assert pipe["dedupe_rate"] == 0.5
    assert pipe["event_to_signal_rate"] == 0.5
    assert pipe["signal_to_alert_candidate_rate"] == 1.0
    assert pipe["candidate_to_presented_rate"] == 1.0


def test_zero_denominator_returns_unavailable() -> None:
    report = evaluate(_loaded([])).to_record()
    pipe = report["pipeline"]
    assert pipe["events_generated"] == 0
    assert pipe["dedupe_rate"] is None
    assert pipe["event_to_signal_rate"] is None
    assert pipe["signal_to_alert_candidate_rate"] is None
    assert pipe["candidate_to_presented_rate"] is None
    assert pipe["alert_suppression_rate"] is None
    assert report["alert_noise"]["important_critical_ratio"] is None
    assert report["alert_noise"]["alerts_per_market_hour"]["available"] is False
    assert report["pipeline"]["cluster_tracker_seen_count"] == 0


def test_repeated_episode_definition() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="A",
            symbol="00700.HK",
            telemetry_id="a1",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="A",
            symbol="00700.HK",
            telemetry_id="a2",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="A",
            symbol="00700.HK",
            telemetry_id="a3",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="B",
            symbol="00700.HK",
            telemetry_id="b1",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="C",
            symbol="00700.HK",
            telemetry_id="c1",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="C",
            symbol="00700.HK",
            telemetry_id="c2",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_SUPPRESSED,
            signal_id="A",
            symbol="00700.HK",
            telemetry_id="sup",
            suppression_reason=SuppressionReason.COOLDOWN,
        ),
    ]
    noise = evaluate(_loaded(records)).to_record()["alert_noise"]
    assert noise["repeated_episode_signal_count"] == 2
    assert noise["repeated_episode_extra_alert_count"] == 3


def test_suppression_by_reason() -> None:
    records = [
        _event(
            TelemetryName.ALERT_SUPPRESSED,
            signal_id="s1",
            symbol="00700.HK",
            telemetry_id="c1",
            suppression_reason=SuppressionReason.COOLDOWN,
        ),
        _event(
            TelemetryName.ALERT_SUPPRESSED,
            signal_id="s1",
            symbol="00700.HK",
            telemetry_id="c2",
            suppression_reason=SuppressionReason.COOLDOWN,
        ),
        _event(
            TelemetryName.ALERT_SUPPRESSED,
            signal_id="s2",
            symbol="00700.HK",
            telemetry_id="d1",
            suppression_reason=SuppressionReason.SAME_TICK_DUPLICATE,
        ),
    ]
    noise = evaluate(_loaded(records)).to_record()["alert_noise"]
    assert noise["suppression_by_reason"] == {"cooldown": 2, "same_tick_duplicate": 1}
    assert noise["unrecognized_suppression_reason_count"] == 0


def test_priority_distribution() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="i",
            symbol="00700.HK",
            telemetry_id="1",
            priority="INFO",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="n",
            symbol="00700.HK",
            telemetry_id="2",
            priority="NOTICE",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="im",
            symbol="00700.HK",
            telemetry_id="3",
            priority="IMPORTANT",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="c",
            symbol="00700.HK",
            telemetry_id="4",
            priority="CRITICAL",
        ),
    ]
    noise = evaluate(_loaded(records)).to_record()["alert_noise"]
    assert noise["info_count"] == 1
    assert noise["notice_count"] == 1
    assert noise["important_count"] == 1
    assert noise["critical_count"] == 1
    assert noise["important_critical_ratio"] == 0.5


def test_host_unimplemented_is_unavailable_not_zero() -> None:
    records = [
        _event(TelemetryName.ALERT_PRESENTED, signal_id="s1", telemetry_id="p1"),
        _event(TelemetryName.ALERT_BADGE_RESET, telemetry_id="r1", host_action="reset_unread"),
    ]
    host = evaluate(_loaded(records)).to_record()["host_interaction"]
    assert host["alerts_presented"] == 1
    assert host["alert_badge_reset"] == 1
    for key in ("open_rate", "dismiss_rate", "mute_rate", "signal_opened"):
        assert host[key]["available"] is False
        assert host[key]["value"] is None
        assert host[key]["unavailable_reason"] == UNAVAILABLE_PRODUCER
        assert host[key]["value"] != 0


def test_intelligence_skip_and_fallback_breakdown() -> None:
    records = [
        _event(
            TelemetryName.INTELLIGENCE_SKIPPED,
            signal_id="s1",
            telemetry_id="k1",
            decision_reason=DecisionReason.STALE_FEED,
        ),
        _event(
            TelemetryName.INTELLIGENCE_SKIPPED,
            signal_id="s2",
            telemetry_id="k2",
            decision_reason=DecisionReason.NOT_CANDIDATE,
        ),
        _event(
            TelemetryName.INTELLIGENCE_FALLBACK,
            signal_id="s3",
            telemetry_id="f1",
            fallback_reason="timeout",
        ),
        _event(
            TelemetryName.INTELLIGENCE_ROUTED,
            signal_id="s3",
            telemetry_id="r1",
        ),
    ]
    intel = evaluate(_loaded(records)).to_record()["intelligence"]
    assert intel["skipped"] == 2
    assert intel["skip_by_decision_reason"]["stale_feed"] == 1
    assert intel["skip_by_decision_reason"]["not_candidate"] == 1
    assert set(intel["skip_by_decision_reason"]) == {item.value for item in DecisionReason}
    assert intel["fallback"] == 1
    assert intel["fallback_by_fallback_reason"]["timeout"] == 1
    assert intel["routed"] == 1
    assert intel["unrecognized_skip_reason_count"] == 0
    assert intel["unrecognized_fallback_reason_count"] == 0


def test_latency_statistics() -> None:
    records = [
        _event(
            TelemetryName.INTELLIGENCE_LATENCY,
            signal_id="s1",
            telemetry_id=f"l{index}",
            latency_s=value,
            latency_stage=LatencyStage.MODEL,
        )
        for index, value in enumerate((0.1, 0.2, 0.3, 0.4, 1.0), start=1)
    ]
    model = evaluate(_loaded(records)).to_record()["intelligence"]["latency"]["model"]
    assert model["count"] == 5
    assert model["min_s"] == 0.1
    assert model["max_s"] == 1.0
    assert model["median_s"] == 0.3
    assert model["p95_s"] == 1.0
    router = evaluate(_loaded(records)).to_record()["intelligence"]["latency"]["router"]
    assert router["count"] == 0
    assert router["p95_s"] is None


def test_token_totals_only_from_actual_usage() -> None:
    empty = evaluate(_loaded([])).to_record()["intelligence"]["token_usage"]
    assert empty["available"] is False
    assert empty["unavailable_reason"] == UNAVAILABLE_NO_USAGE
    assert empty["token_in_total"] is None
    records = [
        _event(
            TelemetryName.INTELLIGENCE_TOKEN_USAGE,
            signal_id="s1",
            telemetry_id="u1",
            token_in=10,
            token_out=4,
        ),
        _event(
            TelemetryName.INTELLIGENCE_TOKEN_USAGE,
            signal_id="s2",
            telemetry_id="u2",
            token_in=2,
            token_out=1,
        ),
    ]
    usage = evaluate(_loaded(records)).to_record()["intelligence"]["token_usage"]
    assert usage["available"] is True
    assert usage["token_in_total"] == 12
    assert usage["token_out_total"] == 5
    assert usage["token_total"] == 17
    assert usage["token_events_count"] == 2


def test_latency_events_do_not_imply_token_usage() -> None:
    records = [
        _event(
            TelemetryName.INTELLIGENCE_LATENCY,
            signal_id="s1",
            telemetry_id="l1",
            latency_s=0.2,
            latency_stage=LatencyStage.MODEL,
        )
    ]
    usage = evaluate(_loaded(records)).to_record()["intelligence"]["token_usage"]
    assert usage["available"] is False
    assert usage["unavailable_reason"] == UNAVAILABLE_NO_USAGE
    assert usage["token_in_total"] is None


def test_market_hour_excludes_lunch() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol=ASHARE,
            telemetry_id="a",
            priority="NOTICE",
            market_timestamp=_ts(11, 0),
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s2",
            symbol=ASHARE,
            telemetry_id="b",
            priority="NOTICE",
            market_timestamp=_ts(14, 0),
        ),
    ]
    report = evaluate(_loaded(records)).to_record()
    noise = report["alert_noise"]
    assert noise["observed_market_seconds"] == 5400.0
    assert report["data_quality"]["market_time_coverage"]["observed_market_seconds"] == 5400.0
    hour = noise["alerts_per_market_hour"]
    assert hour["available"] is True
    assert hour["value"] == 2 / 5400.0 * 3600.0


def test_insufficient_market_time_unavailable() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol=ASHARE,
            telemetry_id="a",
            priority="NOTICE",
            market_timestamp=_ts(10, 0),
        )
    ]
    hour = evaluate(_loaded(records)).to_record()["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is False
    assert hour["unavailable_reason"] == UNAVAILABLE_MARKET_TIME
    assert hour["value"] is None


def test_lunch_only_span_is_unavailable() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol=ASHARE,
            telemetry_id="a",
            priority="NOTICE",
            market_timestamp=_ts(12, 0),
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s2",
            symbol=ASHARE,
            telemetry_id="b",
            priority="NOTICE",
            market_timestamp=_ts(12, 30),
        ),
    ]
    noise = evaluate(_loaded(records)).to_record()["alert_noise"]
    assert noise["observed_market_seconds"] == 0.0
    assert noise["alerts_per_market_hour"]["available"] is False
    assert noise["alerts_per_market_hour"]["unavailable_reason"] == UNAVAILABLE_MARKET_TIME


def test_market_hour_ignores_created_timestamp() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol=ASHARE,
            telemetry_id="a",
            priority="NOTICE",
            created_timestamp=_ts(9, 30),
            market_timestamp=_ts(12, 0),
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s2",
            symbol=ASHARE,
            telemetry_id="b",
            priority="NOTICE",
            created_timestamp=_ts(15, 0),
            market_timestamp=_ts(12, 30),
        ),
    ]
    hour = evaluate(_loaded(records)).to_record()["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is False
    assert hour["unavailable_reason"] == UNAVAILABLE_MARKET_TIME


def test_run_id_and_symbol_grouping() -> None:
    records = [
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e1",
            symbol="AAA",
            run_id="r1",
            telemetry_id="1",
        ),
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e2",
            symbol="BBB",
            run_id="r2",
            telemetry_id="2",
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol="AAA",
            run_id="r1",
            telemetry_id="3",
            priority="NOTICE",
        ),
    ]
    filtered = evaluate(_loaded(records), run_id="r1").to_record()
    assert filtered["metadata"]["filter_run_id"] == "r1"
    assert filtered["metadata"]["run_ids"] == ["r1"]
    assert filtered["pipeline"]["events_generated"] == 1
    symbols = {row["symbol"]: row for row in filtered["per_symbol"]}
    assert symbols["AAA"]["events_generated"] == 1
    assert "BBB" not in symbols
    all_runs = evaluate(_loaded(records)).to_record()
    assert set(all_runs["metadata"]["run_ids"]) == {"r1", "r2"}
    by_symbol = {row["symbol"]: row for row in all_runs["per_symbol"]}
    assert by_symbol["AAA"]["alert_candidates"] == 1
    assert by_symbol["BBB"]["events_generated"] == 1


def test_rotated_files_oldest_to_newest(tmp_path: Path) -> None:
    current = tmp_path / "telemetry.jsonl"
    current.write_text('{"telemetry_id":"new","name":"alert_badge_reset"}\n', encoding="utf-8")
    (tmp_path / "telemetry.jsonl.1").write_text(
        '{"telemetry_id":"mid","name":"alert_badge_reset"}\n', encoding="utf-8"
    )
    (tmp_path / "telemetry.jsonl.5").write_text(
        '{"telemetry_id":"old","name":"alert_badge_reset"}\n', encoding="utf-8"
    )
    loaded = TelemetryReader().load(current, backup_count=DEFAULT_BACKUP_COUNT)
    ids = [str(row["telemetry_id"]) for row in loaded.records]
    assert ids == ["old", "mid", "new"]
    assert Path(loaded.input_files[0]).name == "telemetry.jsonl.5"
    assert Path(loaded.input_files[-1]).name == "telemetry.jsonl"


def test_malformed_middle_surfaces_data_quality(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_bytes(
        b'{"telemetry_id":"a","name":"alert_badge_reset"}\n'
        b"{not-json}\n"
        b'{"telemetry_id":"b","name":"alert_badge_reset"}\n'
    )
    loaded = TelemetryReader().load(path)
    report = evaluate(loaded).to_record()
    quality = report["data_quality"]
    assert quality["healthy"] is False
    assert quality["data_quality_warning"] is True
    assert quality["malformed_complete_lines"] == 1
    assert [row["telemetry_id"] for row in loaded.records] == ["a", "b"]


def test_trailing_partial_is_surfaced(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_bytes(b'{"telemetry_id":"keep","name":"alert_badge_reset"}\n{"partial":')
    loaded = TelemetryReader().load(path)
    quality = evaluate(loaded).to_record()["data_quality"]
    assert quality["skipped_trailing_partial"] is True
    assert quality["healthy"] is True
    assert loaded.records[0]["telemetry_id"] == "keep"


def test_report_serialization_allowlist() -> None:
    records = [
        _event(TelemetryName.EVENT_GENERATED, event_id="e1", symbol="00700.HK"),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol="00700.HK",
            telemetry_id="c",
            priority="NOTICE",
        ),
    ]
    raw = json.dumps(evaluate(_loaded(records)).to_record())
    parsed = json.loads(raw)
    keys: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            keys.update(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(parsed)
    assert TELEMETRY_DENYLIST.isdisjoint(keys)
    assert keys <= EVALUATION_ALLOWLIST
    for denied in TELEMETRY_DENYLIST:
        assert f'"{denied}"' not in raw


def test_cli_telemetry_report_json(tmp_path: Path, capsys) -> None:
    sink = JsonlTelemetrySink(tmp_path / "telemetry.jsonl")
    sink.write(_event(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread"))
    sink.close()
    assert main(["telemetry", "report", "--data-dir", str(tmp_path), "--format", "json"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["pipeline"]["alert_suppressed"] == 0
    assert payload["host_interaction"]["open_rate"]["available"] is False
    assert "therefore" not in out
    assert "rewrite" not in out


def test_cli_telemetry_report_text(tmp_path: Path, capsys) -> None:
    sink = JsonlTelemetrySink(tmp_path / "telemetry.jsonl")
    sink.write(_event(TelemetryName.ALERT_BADGE_RESET, host_action="reset_unread"))
    sink.close()
    assert main(["telemetry", "report", "--data-dir", str(tmp_path), "--format", "text"]) == 0
    out = capsys.readouterr().out
    assert "data_quality_warning" in out
    assert "open_rate: unavailable" in out
    assert "therefore" not in out
    assert "rewrite threshold" not in out


def test_render_text_is_not_source_of_truth() -> None:
    report = evaluate(_loaded([]))
    text = render_text(report)
    record = report.to_record()
    assert record["pipeline"]["events_generated"] == 0
    assert "unavailable" in text
    assert "producer_not_implemented" in text


def test_report_rejects_denied_reason_key() -> None:
    with pytest.raises(ValueError, match="denied"):
        sanitize_report({"pipeline": {"reason": "too noisy"}})


def test_cluster_tracker_seen_count_override_and_derived() -> None:
    records = [
        _event(
            TelemetryName.EVENT_CLUSTERED,
            event_id="e1",
            symbol="00700.HK",
            telemetry_id="c1",
        ),
        _event(
            TelemetryName.EVENT_CLUSTERED,
            event_id="e2",
            symbol="00700.HK",
            telemetry_id="c2",
        ),
        _event(
            TelemetryName.EVENT_CLUSTERED,
            event_id="e1",
            symbol="00700.HK",
            telemetry_id="c3",
        ),
    ]
    derived = evaluate(_loaded(records)).to_record()["pipeline"]
    assert derived["events_clustered"] == 3
    assert derived["cluster_tracker_seen_count"] == 2
    overridden = evaluate(_loaded(records), cluster_tracker_seen_count=9).to_record()
    assert overridden["pipeline"]["cluster_tracker_seen_count"] == 9


def test_missing_jsonl_is_empty_healthy(tmp_path: Path) -> None:
    loaded = TelemetryReader().load(tmp_path / "telemetry.jsonl")
    quality = evaluate(loaded).to_record()["data_quality"]
    assert loaded.records == ()
    assert quality["records_read"] == 0
    assert quality["healthy"] is True
    assert quality["input_files"] == []


def _ashare_alert(
    signal_id: str,
    telemetry_id: str,
    hour: int,
    minute: int = 0,
    **fields: object,
) -> dict[str, object]:
    day = int(fields.pop("day", 15))
    payload: dict[str, object] = {
        "signal_id": signal_id,
        "symbol": ASHARE,
        "telemetry_id": telemetry_id,
        "priority": "NOTICE",
        "market_timestamp": _ts(hour, minute, day=day),
    }
    payload.update(fields)
    return _event(TelemetryName.ALERT_CANDIDATE, **payload)  # type: ignore[arg-type]


def test_single_alert_uses_all_telemetry_exposure() -> None:
    records = [
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e1",
            symbol=ASHARE,
            telemetry_id="e1",
            market_timestamp=_ts(9, 30),
        ),
        _ashare_alert("s1", "a1", 10, 0),
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e2",
            symbol=ASHARE,
            telemetry_id="e2",
            market_timestamp=_ts(10, 30),
        ),
    ]
    report = evaluate(_loaded(records)).to_record()
    assert report["alert_noise"]["observed_market_seconds"] == 3600.0
    assert report["data_quality"]["market_time_coverage"]["observed_market_seconds"] == 3600.0
    hour = report["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is True
    assert hour["value"] == 1.0


def test_multi_run_does_not_bridge_idle_hours() -> None:
    records = [
        _ashare_alert("s1", "r1a", 9, 30, run_id="r1"),
        _ashare_alert("s2", "r1b", 10, 30, run_id="r1"),
        _ashare_alert("s3", "r2a", 9, 30, run_id="r2", day=16),
        _ashare_alert("s4", "r2b", 10, 30, run_id="r2", day=16),
    ]
    report = evaluate(_loaded(records)).to_record()
    assert report["alert_noise"]["observed_market_seconds"] == 7200.0
    hour = report["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is True
    assert hour["value"] == 2.0
    by_run = {row["run_id"]: row for row in report["per_run"]}
    assert by_run["r1"]["alert_candidates"] == 2
    assert by_run["r1"]["alerts_per_market_hour"]["value"] == 2.0
    assert by_run["r2"]["alert_candidates"] == 2
    assert by_run["r2"]["alerts_per_market_hour"]["value"] == 2.0
    dates = {row["market_date"]: row for row in report["per_market_date"]}
    assert set(dates) == {"2024-01-15", "2024-01-16"}
    assert dates["2024-01-15"]["alert_candidates"] == 2
    assert dates["2024-01-16"]["alert_candidates"] == 2
    assert dates["2024-01-15"]["alerts_per_market_hour"]["value"] == 2.0


def test_candidate_run_without_exposure_fail_closes_global() -> None:
    records = [
        _ashare_alert("s1", "r1a", 9, 30, run_id="r1"),
        _ashare_alert("s2", "r1b", 10, 30, run_id="r1"),
        _ashare_alert("s3", "r2a", 10, 0, run_id="r2"),
    ]
    report = evaluate(_loaded(records)).to_record()
    hour = report["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is False
    assert hour["unavailable_reason"] == UNAVAILABLE_MARKET_TIME
    assert hour["value"] is None
    assert report["alert_noise"]["observed_market_seconds"] == 0.0
    by_run = {row["run_id"]: row for row in report["per_run"]}
    assert by_run["r1"]["alerts_per_market_hour"]["available"] is True
    assert by_run["r1"]["alerts_per_market_hour"]["value"] == 2.0
    assert by_run["r2"]["alerts_per_market_hour"]["available"] is False
    assert by_run["r2"]["alerts_per_market_hour"]["unavailable_reason"] == UNAVAILABLE_MARKET_TIME
    assert report["data_quality"]["runs_insufficient_market_time"] == ["r2"]


def test_hk_market_hour_is_unsupported_scope() -> None:
    records = [
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s1",
            symbol=HK,
            telemetry_id="a",
            priority="NOTICE",
            market_timestamp=_ts(11, 0),
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s2",
            symbol=HK,
            telemetry_id="b",
            priority="NOTICE",
            market_timestamp=_ts(14, 0),
        ),
    ]
    report = evaluate(_loaded(records)).to_record()
    hour = report["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is False
    assert hour["unavailable_reason"] == UNAVAILABLE_MARKET_SCOPE
    assert hour["value"] is None
    assert report["alert_noise"]["observed_market_seconds"] == 0.0
    assert report["data_quality"]["runs_unsupported_market_scope"] == ["run-1"]


def test_ashare_market_hour_is_computable() -> None:
    records = [
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e1",
            symbol=ASHARE,
            telemetry_id="e1",
            market_timestamp=_ts(9, 30),
        ),
        _ashare_alert("s1", "a1", 10, 0),
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e2",
            symbol="000001.SZ",
            telemetry_id="e2",
            market_timestamp=_ts(10, 30),
        ),
    ]
    hour = evaluate(_loaded(records)).to_record()["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is True
    assert hour["value"] == 1.0


def test_mixed_ashare_and_hk_fail_closes_global() -> None:
    records = [
        _ashare_alert("s1", "r1a", 9, 30, run_id="r1"),
        _ashare_alert("s2", "r1b", 10, 30, run_id="r1"),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s3",
            symbol=HK,
            run_id="r2",
            telemetry_id="h1",
            priority="NOTICE",
            market_timestamp=_ts(9, 30),
        ),
        _event(
            TelemetryName.ALERT_CANDIDATE,
            signal_id="s4",
            symbol=HK,
            run_id="r2",
            telemetry_id="h2",
            priority="NOTICE",
            market_timestamp=_ts(10, 30),
        ),
    ]
    hour = evaluate(_loaded(records)).to_record()["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is False
    assert hour["unavailable_reason"] == UNAVAILABLE_MARKET_SCOPE


def test_saturday_is_not_cash_session_exposure() -> None:
    records = [
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e1",
            symbol=ASHARE,
            telemetry_id="e1",
            market_timestamp=_ts(9, 30, day=13),
        ),
        _ashare_alert("s1", "a1", 10, 0, day=13),
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e2",
            symbol=ASHARE,
            telemetry_id="e2",
            market_timestamp=_ts(15, 0, day=13),
        ),
    ]
    report = evaluate(_loaded(records)).to_record()
    assert report["alert_noise"]["observed_market_seconds"] == 0.0
    hour = report["alert_noise"]["alerts_per_market_hour"]
    assert hour["available"] is False
    assert hour["unavailable_reason"] == UNAVAILABLE_MARKET_TIME


def test_per_run_and_per_market_date_are_separate() -> None:
    records = [
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e1",
            symbol=ASHARE,
            run_id="r1",
            telemetry_id="e1",
            market_timestamp=_ts(9, 30, day=15),
        ),
        _ashare_alert("s1", "a1", 10, 30, run_id="r1", day=15),
        _event(
            TelemetryName.EVENT_GENERATED,
            event_id="e2",
            symbol=ASHARE,
            run_id="r2",
            telemetry_id="e2",
            market_timestamp=_ts(9, 30, day=16),
        ),
        _ashare_alert("s2", "a2", 10, 30, run_id="r2", day=16),
        _event(
            TelemetryName.ALERT_BADGE_RESET,
            telemetry_id="host",
            host_action="reset_unread",
            run_id="r1",
        ),
    ]
    report = evaluate(_loaded(records)).to_record()
    assert [row["run_id"] for row in report["per_run"]] == ["r1", "r2"]
    dates = [row["market_date"] for row in report["per_market_date"]]
    assert dates == ["2024-01-15", "2024-01-16"]
    by_date = {row["market_date"]: row for row in report["per_market_date"]}
    assert by_date["2024-01-15"]["events_generated"] == 1
    assert by_date["2024-01-16"]["events_generated"] == 1
    assert by_date["2024-01-15"]["alert_candidates"] == 1
    assert "2024-01-01" not in by_date


def test_unknown_breakdown_values_do_not_leak_into_report() -> None:
    leaked = "arbitrary free text from future adapter"
    records = [
        {
            "telemetry_id": "k1",
            "name": "intelligence_skipped",
            "kind": "intelligence",
            "created_timestamp": 1.0,
            "run_id": "run-1",
            "signal_id": "s1",
            "decision_reason": leaked,
        },
        _event(
            TelemetryName.INTELLIGENCE_FALLBACK,
            signal_id="s2",
            telemetry_id="f1",
            fallback_reason=leaked,
        ),
        {
            "telemetry_id": "sup",
            "name": "alert_suppressed",
            "kind": "pipeline",
            "created_timestamp": 1.0,
            "run_id": "run-1",
            "signal_id": "s3",
            "symbol": ASHARE,
            "suppression_reason": leaked,
        },
    ]
    report = evaluate(_loaded(records)).to_record()
    raw = json.dumps(report)
    assert leaked not in raw
    assert leaked not in report["intelligence"]["skip_by_decision_reason"]
    assert leaked not in report["intelligence"]["fallback_by_fallback_reason"]
    assert leaked not in report["alert_noise"]["suppression_by_reason"]
    assert report["intelligence"]["unrecognized_skip_reason_count"] == 1
    assert report["intelligence"]["unrecognized_fallback_reason_count"] == 1
    assert report["alert_noise"]["unrecognized_suppression_reason_count"] == 1
    assert report["data_quality"]["semantic_warning_count"] == 3
    assert report["data_quality"]["data_quality_warning"] is True
    keys: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            keys.update(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(report)
    assert keys <= EVALUATION_ALLOWLIST
    assert leaked not in keys


def _feedback_record(
    label: FeedbackLabel, *, signal_id: str, feedback_id: str, run_id: str = "run-1"
) -> dict[str, object]:
    return UserFeedback(
        feedback_id=feedback_id,
        created_timestamp=1.0,
        run_id=run_id,
        label=label,
        signal_id=signal_id,
    ).to_record()


def test_no_explicit_feedback_is_not_not_useful() -> None:
    records = [
        _event(TelemetryName.ALERT_PRESENTED, signal_id="s1", telemetry_id="p1"),
        _event(TelemetryName.ALERT_BADGE_RESET, telemetry_id="r1", host_action="reset_unread"),
    ]
    report = evaluate(_loaded(records)).to_record()
    feedback = report["explicit_feedback"]
    assert feedback["feedback_count"] == 0
    assert feedback["useful_count"] == 0
    assert feedback["not_useful_count"] == 0
    assert feedback["too_noisy_count"] == 0
    assert feedback["too_late_count"] == 0
    assert feedback["useful_rate"]["available"] is False
    assert feedback["useful_rate"]["value"] is None
    assert feedback["useful_rate"]["unavailable_reason"] == "no_explicit_feedback"
    assert report["host_interaction"]["alert_badge_reset"] == 1
    assert report["host_interaction"]["dismiss_rate"]["available"] is False


def test_explicit_feedback_useful_rate_and_coverage() -> None:
    presented = [
        _event(TelemetryName.ALERT_PRESENTED, signal_id="s1", telemetry_id="p1"),
        _event(TelemetryName.ALERT_PRESENTED, signal_id="s2", telemetry_id="p2"),
        _event(TelemetryName.ALERT_PRESENTED, signal_id="s3", telemetry_id="p3"),
        _event(TelemetryName.ALERT_PRESENTED, signal_id="s4", telemetry_id="p4"),
    ]
    feedback_rows = [
        _feedback_record(FeedbackLabel.USEFUL, signal_id="s1", feedback_id="f1"),
        _feedback_record(FeedbackLabel.USEFUL, signal_id="s2", feedback_id="f2"),
        _feedback_record(FeedbackLabel.NOT_USEFUL, signal_id="s3", feedback_id="f3"),
        _feedback_record(FeedbackLabel.TOO_NOISY, signal_id="s1", feedback_id="f4"),
    ]
    report = evaluate(_loaded(presented), feedback=_loaded(feedback_rows)).to_record()
    section = report["explicit_feedback"]
    assert section["feedback_count"] == 4
    assert section["useful_count"] == 2
    assert section["not_useful_count"] == 1
    assert section["too_noisy_count"] == 1
    assert section["too_late_count"] == 0
    assert section["useful_rate"]["available"] is True
    assert section["useful_rate"]["value"] == 0.5
    assert section["feedback_coverage"]["available"] is True
    assert section["feedback_coverage"]["value"] == 0.75


def test_feedback_coverage_unavailable_without_presented_denominator() -> None:
    feedback_rows = [
        _feedback_record(FeedbackLabel.USEFUL, signal_id="s1", feedback_id="f1"),
    ]
    report = evaluate(_loaded([]), feedback=_loaded(feedback_rows)).to_record()
    coverage = report["explicit_feedback"]["feedback_coverage"]
    assert coverage["available"] is False
    assert coverage["value"] is None


def test_cli_telemetry_report_reads_feedback_jsonl(tmp_path: Path, capsys) -> None:
    tel = JsonlTelemetrySink(tmp_path / "telemetry.jsonl")
    tel.write(_event(TelemetryName.ALERT_PRESENTED, signal_id="s1", telemetry_id="p1"))
    tel.close()
    fb = JsonlTelemetrySink(tmp_path / "feedback.jsonl", allowlist=FEEDBACK_ALLOWLIST)
    fb.write(_feedback_record(FeedbackLabel.USEFUL, signal_id="s1", feedback_id="f1"))
    fb.write(_feedback_record(FeedbackLabel.NOT_USEFUL, signal_id="s1", feedback_id="f2"))
    fb.close()
    assert main(["telemetry", "report", "--data-dir", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["explicit_feedback"]["feedback_count"] == 2
    assert payload["explicit_feedback"]["useful_rate"]["value"] == 0.5
    assert "therefore" not in json.dumps(payload)
