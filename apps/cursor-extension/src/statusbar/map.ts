import { applyUnreadBadge } from "../alerts/state";
import { displaySymbol, parseStatusBarMaxSymbols, parseSymbolDisplay } from "../host/display";
import type { ActualState, DesiredState, SymbolDisplayMode } from "../host/types";
import { formatPercent, formatPrice } from "../hover/format";
import type { SchedulerLevel, WireMarketState, WireSymbolState } from "../protocol/types";

export type StatusBarKind =
  | "DISCONNECTED"
  | "STARTING"
  | "PAUSED"
  | "IDLE"
  | "STALE"
  | "DELAYED"
  | "ALERT"
  | "HOT"
  | "WARM"
  | "NORMAL"
  | "REPLAY_COMPLETE";

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
  unreadAlertCount?: number;
  symbolNames?: Record<string, string>;
  symbolDisplay?: SymbolDisplayMode;
  maxSymbols?: number;
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

function iconFor(kind: StatusBarKind, feed?: WireMarketState["feed_status"]): string {
  if (kind === "STALE" && feed === "DISCONNECTED") {
    return "$(error)";
  }
  switch (kind) {
    case "STARTING":
      return "$(sync~spin)";
    case "PAUSED":
      return "$(debug-pause)";
    case "DELAYED":
      return "$(clock)";
    case "STALE":
      return "$(warning)";
    case "DISCONNECTED":
      return "$(error)";
    case "ALERT":
      return "$(bell)";
    case "REPLAY_COMPLETE":
      return "$(check)";
    default:
      return "$(circle-outline)";
  }
}

function formatQuote(
  symbol: WireSymbolState,
  names: Record<string, string>,
  mode: SymbolDisplayMode,
): string {
  const label = displaySymbol(symbol.symbol, names, mode, "statusBar");
  if (symbol.price === null) {
    return `${label} --`;
  }
  return `${label} ${formatPrice(symbol.price)} ${formatPercent(symbol.change_day)}`;
}

function quoteLine(input: StatusBarInput, market: WireMarketState): string | undefined {
  if (market.symbols.length === 0) {
    return undefined;
  }
  const names = input.symbolNames ?? {};
  const mode = parseSymbolDisplay(input.symbolDisplay);
  const max = parseStatusBarMaxSymbols(input.maxSymbols);
  const shown = market.symbols.slice(0, max);
  const overflow = Math.max(0, market.symbols.length - max);
  const parts = shown.map((item) => formatQuote(item, names, mode));
  if (overflow > 0) {
    parts.push(`+${overflow}`);
  }
  return parts.join(" | ");
}

function compose(
  kind: StatusBarKind,
  body: string,
  input: StatusBarInput,
): StatusBarModel {
  return {
    kind,
    text: applyUnreadBadge(
      `${iconFor(kind, input.market?.feed_status)} ${body}`,
      input.unreadAlertCount ?? 0,
    ),
    tooltip: tooltip(kind, input),
    tone: "default",
  };
}

export function mapStatusBar(input: StatusBarInput): StatusBarModel {
  const hold = input.alertHoldMs ?? DEFAULT_ALERT_HOLD_MS;
  const elapsed = input.lastAlertAt === undefined ? hold : input.now - input.lastAlertAt;
  const alertActive = input.lastAlertAt !== undefined && elapsed >= 0 && elapsed < hold;
  const quotes = input.market !== undefined ? quoteLine(input, input.market) : undefined;

  if (input.actual === "STARTING") {
    return compose("STARTING", "启动中", input);
  }
  if (
    input.actual === "DISCONNECTED" ||
    input.actual === "STOPPED" ||
    input.actual === "STOPPING"
  ) {
    return compose("DISCONNECTED", quotes ?? "已断开", input);
  }
  if (input.actual === "PAUSED") {
    return compose("PAUSED", quotes ?? "已暂停", input);
  }

  if (input.market === undefined) {
    return compose("STARTING", "启动中", input);
  }

  if (input.market.watchlist_count === 0 && input.market.symbols.length === 0) {
    return compose("IDLE", "无标的", input);
  }

  const feed = input.market.feed_status;
  if (feed === "STALE") {
    return compose("STALE", quotes ?? "--", input);
  }
  if (feed === "DISCONNECTED") {
    return compose("STALE", quotes ?? "--", input);
  }

  if (alertActive) {
    return compose("ALERT", quotes ?? "--", input);
  }

  if (input.market.replay_complete === true) {
    return compose("REPLAY_COMPLETE", "Replay 已结束", input);
  }

  if (feed === "DELAYED") {
    return compose("DELAYED", quotes ?? "--", input);
  }

  const level = highestSchedulerLevel(input.market);
  if (level === "HOT") {
    return compose("HOT", quotes ?? "--", input);
  }
  if (level === "WARM") {
    return compose("WARM", quotes ?? "--", input);
  }
  return compose("NORMAL", quotes ?? "--", input);
}
