import type { ActualState, DesiredState } from "../host/types";
import type { SchedulerLevel, WireMarketState } from "../protocol/types";

export type StatusBarKind =
  | "DISCONNECTED"
  | "STARTING"
  | "PAUSED"
  | "STALE"
  | "ALERT"
  | "HOT"
  | "WARM"
  | "NORMAL";

export type StatusBarTone = "default" | "warning" | "error";

export interface StatusBarModel {
  kind: StatusBarKind;
  text: string;
  tooltip: string;
  tone: StatusBarTone;
}

export interface StatusBarInput {
  actual: ActualState;
  desired: DesiredState;
  market?: WireMarketState;
  lastAlertAt?: number;
  now: number;
  alertHoldMs?: number;
  lastError?: string;
  restartNeeded?: boolean;
}

export const DEFAULT_ALERT_HOLD_MS = 15_000;

function highestSchedulerLevel(market: WireMarketState | undefined): SchedulerLevel {
  let hot = false;
  let warm = false;
  for (const symbol of market?.symbols ?? []) {
    if (symbol.scheduler_level === "HOT") {
      hot = true;
    } else if (symbol.scheduler_level === "WARM") {
      warm = true;
    }
  }
  if (hot) {
    return "HOT";
  }
  if (warm) {
    return "WARM";
  }
  return "COLD";
}

function tooltip(kind: StatusBarKind, input: StatusBarInput): string {
  const parts = [`Market Sentinel · ${kind}`];
  if (input.market !== undefined) {
    parts.push(`feed=${input.market.feed_status}`);
    parts.push(`symbols=${input.market.watchlist_count}`);
  }
  if (input.actual !== "RUNNING") {
    parts.push(`host=${input.actual}`);
  }
  if (input.desired === "PAUSED") {
    parts.push("desired=PAUSED");
  }
  if (input.restartNeeded === true) {
    parts.push("restart core to apply settings");
  }
  if (input.lastError !== undefined && input.lastError.length > 0) {
    parts.push(input.lastError);
  }
  return parts.join(" · ");
}

function model(kind: StatusBarKind, tone: StatusBarTone, input: StatusBarInput): StatusBarModel {
  return {
    kind,
    text: `MS ${kind}`,
    tooltip: tooltip(kind, input),
    tone,
  };
}

export function mapStatusBar(input: StatusBarInput): StatusBarModel {
  const hold = input.alertHoldMs ?? DEFAULT_ALERT_HOLD_MS;
  const alertActive =
    input.lastAlertAt !== undefined && input.now - input.lastAlertAt >= 0 && input.now - input.lastAlertAt <= hold;

  if (input.actual === "STARTING") {
    return model("STARTING", "default", input);
  }
  if (
    input.actual === "DISCONNECTED" ||
    input.actual === "STOPPED" ||
    input.actual === "STOPPING"
  ) {
    return model("DISCONNECTED", "error", input);
  }
  if (input.actual === "PAUSED") {
    return model("PAUSED", "default", input);
  }

  const feed = input.market?.feed_status;
  if (feed === "STALE" || feed === "DISCONNECTED") {
    return model("STALE", "error", input);
  }

  if (alertActive) {
    return model("ALERT", "warning", input);
  }

  const level = highestSchedulerLevel(input.market);
  if (level === "HOT") {
    return model("HOT", "warning", input);
  }
  if (level === "WARM") {
    return model("WARM", "default", input);
  }
  return model("NORMAL", "default", input);
}
