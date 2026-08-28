from __future__ import annotations

import pytest

from market_sentinel.domain.models import MarketState
from market_sentinel.intelligence.diagnostics import IntelligenceDiagnostics
from market_sentinel.ipc.dto import WireMarketState
from market_sentinel.telemetry.contract import (
    FEEDBACK_ALLOWLIST,
    TELEMETRY_ALLOWLIST,
    TELEMETRY_DENYLIST,
    TUNING_ALLOWLIST,
    FeedbackLabel,
    TelemetryEvent,
    TelemetryKind,
    TelemetryName,
    TuningSnapshot,
    TuningSource,
    UserFeedback,
    kind_for,
    project_allowlist,
)


def _event(**overrides: object) -> TelemetryEvent:
    payload = dict(
        telemetry_id="tel-1",
        name=TelemetryName.ALERT_CANDIDATE,
        kind=TelemetryKind.PIPELINE,
        created_timestamp=1_700_000_000.0,
        symbol="00700.HK",
        signal_id="sig-1",
        family="price_volume",
        direction="up",
        priority="important",
    )
    payload.update(overrides)
    return TelemetryEvent(**payload)  # type: ignore[arg-type]


def test_required_pipeline_and_host_names_exist() -> None:
    names = {item.value for item in TelemetryName}
    assert names >= {
        "event_generated",
        "event_deduped",
        "event_clustered",
        "signal_episode_created",
        "signal_escalated",
        "alert_candidate",
        "alert_presented",
        "signal_opened",
        "alert_badge_reset",
        "alert_dismissed",
        "signal_muted",
        "intelligence_routed",
        "intelligence_skipped",
        "intelligence_succeeded",
        "intelligence_fallback",
        "intelligence_token_usage",
        "intelligence_latency",
    }


def test_kind_is_locked_to_name() -> None:
    assert kind_for(TelemetryName.EVENT_GENERATED) is TelemetryKind.PIPELINE
    assert kind_for(TelemetryName.ALERT_PRESENTED) is TelemetryKind.HOST
    assert kind_for(TelemetryName.INTELLIGENCE_ROUTED) is TelemetryKind.INTELLIGENCE
    with pytest.raises(ValueError, match="kind="):
        _event(name=TelemetryName.ALERT_PRESENTED, kind=TelemetryKind.PIPELINE)


def test_record_is_allowlisted_and_rejects_denied_keys() -> None:
    record = _event().to_record()
    assert set(record) <= TELEMETRY_ALLOWLIST
    assert "title" not in record
    assert "summary" not in record
    assert TELEMETRY_DENYLIST.isdisjoint(record)
    with pytest.raises(ValueError, match="denied keys"):
        project_allowlist({"telemetry_id": "x", "workspace": "/tmp/src"}, TELEMETRY_ALLOWLIST)
    with pytest.raises(ValueError, match="denied keys"):
        project_allowlist({"delete_event": True, "name": "alert_candidate"}, TELEMETRY_ALLOWLIST)


def test_feedback_is_not_a_market_fact_and_cannot_mutate() -> None:
    row = UserFeedback(
        feedback_id="fb-1",
        created_timestamp=1.0,
        label=FeedbackLabel.TOO_NOISY,
        signal_id="sig-1",
        symbol="00700.HK",
    )
    record = row.to_record()
    assert set(record) <= FEEDBACK_ALLOWLIST
    assert "delete_event" not in record
    assert not hasattr(row, "apply")
    assert not hasattr(row, "mutate")
    with pytest.raises(ValueError, match="denied keys"):
        project_allowlist(
            {"feedback_id": "fb-1", "rewrite_threshold": True, "label": "too_noisy"},
            FEEDBACK_ALLOWLIST,
        )


def test_tuning_snapshot_has_no_online_apply_api() -> None:
    snap = TuningSnapshot(
        snapshot_id="tune-1",
        created_timestamp=1.0,
        source=TuningSource.OFFLINE_EVAL,
        config_version="event-rules-unreleased",
        notes="replay before/after only",
    )
    assert snap.to_record().keys() <= TUNING_ALLOWLIST
    assert not hasattr(snap, "apply")
    assert not hasattr(snap, "apply_online")


def test_telemetry_is_not_market_state_or_protocol() -> None:
    row = _event()
    assert not isinstance(row, MarketState)
    assert not isinstance(row, WireMarketState)
    assert "protocol_version" not in row.to_record()


def test_ids_are_correlation_only() -> None:
    row = _event(event_id="ev-1", signal_id="sig-1")
    record = row.to_record()
    assert record["event_id"] == "ev-1"
    assert record["signal_id"] == "sig-1"
    assert record["telemetry_id"] == "tel-1"
    assert record["telemetry_id"] != record["signal_id"]


def test_intelligence_diagnostics_are_not_the_telemetry_stream() -> None:
    snap = IntelligenceDiagnostics().snapshot()
    assert "router_decisions" in snap
    assert "model_calls" in snap
    assert "fallback_count" in snap
    assert "telemetry_id" not in snap
    assert snap.keys().isdisjoint(TELEMETRY_DENYLIST)
    assert "token_in" not in snap
    assert "requests_submitted" in snap
    assert "requests_suppressed" in snap
    assert "fallback_count" in snap
