from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from market_sentinel.evaluation.reader import LoadedTelemetry
from market_sentinel.evaluation.report import (
    PRODUCER_ALERT_DISMISSED,
    PRODUCER_SIGNAL_MUTED,
    PRODUCER_SIGNAL_OPENED,
    UNAVAILABLE_MARKET_TIME,
    UNAVAILABLE_NO_USAGE,
    UNAVAILABLE_PRODUCER,
    EvaluationReport,
    available_value,
    unavailable,
)
from market_sentinel.evaluation.stats import latency_bundle, ratio
from market_sentinel.market_data.session import cash_session_overlap_s, session_id
from market_sentinel.telemetry.contract import LatencyStage, TelemetryName

_PRIORITIES = ("INFO", "NOTICE", "IMPORTANT", "CRITICAL")


def evaluate(
    loaded: LoadedTelemetry,
    *,
    run_id: str | None = None,
    cluster_tracker_seen_count: int | None = None,
) -> EvaluationReport:
    records = [
        row
        for row in loaded.records
        if isinstance(row.get("name"), str) and (run_id is None or row.get("run_id") == run_id)
    ]
    names = [str(row["name"]) for row in records]
    pipeline = _pipeline(records, names, cluster_tracker_seen_count)
    alert_noise = _alert_noise(records, names)
    host = _host(names)
    intelligence = _intelligence(records, names)
    return EvaluationReport(
        metadata=_metadata(records, run_id),
        data_quality=_data_quality(loaded, records, run_id),
        pipeline=pipeline,
        alert_noise=alert_noise,
        host_interaction=host,
        intelligence=intelligence,
        per_symbol=_per_symbol(records),
    )


def _count(names: Sequence[str], name: str) -> int:
    return sum(1 for item in names if item == name)


def _metadata(records: Sequence[dict[str, object]], run_id: str | None) -> dict[str, object]:
    run_ids = sorted({str(row["run_id"]) for row in records if isinstance(row.get("run_id"), str)})
    symbols = sorted({str(row["symbol"]) for row in records if isinstance(row.get("symbol"), str)})
    dates = sorted(
        {
            session_id(float(row["market_timestamp"]))
            for row in records
            if isinstance(row.get("market_timestamp"), int | float)
        }
    )
    return {
        "run_ids": run_ids,
        "symbols": symbols,
        "market_dates": dates,
        "filter_run_id": run_id,
    }


def _data_quality(
    loaded: LoadedTelemetry,
    records: Sequence[dict[str, object]],
    run_id: str | None,
) -> dict[str, object]:
    timestamps = [
        float(row["market_timestamp"])
        for row in records
        if isinstance(row.get("market_timestamp"), int | float)
    ]
    coverage: dict[str, object]
    if len(timestamps) >= 2:
        lo, hi = min(timestamps), max(timestamps)
        coverage = {
            "min_market_timestamp": lo,
            "max_market_timestamp": hi,
            "observed_market_seconds": cash_session_overlap_s(lo, hi),
        }
    else:
        coverage = {
            "min_market_timestamp": timestamps[0] if timestamps else None,
            "max_market_timestamp": timestamps[0] if timestamps else None,
            "observed_market_seconds": 0.0,
        }
    run_ids = sorted({str(row["run_id"]) for row in records if isinstance(row.get("run_id"), str)})
    return {
        "input_files": list(loaded.input_files),
        "records_read": loaded.records_read if run_id is None else len(records),
        "malformed_complete_lines": loaded.malformed_complete_lines,
        "skipped_trailing_partial": loaded.skipped_trailing_partial,
        "healthy": loaded.healthy,
        "data_quality_warning": not loaded.healthy,
        "run_ids": run_ids,
        "market_time_coverage": coverage,
    }


def _pipeline(
    records: Sequence[dict[str, object]],
    names: Sequence[str],
    cluster_seen: int | None,
) -> dict[str, object]:
    generated = _count(names, TelemetryName.EVENT_GENERATED.value)
    deduped = _count(names, TelemetryName.EVENT_DEDUPED.value)
    clustered = _count(names, TelemetryName.EVENT_CLUSTERED.value)
    created = _count(names, TelemetryName.SIGNAL_EPISODE_CREATED.value)
    escalated = _count(names, TelemetryName.SIGNAL_ESCALATED.value)
    candidates = _count(names, TelemetryName.ALERT_CANDIDATE.value)
    suppressed = _count(names, TelemetryName.ALERT_SUPPRESSED.value)
    presented = _count(names, TelemetryName.ALERT_PRESENTED.value)
    seen = (
        cluster_seen
        if cluster_seen is not None
        else len(
            {
                row.get("event_id")
                for row in records
                if row.get("name") == TelemetryName.EVENT_CLUSTERED.value
                and isinstance(row.get("event_id"), str)
            }
        )
    )
    return {
        "events_generated": generated,
        "events_deduped": deduped,
        "events_clustered": clustered,
        "signal_episodes_created": created,
        "signal_escalations": escalated,
        "alert_candidates": candidates,
        "alert_suppressed": suppressed,
        "alerts_presented": presented,
        "cluster_tracker_seen_count": seen,
        "dedupe_rate": ratio(deduped, generated),
        "event_to_signal_rate": ratio(created, generated),
        "signal_to_alert_candidate_rate": ratio(candidates, created),
        "candidate_to_presented_rate": ratio(presented, candidates),
        "alert_suppression_rate": ratio(suppressed, candidates + suppressed),
    }


def _alert_noise(records: Sequence[dict[str, object]], names: Sequence[str]) -> dict[str, object]:
    candidates = [row for row in records if row.get("name") == TelemetryName.ALERT_CANDIDATE.value]
    priority_counts = {key: 0 for key in _PRIORITIES}
    for row in candidates:
        priority = row.get("priority")
        if isinstance(priority, str) and priority in priority_counts:
            priority_counts[priority] += 1
    total_priority = sum(priority_counts.values())
    important_critical = priority_counts["IMPORTANT"] + priority_counts["CRITICAL"]
    suppression: dict[str, int] = {"cooldown": 0, "same_tick_duplicate": 0}
    for row in records:
        if row.get("name") != TelemetryName.ALERT_SUPPRESSED.value:
            continue
        reason = row.get("suppression_reason")
        if reason in suppression:
            suppression[str(reason)] += 1
    repeated_signals, extra_alerts = _repeated_episodes(candidates)
    per_hour, observed = _alerts_per_market_hour(candidates)
    return {
        "info_count": priority_counts["INFO"],
        "notice_count": priority_counts["NOTICE"],
        "important_count": priority_counts["IMPORTANT"],
        "critical_count": priority_counts["CRITICAL"],
        "important_critical_ratio": ratio(important_critical, total_priority),
        "alerts_per_market_hour": per_hour,
        "observed_market_seconds": observed,
        "repeated_episode_signal_count": repeated_signals,
        "repeated_episode_extra_alert_count": extra_alerts,
        "suppression_by_reason": suppression,
    }


def _repeated_episodes(candidates: Sequence[dict[str, object]]) -> tuple[int, int]:
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for row in candidates:
        run_id = row.get("run_id")
        signal_id = row.get("signal_id")
        if not isinstance(run_id, str) or not isinstance(signal_id, str):
            continue
        grouped[(run_id, signal_id)] += 1
    repeated = 0
    extra = 0
    for count in grouped.values():
        if count > 1:
            repeated += 1
            extra += count - 1
    return repeated, extra


def _alerts_per_market_hour(
    candidates: Sequence[dict[str, object]],
) -> tuple[dict[str, object], float]:
    timestamps = [
        float(row["market_timestamp"])
        for row in candidates
        if isinstance(row.get("market_timestamp"), int | float)
    ]
    unique = sorted(set(timestamps))
    if len(unique) < 2:
        return unavailable(UNAVAILABLE_MARKET_TIME), 0.0
    observed = cash_session_overlap_s(unique[0], unique[-1])
    if observed <= 0:
        return unavailable(UNAVAILABLE_MARKET_TIME), observed
    return available_value(len(candidates) / observed * 3600.0), observed


def _host(names: Sequence[str]) -> dict[str, object]:
    presented = _count(names, TelemetryName.ALERT_PRESENTED.value)
    reset = _count(names, TelemetryName.ALERT_BADGE_RESET.value)
    unimplemented = unavailable(UNAVAILABLE_PRODUCER)
    return {
        "alerts_presented": presented,
        "alert_badge_reset": reset,
        "signal_opened": {**unimplemented, "producer": PRODUCER_SIGNAL_OPENED},
        "alert_dismissed": {**unimplemented, "producer": PRODUCER_ALERT_DISMISSED},
        "signal_muted": {**unimplemented, "producer": PRODUCER_SIGNAL_MUTED},
        "open_rate": {**unimplemented, "producer": PRODUCER_SIGNAL_OPENED},
        "dismiss_rate": {**unimplemented, "producer": PRODUCER_ALERT_DISMISSED},
        "mute_rate": {**unimplemented, "producer": PRODUCER_SIGNAL_MUTED},
    }


def _intelligence(records: Sequence[dict[str, object]], names: Sequence[str]) -> dict[str, object]:
    skip_counts: dict[str, int] = defaultdict(int)
    fallback_counts: dict[str, int] = defaultdict(int)
    samples: dict[str, list[float]] = {
        LatencyStage.ROUTER.value: [],
        LatencyStage.MODEL.value: [],
        LatencyStage.PARSE.value: [],
    }
    for row in records:
        name = row.get("name")
        if name == TelemetryName.INTELLIGENCE_SKIPPED.value:
            reason = row.get("decision_reason")
            if isinstance(reason, str):
                skip_counts[reason] += 1
        elif name == TelemetryName.INTELLIGENCE_FALLBACK.value:
            reason = row.get("fallback_reason")
            if isinstance(reason, str):
                fallback_counts[reason] += 1
        elif name == TelemetryName.INTELLIGENCE_LATENCY.value:
            stage = row.get("latency_stage")
            latency = row.get("latency_s")
            if isinstance(stage, str) and stage in samples and isinstance(latency, int | float):
                samples[stage].append(float(latency))
    token_rows = [
        row for row in records if row.get("name") == TelemetryName.INTELLIGENCE_TOKEN_USAGE.value
    ]
    if not token_rows:
        token_usage: dict[str, object] = {
            "available": False,
            "unavailable_reason": UNAVAILABLE_NO_USAGE,
            "token_in_total": None,
            "token_out_total": None,
            "token_total": None,
            "token_events_count": 0,
        }
    else:
        token_in = sum(
            int(row["token_in"]) for row in token_rows if isinstance(row.get("token_in"), int)
        )
        token_out = sum(
            int(row["token_out"]) for row in token_rows if isinstance(row.get("token_out"), int)
        )
        token_usage = {
            "available": True,
            "unavailable_reason": None,
            "token_in_total": token_in,
            "token_out_total": token_out,
            "token_total": token_in + token_out,
            "token_events_count": len(token_rows),
        }
    return {
        "routed": _count(names, TelemetryName.INTELLIGENCE_ROUTED.value),
        "skipped": _count(names, TelemetryName.INTELLIGENCE_SKIPPED.value),
        "succeeded": _count(names, TelemetryName.INTELLIGENCE_SUCCEEDED.value),
        "fallback": _count(names, TelemetryName.INTELLIGENCE_FALLBACK.value),
        "skip_by_decision_reason": dict(sorted(skip_counts.items())),
        "fallback_by_fallback_reason": dict(sorted(fallback_counts.items())),
        "latency": {stage: latency_bundle(samples[stage], stage) for stage in samples},
        "token_usage": token_usage,
    }


def _per_symbol(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in records:
        symbol = row.get("symbol")
        if isinstance(symbol, str):
            by_symbol[symbol].append(row)
    rows: list[dict[str, object]] = []
    for symbol in sorted(by_symbol):
        subset = by_symbol[symbol]
        names = [str(item["name"]) for item in subset if isinstance(item.get("name"), str)]
        rows.append(
            {
                "symbol": symbol,
                "events_generated": _count(names, TelemetryName.EVENT_GENERATED.value),
                "signal_episodes_created": _count(
                    names, TelemetryName.SIGNAL_EPISODE_CREATED.value
                ),
                "alert_candidates": _count(names, TelemetryName.ALERT_CANDIDATE.value),
                "alert_suppressed": _count(names, TelemetryName.ALERT_SUPPRESSED.value),
                "alerts_presented": _count(names, TelemetryName.ALERT_PRESENTED.value),
            }
        )
    return rows
