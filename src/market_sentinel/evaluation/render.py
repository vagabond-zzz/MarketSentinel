from __future__ import annotations

from market_sentinel.evaluation.report import EvaluationReport


def render_text(report: EvaluationReport) -> str:
    """Human view of an EvaluationReport. Not the source of truth."""
    record = report.to_record()
    quality = record["data_quality"]
    pipeline = record["pipeline"]
    noise = record["alert_noise"]
    host = record["host_interaction"]
    intel = record["intelligence"]
    warning = "yes" if quality["data_quality_warning"] else "no"
    lines = [
        "# Market Sentinel evaluation",
        "",
        "## Data quality",
        f"- data_quality_warning: {warning}",
        f"- healthy: {quality['healthy']}",
        f"- records_read: {quality['records_read']}",
        f"- malformed_complete_lines: {quality['malformed_complete_lines']}",
        f"- skipped_trailing_partial: {quality['skipped_trailing_partial']}",
        f"- semantic_warning_count: {quality['semantic_warning_count']}",
        f"- input_files: {len(quality['input_files'])}",
        "",
        "## Pipeline",
        f"- events_generated: {pipeline['events_generated']}",
        f"- events_deduped: {pipeline['events_deduped']}",
        f"- events_clustered: {pipeline['events_clustered']}",
        f"- signal_episodes_created: {pipeline['signal_episodes_created']}",
        f"- signal_escalations: {pipeline['signal_escalations']}",
        f"- alert_candidates: {pipeline['alert_candidates']}",
        f"- alert_suppressed: {pipeline['alert_suppressed']}",
        f"- alerts_presented: {pipeline['alerts_presented']}",
        f"- cluster_tracker_seen_count: {pipeline['cluster_tracker_seen_count']}",
        f"- dedupe_rate: {_fmt_ratio(pipeline['dedupe_rate'])}",
        f"- event_to_signal_rate: {_fmt_ratio(pipeline['event_to_signal_rate'])}",
        "",
        "## Alert noise",
        f"- NOTICE: {noise['notice_count']} IMPORTANT: {noise['important_count']}"
        f" CRITICAL: {noise['critical_count']}",
        f"- important_critical_ratio: {_fmt_ratio(noise['important_critical_ratio'])}",
        f"- alerts_per_market_hour: {_fmt_optional(noise['alerts_per_market_hour'])}",
        f"- observed_market_seconds: {noise['observed_market_seconds']}",
        f"- repeated_episode_signal_count: {noise['repeated_episode_signal_count']}",
        f"- repeated_episode_extra_alert_count: {noise['repeated_episode_extra_alert_count']}",
        f"- suppression_by_reason: {noise['suppression_by_reason']}",
        f"- per_run: {len(record['per_run'])}",
        f"- per_market_date: {len(record['per_market_date'])}",
        "",
        "## Host interaction",
        f"- alerts_presented: {host['alerts_presented']}",
        f"- alert_badge_reset: {host['alert_badge_reset']}",
        f"- open_rate: {_fmt_optional(host['open_rate'])}",
        f"- dismiss_rate: {_fmt_optional(host['dismiss_rate'])}",
        f"- mute_rate: {_fmt_optional(host['mute_rate'])}",
        "",
        "## Intelligence",
        f"- routed: {intel['routed']} skipped: {intel['skipped']}"
        f" succeeded: {intel['succeeded']} fallback: {intel['fallback']}",
        f"- token_usage: {_fmt_tokens(intel['token_usage'])}",
    ]
    return "\n".join(lines) + "\n"


def _fmt_ratio(value: object) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.4f}"


def _fmt_optional(payload: object) -> str:
    if not isinstance(payload, dict):
        return "unavailable"
    if payload.get("available") is not True:
        reason = payload.get("unavailable_reason") or "unavailable"
        producer = payload.get("producer")
        if producer:
            return f"unavailable ({reason}; producer={producer})"
        return f"unavailable ({reason})"
    return str(payload.get("value"))


def _fmt_tokens(payload: object) -> str:
    if not isinstance(payload, dict) or payload.get("available") is not True:
        return "unavailable"
    return (
        f"in={payload.get('token_in_total')} out={payload.get('token_out_total')}"
        f" events={payload.get('token_events_count')}"
    )
