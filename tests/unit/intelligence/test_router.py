from __future__ import annotations

from market_sentinel.domain.enums import EventDirection, FeedStatus, SignalPriority
from market_sentinel.intelligence.contract import (
    EpisodeCallBudget,
    FallbackReason,
    IntelligenceInput,
)
from market_sentinel.intelligence.router import need_intelligence


def _input(**overrides: object) -> IntelligenceInput:
    payload = dict(
        signal_id="sig-1",
        symbol="00700.HK",
        family="price_volume",
        direction=EventDirection.UP,
        priority=SignalPriority.IMPORTANT,
        event_types=("price_volume_expansion", "rapid_move"),
        change_1m=0.008,
        change_5m=0.018,
        volume_ratio_5m=2.6,
        above_vwap=True,
        rsi14=68.0,
        day_range_position=0.9,
        feed_status=FeedStatus.LIVE,
        alert_edge=True,
        episode_call_count=0,
        last_requested_priority=None,
        expired=False,
    )
    payload.update(overrides)
    return IntelligenceInput(**payload)  # type: ignore[arg-type]


def test_info_and_ordinary_notice_are_not_requested() -> None:
    info = need_intelligence(
        _input(priority=SignalPriority.INFO, family="vwap", event_types=("vwap_cross",))
    )
    notice = need_intelligence(
        _input(priority=SignalPriority.NOTICE, family="volume", event_types=("volume_spike",))
    )
    assert info.requested is False
    assert info.reason is FallbackReason.NOT_CANDIDATE
    assert notice.requested is False
    assert notice.reason is FallbackReason.NOT_CANDIDATE


def test_stale_disconnected_insufficient_suppressed_expired_skip() -> None:
    assert (
        need_intelligence(_input(feed_status=FeedStatus.STALE)).reason is FallbackReason.STALE_FEED
    )
    assert (
        need_intelligence(_input(feed_status=FeedStatus.DISCONNECTED)).reason
        is FallbackReason.STALE_FEED
    )
    assert (
        need_intelligence(_input(change_1m=None, change_5m=None, volume_ratio_5m=None)).reason
        is FallbackReason.INSUFFICIENT_FEATURES
    )
    assert need_intelligence(_input(alert_edge=False)).reason is FallbackReason.SUPPRESSED_EDGE
    assert need_intelligence(_input(expired=True)).reason is FallbackReason.EXPIRED_EPISODE
    for row in (
        _input(feed_status=FeedStatus.STALE),
        _input(alert_edge=False),
        _input(expired=True),
    ):
        assert need_intelligence(row).requested is False


def test_already_called_episode_is_budget_blocked() -> None:
    decision = need_intelligence(
        _input(episode_call_count=1, last_requested_priority=SignalPriority.IMPORTANT)
    )
    assert decision.requested is False
    assert decision.reason is FallbackReason.EPISODE_BUDGET


def test_important_critical_and_price_volume_breakout_are_candidates() -> None:
    important = need_intelligence(_input())
    critical = need_intelligence(_input(priority=SignalPriority.CRITICAL))
    cluster = need_intelligence(
        _input(
            priority=SignalPriority.NOTICE,
            family="other",
            event_types=("rapid_move", "volume_spike", "day_high_breakout"),
        )
    )
    assert important.requested is True
    assert critical.requested is True
    assert cluster.requested is True
    assert cluster.candidate is True


def test_escalation_second_call_requires_explicit_policy() -> None:
    default = need_intelligence(
        _input(
            episode_call_count=1,
            priority=SignalPriority.CRITICAL,
            last_requested_priority=SignalPriority.IMPORTANT,
        )
    )
    assert default.requested is False
    allowed = need_intelligence(
        _input(
            episode_call_count=1,
            priority=SignalPriority.CRITICAL,
            last_requested_priority=SignalPriority.IMPORTANT,
        ),
        budget=EpisodeCallBudget(allow_escalation_recall=True),
    )
    assert allowed.requested is True


def test_delayed_feed_may_still_be_candidate() -> None:
    decision = need_intelligence(_input(feed_status=FeedStatus.DELAYED))
    assert decision.requested is True


async def test_normal_market_replay_does_not_request_intelligence(tmp_path) -> None:
    from tests.integration.test_replay_scenarios import _run

    from market_sentinel.intelligence.compress import compress_intelligence_input

    engine, results = await _run(tmp_path, "normal_market.jsonl")
    requested = 0
    for result in results:
        for row in result.symbol_results:
            feed = engine.health.status(row.symbol)
            traces = {item.signal_id: item for item in row.traces}
            alerts = {item.id for item in row.alert_candidates}
            for signal in row.signal_updates:
                trace = traces.get(signal.id)
                if trace is None:
                    continue
                decision = need_intelligence(
                    compress_intelligence_input(
                        signal=signal,
                        trace=trace,
                        feed_status=feed,
                        alert_edge=signal.id in alerts,
                        episode_call_count=0,
                        last_requested_priority=None,
                        expired=False,
                    )
                )
                if decision.requested:
                    requested += 1
    assert len(results) > 10
    assert requested == 0
