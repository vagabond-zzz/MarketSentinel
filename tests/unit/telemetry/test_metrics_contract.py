from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from market_sentinel.telemetry.contract import (
    FEEDBACK_ALLOWLIST,
    HOST_INTERACTION_FACT_OWNER,
    TELEMETRY_ALLOWLIST,
    TELEMETRY_COLLECTOR_OWNER,
    TELEMETRY_DENYLIST,
    TUNING_ALLOWLIST,
    ClusterMembershipTracker,
    DecisionReason,
    FeedbackLabel,
    LatencyStage,
    SuppressionReason,
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
    payload: dict[str, object] = {
        "telemetry_id": "t1",
        "name": TelemetryName.EVENT_GENERATED,
        "kind": TelemetryKind.PIPELINE,
        "created_timestamp": 1.0,
        "run_id": "run-1",
        "symbol": "AAPL",
        "event_id": "e1",
    }
    payload.update(overrides)
    return TelemetryEvent(**payload)  # type: ignore[arg-type]


def test_market_and_created_timestamps_are_independent() -> None:
    event = _event(created_timestamp=100.0, market_timestamp=50.0)
    assert event.created_timestamp == 100.0
    assert event.market_timestamp == 50.0
    assert event.created_timestamp != event.market_timestamp


def test_run_id_required() -> None:
    with pytest.raises(ValueError, match="run_id"):
        _event(run_id="")
    with pytest.raises(ValueError, match="run_id"):
        UserFeedback(
            feedback_id="f1",
            created_timestamp=1.0,
            run_id="",
            label=FeedbackLabel.USEFUL,
        )


def test_no_telemetry_session_id() -> None:
    names = {field.name for field in fields(TelemetryEvent)} | {
        field.name for field in fields(UserFeedback)
    }
    assert "session_id" not in names
    assert "session_id" in TELEMETRY_DENYLIST
    with pytest.raises(ValueError, match="denied"):
        project_allowlist({"session_id": "2026-08-28"}, TELEMETRY_ALLOWLIST)


def test_alert_suppressed_requires_enum_reason() -> None:
    event = _event(
        name=TelemetryName.ALERT_SUPPRESSED,
        kind=TelemetryKind.PIPELINE,
        event_id=None,
        signal_id="s1",
        suppression_reason=SuppressionReason.COOLDOWN,
    )
    assert event.suppression_reason is SuppressionReason.COOLDOWN
    duplicate = _event(
        name=TelemetryName.ALERT_SUPPRESSED,
        kind=TelemetryKind.PIPELINE,
        event_id=None,
        signal_id="s1",
        suppression_reason=SuppressionReason.SAME_TICK_DUPLICATE,
    )
    assert duplicate.suppression_reason is SuppressionReason.SAME_TICK_DUPLICATE
    with pytest.raises(ValueError, match="suppression_reason"):
        _event(
            name=TelemetryName.ALERT_SUPPRESSED,
            kind=TelemetryKind.PIPELINE,
            event_id=None,
            signal_id="s1",
        )
    with pytest.raises(ValueError, match="SuppressionReason"):
        _event(
            name=TelemetryName.ALERT_SUPPRESSED,
            kind=TelemetryKind.PIPELINE,
            event_id=None,
            signal_id="s1",
            suppression_reason="because noisy",  # type: ignore[arg-type]
        )


def test_skip_decision_reason_separated_from_fallback() -> None:
    skipped = TelemetryEvent(
        telemetry_id="t-skip",
        name=TelemetryName.INTELLIGENCE_SKIPPED,
        kind=TelemetryKind.INTELLIGENCE,
        created_timestamp=1.0,
        run_id="run-1",
        signal_id="s1",
        decision_reason=DecisionReason.STALE_FEED,
    )
    assert skipped.fallback_reason is None
    fallback = TelemetryEvent(
        telemetry_id="t-fb",
        name=TelemetryName.INTELLIGENCE_FALLBACK,
        kind=TelemetryKind.INTELLIGENCE,
        created_timestamp=1.0,
        run_id="run-1",
        signal_id="s1",
        fallback_reason="timeout",
    )
    assert fallback.decision_reason is None
    with pytest.raises(ValueError, match="fallback_reason"):
        TelemetryEvent(
            telemetry_id="bad",
            name=TelemetryName.INTELLIGENCE_SKIPPED,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
            decision_reason=DecisionReason.NOT_CANDIDATE,
            fallback_reason="timeout",
        )
    with pytest.raises(ValueError, match="decision_reason"):
        TelemetryEvent(
            telemetry_id="bad2",
            name=TelemetryName.INTELLIGENCE_FALLBACK,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
            fallback_reason="timeout",
            decision_reason=DecisionReason.EPISODE_BUDGET,
        )


def test_intelligence_latency_requires_stage() -> None:
    event = TelemetryEvent(
        telemetry_id="lat",
        name=TelemetryName.INTELLIGENCE_LATENCY,
        kind=TelemetryKind.INTELLIGENCE,
        created_timestamp=1.0,
        run_id="run-1",
        signal_id="s1",
        latency_s=0.4,
        latency_stage=LatencyStage.MODEL,
    )
    assert event.latency_stage is LatencyStage.MODEL
    with pytest.raises(ValueError, match="latency_stage"):
        TelemetryEvent(
            telemetry_id="lat-bad",
            name=TelemetryName.INTELLIGENCE_LATENCY,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
            latency_s=0.4,
        )


def test_negative_latency_and_tokens_rejected() -> None:
    with pytest.raises(ValueError, match="latency_s"):
        TelemetryEvent(
            telemetry_id="n1",
            name=TelemetryName.INTELLIGENCE_LATENCY,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
            latency_s=-0.1,
            latency_stage=LatencyStage.ROUTER,
        )
    with pytest.raises(ValueError, match="token_in"):
        TelemetryEvent(
            telemetry_id="n2",
            name=TelemetryName.INTELLIGENCE_TOKEN_USAGE,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
            token_in=-1,
        )
    with pytest.raises(ValueError, match="token_out"):
        TelemetryEvent(
            telemetry_id="n3",
            name=TelemetryName.INTELLIGENCE_TOKEN_USAGE,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
            token_out=-2,
        )


def test_required_correlation_fields() -> None:
    with pytest.raises(ValueError, match="telemetry_id"):
        _event(telemetry_id="")
    with pytest.raises(ValueError, match="event_id"):
        _event(event_id=None)
    with pytest.raises(ValueError, match="signal_id"):
        _event(
            name=TelemetryName.ALERT_CANDIDATE,
            kind=TelemetryKind.PIPELINE,
            event_id=None,
            signal_id=None,
        )
    with pytest.raises(ValueError, match="signal_id"):
        TelemetryEvent(
            telemetry_id="h1",
            name=TelemetryName.ALERT_PRESENTED,
            kind=TelemetryKind.HOST,
            created_timestamp=1.0,
            run_id="run-1",
        )
    TelemetryEvent(
        telemetry_id="badge",
        name=TelemetryName.ALERT_BADGE_RESET,
        kind=TelemetryKind.HOST,
        created_timestamp=1.0,
        run_id="run-1",
        host_action="reset_unread",
    )
    with pytest.raises(ValueError, match="token"):
        TelemetryEvent(
            telemetry_id="tok",
            name=TelemetryName.INTELLIGENCE_TOKEN_USAGE,
            kind=TelemetryKind.INTELLIGENCE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
        )


def test_event_clustered_once_per_event_id() -> None:
    tracker = ClusterMembershipTracker()
    first = tracker.newly_clustered(("e1", "e2"))
    assert set(first) == {"e1", "e2"}
    assert tracker.newly_clustered(("e1",)) == ()
    later = tracker.newly_clustered(("e1", "e2", "e3"))
    assert later == ("e3",)
    assert tracker.newly_clustered(("e1", "e2", "e3")) == ()
    singleton_then_pair = ClusterMembershipTracker()
    assert singleton_then_pair.newly_clustered(("e1",)) == ()
    assert set(singleton_then_pair.newly_clustered(("e1", "e2"))) == {"e1", "e2"}


def test_tuning_snapshot_has_no_notes() -> None:
    names = {field.name for field in fields(TuningSnapshot)}
    assert names == {"snapshot_id", "created_timestamp", "source", "config_version"}
    snapshot = TuningSnapshot(
        snapshot_id="snap-1",
        created_timestamp=1.0,
        source=TuningSource.OFFLINE_EVAL,
        config_version="cfg-1",
    )
    assert "notes" not in snapshot.to_record()
    assert "notes" not in TUNING_ALLOWLIST


def test_free_text_cannot_enter_tuning_record() -> None:
    with pytest.raises(ValueError, match="denied"):
        project_allowlist(
            {
                "snapshot_id": "s",
                "notes": "workspace=/secret prompt=leak",
                "workspace": "C:/users/me",
                "prompt": "buy now",
            },
            TUNING_ALLOWLIST,
        )
    with pytest.raises(ValueError, match="denied"):
        project_allowlist({"source_code": "print(1)"}, TUNING_ALLOWLIST)


def test_host_core_ownership_constants() -> None:
    assert HOST_INTERACTION_FACT_OWNER == "host"
    assert TELEMETRY_COLLECTOR_OWNER == "core"
    docs = (Path(__file__).resolve().parents[3] / "docs" / "16_v0.6_Metrics_Contract.md").read_text(
        encoding="utf-8"
    )
    assert "Host interaction fact owner:" in docs
    assert "Telemetry collector / future local storage owner:" in docs
    assert "additive Protocol v1 host-interaction command" in docs
    assert "independent Cursor telemetry DB" in docs
    assert 'HOST_INTERACTION_FACT_OWNER = "host"' in docs
    assert 'TELEMETRY_COLLECTOR_OWNER = "core"' in docs


def test_kind_is_frozen_per_name() -> None:
    assert kind_for(TelemetryName.ALERT_PRESENTED) is TelemetryKind.HOST
    assert kind_for(TelemetryName.ALERT_SUPPRESSED) is TelemetryKind.PIPELINE
    with pytest.raises(ValueError, match="kind="):
        TelemetryEvent(
            telemetry_id="t-bad",
            name=TelemetryName.ALERT_PRESENTED,
            kind=TelemetryKind.PIPELINE,
            created_timestamp=1.0,
            run_id="run-1",
            signal_id="s1",
        )


def test_allowlist_rejects_mutation_and_workspace_payloads() -> None:
    with pytest.raises(ValueError, match="denied"):
        project_allowlist({"workspace": "/Users/me/proj", "name": "x"}, TELEMETRY_ALLOWLIST)
    with pytest.raises(ValueError, match="denied"):
        project_allowlist({"apply_online": True}, TELEMETRY_ALLOWLIST)
    with pytest.raises(ValueError, match="denied"):
        project_allowlist({"prompt": "analyze this"}, FEEDBACK_ALLOWLIST)


def test_tuning_snapshot_has_no_apply_api() -> None:
    snapshot = TuningSnapshot(
        snapshot_id="snap-1",
        created_timestamp=1.0,
        source=TuningSource.MANUAL,
        config_version="cfg-1",
    )
    assert not hasattr(snapshot, "apply")
    assert snapshot.to_record() == {
        "snapshot_id": "snap-1",
        "created_timestamp": 1.0,
        "source": "manual",
        "config_version": "cfg-1",
    }


def test_feedback_is_not_a_market_fact() -> None:
    feedback = UserFeedback(
        feedback_id="fb-1",
        created_timestamp=2.0,
        run_id="run-1",
        label=FeedbackLabel.TOO_NOISY,
        signal_id="sig-1",
    )
    record = feedback.to_record()
    assert "label" in record
    assert "price" not in record
    assert "last" not in record


def test_host_only_market_timestamp_may_be_none() -> None:
    event = TelemetryEvent(
        telemetry_id="open",
        name=TelemetryName.SIGNAL_OPENED,
        kind=TelemetryKind.HOST,
        created_timestamp=9.0,
        run_id="run-1",
        signal_id="s1",
        market_timestamp=None,
        host_action="open_from_statusbar",
    )
    assert event.market_timestamp is None
