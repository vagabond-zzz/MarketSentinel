from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from market_sentinel.evaluation.reader import LoadedTelemetry
from market_sentinel.evaluation.report import (
    KNOWN_FALLBACK_REASONS,
    KNOWN_SKIP_REASONS,
    KNOWN_SUPPRESSION_REASONS,
    PRODUCER_ALERT_DISMISSED,
    PRODUCER_SIGNAL_MUTED,
    PRODUCER_SIGNAL_OPENED,
    UNAVAILABLE_DENOMINATOR_ZERO,
    UNAVAILABLE_MARKET_SCOPE,
    UNAVAILABLE_MARKET_TIME,
    UNAVAILABLE_NO_FEEDBACK,
    UNAVAILABLE_NO_USAGE,
    UNAVAILABLE_PRODUCER,
    EvaluationReport,
    available_value,
    unavailable,
)
from market_sentinel.evaluation.stats import latency_bundle, ratio
from market_sentinel.market_data.session import (
    cash_session_overlap_s,
    is_a_share_symbol,
    session_id,
)
from market_sentinel.telemetry.contract import FeedbackLabel, LatencyStage, TelemetryName

_PRIORITIES = ("INFO", "NOTICE", "IMPORTANT", "CRITICAL")
_CANDIDATE = TelemetryName.ALERT_CANDIDATE.value
_SKIPPED = TelemetryName.INTELLIGENCE_SKIPPED.value
_FALLBACK = TelemetryName.INTELLIGENCE_FALLBACK.value
_SUPPRESSED = TelemetryName.ALERT_SUPPRESSED.value


def evaluate(
    loaded: LoadedTelemetry,
    *,
    run_id: str | None = None,
    cluster_tracker_seen_count: int | None = None,
    feedback: LoadedTelemetry | None = None,
) -> EvaluationReport:
    records = [
        row
        for row in loaded.records
        if isinstance(row.get("name"), str) and (run_id is None or row.get("run_id") == run_id)
    ]
    names = [str(row["name"]) for row in records]
    intelligence, skip_unknown, fallback_unknown = _intelligence(records, names)
    suppression, suppression_unknown = _suppression(records)
    semantic = skip_unknown + fallback_unknown + suppression_unknown
    market = _market_metrics(records)
    dates = _per_market_date(records)
    fb_loaded = feedback or LoadedTelemetry((), (), 0, 0, False, True)
    fb_records = [row for row in fb_loaded.records if run_id is None or row.get("run_id") == run_id]
    return EvaluationReport(
        metadata=_metadata(records, run_id),
        data_quality=_data_quality(
            loaded, records, run_id, market, semantic, fb_loaded, len(fb_records)
        ),
        pipeline=_pipeline(records, names, cluster_tracker_seen_count),
        alert_noise=_alert_noise(records, market, suppression, suppression_unknown),
        host_interaction=_host(names),
        intelligence=intelligence,
        per_symbol=_per_symbol(records),
        per_run=market["per_run"],
        per_market_date=dates,
        explicit_feedback=_explicit_feedback(fb_records, records),
    )


def _count(names: Sequence[str], name: str) -> int:
    return sum(1 for item in names if item == name)


def _funnel(records: Sequence[dict[str, object]]) -> dict[str, int]:
    names = [str(row["name"]) for row in records if isinstance(row.get("name"), str)]
    return {
        "events_generated": _count(names, TelemetryName.EVENT_GENERATED.value),
        "signal_episodes_created": _count(names, TelemetryName.SIGNAL_EPISODE_CREATED.value),
        "alert_candidates": _count(names, _CANDIDATE),
        "alert_suppressed": _count(names, _SUPPRESSED),
        "alerts_presented": _count(names, TelemetryName.ALERT_PRESENTED.value),
    }


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
    market: dict[str, object],
    semantic: int,
    feedback: LoadedTelemetry,
    feedback_records_used: int,
) -> dict[str, object]:
    timestamps = [
        float(row["market_timestamp"])
        for row in records
        if isinstance(row.get("market_timestamp"), int | float)
    ]
    if timestamps:
        coverage = {
            "min_market_timestamp": min(timestamps),
            "max_market_timestamp": max(timestamps),
            "observed_market_seconds": market["observed_market_seconds"],
        }
    else:
        coverage = {
            "min_market_timestamp": None,
            "max_market_timestamp": None,
            "observed_market_seconds": 0.0,
        }
    run_ids = sorted({str(row["run_id"]) for row in records if isinstance(row.get("run_id"), str)})
    warning = (not loaded.healthy) or (not feedback.healthy) or semantic > 0
    records_read = (
        loaded.records_read + feedback.records_read
        if run_id is None
        else len(records) + feedback_records_used
    )
    return {
        "input_files": list(loaded.input_files) + list(feedback.input_files),
        "records_read": records_read,
        "malformed_complete_lines": (
            loaded.malformed_complete_lines + feedback.malformed_complete_lines
        ),
        "skipped_trailing_partial": loaded.skipped_trailing_partial
        or feedback.skipped_trailing_partial,
        "healthy": loaded.healthy and feedback.healthy,
        "data_quality_warning": warning,
        "semantic_warning_count": semantic,
        "runs_insufficient_market_time": list(market["runs_insufficient_market_time"]),
        "runs_unsupported_market_scope": list(market["runs_unsupported_market_scope"]),
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
    candidates = _count(names, _CANDIDATE)
    suppressed = _count(names, _SUPPRESSED)
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


def _alert_noise(
    records: Sequence[dict[str, object]],
    market: dict[str, object],
    suppression: dict[str, int],
    suppression_unknown: int,
) -> dict[str, object]:
    candidates = [row for row in records if row.get("name") == _CANDIDATE]
    priority_counts = {key: 0 for key in _PRIORITIES}
    for row in candidates:
        priority = row.get("priority")
        if isinstance(priority, str) and priority in priority_counts:
            priority_counts[priority] += 1
    total_priority = sum(priority_counts.values())
    important_critical = priority_counts["IMPORTANT"] + priority_counts["CRITICAL"]
    repeated_signals, extra_alerts = _repeated_episodes(candidates)
    return {
        "info_count": priority_counts["INFO"],
        "notice_count": priority_counts["NOTICE"],
        "important_count": priority_counts["IMPORTANT"],
        "critical_count": priority_counts["CRITICAL"],
        "important_critical_ratio": ratio(important_critical, total_priority),
        "alerts_per_market_hour": market["alerts_per_market_hour"],
        "observed_market_seconds": market["observed_market_seconds"],
        "repeated_episode_signal_count": repeated_signals,
        "repeated_episode_extra_alert_count": extra_alerts,
        "suppression_by_reason": suppression,
        "unrecognized_suppression_reason_count": suppression_unknown,
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


def _market_scope(rows: Sequence[dict[str, object]]) -> str:
    """ashare | unsupported | empty — empty means no market-timestamped observations."""
    stamped = [row for row in rows if isinstance(row.get("market_timestamp"), int | float)]
    if not stamped:
        return "empty"
    saw_ashare = False
    saw_other = False
    saw_symbol = False
    for row in stamped:
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol == "":
            continue
        saw_symbol = True
        if is_a_share_symbol(symbol):
            saw_ashare = True
        else:
            saw_other = True
    if saw_other or not saw_symbol:
        return "unsupported"
    if saw_ashare:
        return "ashare"
    return "unsupported"


def _run_exposure(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    stamped = [
        float(row["market_timestamp"])
        for row in rows
        if isinstance(row.get("market_timestamp"), int | float)
    ]
    unique = sorted(set(stamped))
    candidates = sum(1 for row in rows if row.get("name") == _CANDIDATE)
    scope = _market_scope(rows)
    funnel = _funnel(rows)
    if scope == "unsupported":
        return {
            **funnel,
            "observed_market_seconds": 0.0,
            "alerts_per_market_hour": unavailable(UNAVAILABLE_MARKET_SCOPE),
            "scope": scope,
            "candidates": candidates,
            "exposure_ok": False,
        }
    if len(unique) < 2:
        return {
            **funnel,
            "observed_market_seconds": 0.0,
            "alerts_per_market_hour": unavailable(UNAVAILABLE_MARKET_TIME),
            "scope": scope,
            "candidates": candidates,
            "exposure_ok": False,
        }
    observed = cash_session_overlap_s(unique[0], unique[-1])
    if observed <= 0:
        return {
            **funnel,
            "observed_market_seconds": observed,
            "alerts_per_market_hour": unavailable(UNAVAILABLE_MARKET_TIME),
            "scope": scope,
            "candidates": candidates,
            "exposure_ok": False,
        }
    return {
        **funnel,
        "observed_market_seconds": observed,
        "alerts_per_market_hour": available_value(candidates / observed * 3600.0),
        "scope": scope,
        "candidates": candidates,
        "exposure_ok": True,
    }


def _group_by_run(records: Sequence[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in records:
        run_id = row.get("run_id")
        if isinstance(run_id, str):
            grouped[run_id].append(row)
    return grouped


def _market_metrics(records: Sequence[dict[str, object]]) -> dict[str, object]:
    grouped = _group_by_run(records)
    orphan_candidates = [
        row
        for row in records
        if row.get("name") == _CANDIDATE and not isinstance(row.get("run_id"), str)
    ]
    per_run: list[dict[str, object]] = []
    insufficient: list[str] = []
    unsupported: list[str] = []
    exposures: dict[str, dict[str, object]] = {}
    for run_id in sorted(grouped):
        exposure = _run_exposure(grouped[run_id])
        exposures[run_id] = exposure
        per_run.append(
            {
                "run_id": run_id,
                "events_generated": exposure["events_generated"],
                "signal_episodes_created": exposure["signal_episodes_created"],
                "alert_candidates": exposure["alert_candidates"],
                "alert_suppressed": exposure["alert_suppressed"],
                "alerts_presented": exposure["alerts_presented"],
                "observed_market_seconds": exposure["observed_market_seconds"],
                "alerts_per_market_hour": exposure["alerts_per_market_hour"],
            }
        )
        if exposure["scope"] == "unsupported":
            unsupported.append(run_id)
        elif int(exposure["candidates"]) > 0 and not exposure["exposure_ok"]:
            insufficient.append(run_id)
    if orphan_candidates:
        insufficient.append("")

    fail_scope = bool(unsupported)
    fail_time = bool(insufficient)
    if fail_scope:
        rate: dict[str, object] = unavailable(UNAVAILABLE_MARKET_SCOPE)
        observed = 0.0
    elif fail_time:
        rate = unavailable(UNAVAILABLE_MARKET_TIME)
        observed = 0.0
    else:
        observed = 0.0
        candidates = 0
        for exposure in exposures.values():
            if exposure["exposure_ok"]:
                observed += float(exposure["observed_market_seconds"])
            candidates += int(exposure["candidates"])
        candidates += len(orphan_candidates)
        if observed <= 0:
            rate = unavailable(UNAVAILABLE_MARKET_TIME)
            observed = 0.0
        else:
            rate = available_value(candidates / observed * 3600.0)
    return {
        "alerts_per_market_hour": rate,
        "observed_market_seconds": observed,
        "per_run": per_run,
        "runs_insufficient_market_time": [item for item in insufficient if item != ""],
        "runs_unsupported_market_scope": unsupported,
    }


def _per_market_date(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_date: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in records:
        stamp = row.get("market_timestamp")
        if isinstance(stamp, int | float):
            by_date[session_id(float(stamp))].append(row)
    rows: list[dict[str, object]] = []
    for date in sorted(by_date):
        subset = by_date[date]
        funnel = _funnel(subset)
        metrics = _market_metrics(subset)
        rows.append(
            {
                "market_date": date,
                **funnel,
                "observed_market_seconds": metrics["observed_market_seconds"],
                "alerts_per_market_hour": metrics["alerts_per_market_hour"],
            }
        )
    return rows


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


_FEEDBACK_LABELS = tuple(item.value for item in FeedbackLabel)


def _explicit_feedback(
    feedback_rows: Sequence[dict[str, object]],
    telemetry_rows: Sequence[dict[str, object]],
) -> dict[str, object]:
    valid: list[dict[str, object]] = []
    for row in feedback_rows:
        label = row.get("label")
        signal_id = row.get("signal_id")
        if not isinstance(label, str) or label not in _FEEDBACK_LABELS:
            continue
        if not isinstance(signal_id, str) or signal_id.strip() == "":
            continue
        valid.append(row)
    counts = {key: sum(1 for row in valid if row.get("label") == key) for key in _FEEDBACK_LABELS}
    total = len(valid)
    useful_rate = (
        unavailable(UNAVAILABLE_NO_FEEDBACK)
        if total == 0
        else available_value(counts["useful"] / total)
    )
    presented_ids = {
        str(row["signal_id"])
        for row in telemetry_rows
        if row.get("name") == TelemetryName.ALERT_PRESENTED.value
        and isinstance(row.get("signal_id"), str)
        and str(row["signal_id"]).strip() != ""
    }
    feedback_ids = {str(row["signal_id"]) for row in valid}
    coverage = (
        unavailable(UNAVAILABLE_DENOMINATOR_ZERO)
        if not presented_ids
        else available_value(len(feedback_ids.intersection(presented_ids)) / len(presented_ids))
    )
    return {
        "feedback_count": total,
        "useful_count": counts["useful"],
        "not_useful_count": counts["not_useful"],
        "too_noisy_count": counts["too_noisy"],
        "too_late_count": counts["too_late"],
        "useful_rate": useful_rate,
        "feedback_coverage": coverage,
    }


def _suppression(records: Sequence[dict[str, object]]) -> tuple[dict[str, int], int]:
    counts = {key: 0 for key in KNOWN_SUPPRESSION_REASONS}
    unknown = 0
    for row in records:
        if row.get("name") != _SUPPRESSED:
            continue
        reason = row.get("suppression_reason")
        if isinstance(reason, str) and reason in counts:
            counts[reason] += 1
        else:
            unknown += 1
    return counts, unknown


def _intelligence(
    records: Sequence[dict[str, object]], names: Sequence[str]
) -> tuple[dict[str, object], int, int]:
    skip_counts = {key: 0 for key in KNOWN_SKIP_REASONS}
    fallback_counts = {key: 0 for key in KNOWN_FALLBACK_REASONS}
    skip_unknown = 0
    fallback_unknown = 0
    samples: dict[str, list[float]] = {
        LatencyStage.ROUTER.value: [],
        LatencyStage.MODEL.value: [],
        LatencyStage.PARSE.value: [],
    }
    for row in records:
        name = row.get("name")
        if name == _SKIPPED:
            reason = row.get("decision_reason")
            if isinstance(reason, str) and reason in skip_counts:
                skip_counts[reason] += 1
            else:
                skip_unknown += 1
        elif name == _FALLBACK:
            reason = row.get("fallback_reason")
            if isinstance(reason, str) and reason in fallback_counts:
                fallback_counts[reason] += 1
            else:
                fallback_unknown += 1
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
    payload = {
        "routed": _count(names, TelemetryName.INTELLIGENCE_ROUTED.value),
        "skipped": _count(names, _SKIPPED),
        "succeeded": _count(names, TelemetryName.INTELLIGENCE_SUCCEEDED.value),
        "fallback": _count(names, _FALLBACK),
        "skip_by_decision_reason": skip_counts,
        "fallback_by_fallback_reason": fallback_counts,
        "unrecognized_skip_reason_count": skip_unknown,
        "unrecognized_fallback_reason_count": fallback_unknown,
        "latency": {stage: latency_bundle(samples[stage], stage) for stage in samples},
        "token_usage": token_usage,
    }
    return payload, skip_unknown, fallback_unknown


def _per_symbol(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in records:
        symbol = row.get("symbol")
        if isinstance(symbol, str):
            by_symbol[symbol].append(row)
    rows: list[dict[str, object]] = []
    for symbol in sorted(by_symbol):
        subset = by_symbol[symbol]
        funnel = _funnel(subset)
        rows.append({"symbol": symbol, **funnel})
    return rows
