import type { ActualState } from "../host/types";
import {
  displaySymbol,
  parseSymbolDisplay,
  type IntelligenceMode,
  type SymbolDisplayMode,
} from "../host/display";
import type {
  FeedStatus,
  IntelligenceStatus,
  SchedulerLevel,
  WireMarketState,
  WireSignal,
  WireSymbolState,
} from "../protocol/types";
import {
  fallbackReasonLabel,
  formatClock,
  formatPercent,
  formatPrice,
  formatRatio,
  formatRsi,
} from "./format";

export const MAX_HOVER_SIGNALS = 3;

const LEVEL_ORDER: Record<SchedulerLevel, number> = {
  HOT: 0,
  WARM: 1,
  COLD: 2,
};

export type AiStatusLabel =
  | "关闭"
  | "待重启"
  | "不可用（Rule-only）"
  | "已启用"
  | "处理中"
  | "已增强"
  | "回退";

export interface HoverSignalView {
  priority: string;
  direction: string;
  family: string;
  body: string;
  ruleLabel: string;
  aiLabel: string;
  aiBody?: string;
  aiMeta?: string;
}

export interface HoverSymbolView {
  symbol: string;
  displayName: string;
  level: SchedulerLevel;
  feedStatus?: FeedStatus;
  price: string;
  changeDay: string;
  change1m: string;
  change5m: string;
  change15m: string;
  volumeRatio1m: string;
  volumeRatio5m: string;
  ema5: string;
  ema20: string;
  rsi14: string;
  vwap: string;
  vwapBias?: string;
  sessionHighObs: string;
  sessionLowObs: string;
  sessionHighRef: string;
  sessionLowRef: string;
  signals: HoverSignalView[];
  moreSignals: number;
}

export interface HoverModel {
  title: string;
  enableDetails: boolean;
  headline: string;
  connection?: string;
  feedSource?: string;
  aiStatus?: AiStatusLabel;
  unreadLine?: string;
  lastUpdate?: string;
  replayMode?: boolean;
  replayStatus?: string;
  lifecycleMessage?: string;
  outputHint?: string;
  unreadAlertCount: number;
  feed?: FeedStatus;
  symbolCount?: number;
  hotCount?: number;
  warmCount?: number;
  symbols: HoverSymbolView[];
}

export interface HoverInput {
  actual: ActualState;
  market?: WireMarketState;
  enableHoverDetails?: boolean;
  unreadAlertCount?: number;
  symbolNames?: Record<string, string>;
  symbolDisplay?: SymbolDisplayMode;
  intelligenceMode?: IntelligenceMode;
  restartNeeded?: boolean;
}

function countLevels(symbols: readonly WireSymbolState[]): { hot: number; warm: number } {
  let hot = 0;
  let warm = 0;
  for (const symbol of symbols) {
    if (symbol.scheduler_level === "HOT") {
      hot += 1;
    } else if (symbol.scheduler_level === "WARM") {
      warm += 1;
    }
  }
  return { hot, warm };
}

function sortSymbols(symbols: readonly WireSymbolState[]): WireSymbolState[] {
  return symbols
    .map((symbol, index) => ({ symbol, index }))
    .sort((left, right) => {
      const delta = LEVEL_ORDER[left.symbol.scheduler_level] - LEVEL_ORDER[right.symbol.scheduler_level];
      return delta !== 0 ? delta : left.index - right.index;
    })
    .map((item) => item.symbol);
}

function mapSignal(signal: WireSignal): HoverSignalView {
  const status = signal.intelligence?.status;
  let aiLabel = "AI 增强";
  let aiBody: string | undefined;
  let aiMeta: string | undefined;
  if (status === "queued" || status === "running") {
    aiBody = "处理中…";
  } else if (status === "enriched") {
    aiBody = signal.intelligence?.summary;
    const confidence = signal.intelligence?.confidence;
    aiMeta =
      confidence !== undefined
        ? `状态：已增强 · confidence ${confidence.toFixed(2)}`
        : "状态：已增强";
  } else if (status === "fallback") {
    const reason = fallbackReasonLabel(signal.intelligence?.fallback_reason);
    aiBody = "本次未完成";
    aiMeta = reason;
  } else {
    aiLabel = "";
  }
  return {
    priority: signal.priority.toUpperCase(),
    direction: signal.direction,
    family: signal.family,
    body: signal.summary.length > 0 ? signal.summary : signal.title,
    ruleLabel: "规则信号",
    aiLabel,
    aiBody,
    aiMeta,
  };
}

function vwapBias(symbol: WireSymbolState): string | undefined {
  if (symbol.above_vwap === true) {
    return "当前位于 VWAP 上方";
  }
  if (symbol.above_vwap === false) {
    return "当前位于 VWAP 下方";
  }
  return undefined;
}

function mapSymbol(
  symbol: WireSymbolState,
  aggregateFeed: FeedStatus,
  names: Record<string, string>,
  mode: SymbolDisplayMode,
): HoverSymbolView {
  const shown = symbol.active_signals.slice(0, MAX_HOVER_SIGNALS);
  return {
    symbol: symbol.symbol,
    displayName: displaySymbol(symbol.symbol, names, mode, "hover"),
    level: symbol.scheduler_level,
    feedStatus: symbol.feed_status === aggregateFeed ? undefined : symbol.feed_status,
    price: formatPrice(symbol.price),
    changeDay: formatPercent(symbol.change_day),
    change1m: formatPercent(symbol.change_1m),
    change5m: formatPercent(symbol.change_5m),
    change15m: formatPercent(symbol.change_15m),
    volumeRatio1m: formatRatio(symbol.volume_ratio_1m),
    volumeRatio5m: formatRatio(symbol.volume_ratio_5m),
    ema5: formatPrice(symbol.ema5),
    ema20: formatPrice(symbol.ema20),
    rsi14: formatRsi(symbol.rsi14),
    vwap: formatPrice(symbol.vwap),
    vwapBias: vwapBias(symbol),
    sessionHighObs: formatPrice(symbol.session_high_obs),
    sessionLowObs: formatPrice(symbol.session_low_obs),
    sessionHighRef: formatPrice(symbol.session_high_ref),
    sessionLowRef: formatPrice(symbol.session_low_ref),
    signals: shown.map(mapSignal),
    moreSignals: Math.max(0, symbol.active_signals.length - MAX_HOVER_SIGNALS),
  };
}

function collectStatuses(market: WireMarketState): IntelligenceStatus[] {
  const out: IntelligenceStatus[] = [];
  for (const symbol of market.symbols) {
    for (const signal of symbol.active_signals) {
      if (signal.intelligence?.status !== undefined) {
        out.push(signal.intelligence.status);
      }
    }
  }
  return out;
}

export function mapAiStatus(
  market: WireMarketState | undefined,
  requested: IntelligenceMode = "inherit",
  restartNeeded = false,
): AiStatusLabel {
  const actual = market?.intelligence_enabled === true;
  if (requested === "off") {
    return "关闭";
  }
  if (requested === "on" && !actual) {
    return restartNeeded ? "待重启" : "不可用（Rule-only）";
  }
  if (!actual || market === undefined) {
    return "关闭";
  }
  const statuses = collectStatuses(market);
  if (statuses.some((item) => item === "queued" || item === "running")) {
    return "处理中";
  }
  if (statuses.some((item) => item === "enriched")) {
    return "已增强";
  }
  if (statuses.some((item) => item === "fallback")) {
    return "回退";
  }
  return "已启用";
}

function connectionLabel(actual: ActualState, market: WireMarketState | undefined): string {
  if (actual === "STARTING") {
    return "启动中";
  }
  if (actual === "PAUSED") {
    return "已暂停";
  }
  if (actual === "DISCONNECTED" || actual === "STOPPING" || actual === "STOPPED") {
    return "异常";
  }
  if (market?.feed_status === "DISCONNECTED" || market?.feed_status === "STALE") {
    return "异常";
  }
  return "正常";
}

function lastUpdate(market: WireMarketState | undefined): string {
  if (market?.last_market_timestamp != null) {
    return formatClock(market.last_market_timestamp);
  }
  let latest: number | undefined;
  for (const symbol of market?.symbols ?? []) {
    if (symbol.market_timestamp != null) {
      latest = latest === undefined ? symbol.market_timestamp : Math.max(latest, symbol.market_timestamp);
    }
  }
  return formatClock(latest);
}

function emptyLifecycle(
  actual: ActualState,
  market: WireMarketState | undefined,
): { message: string; hint?: string } | undefined {
  if (actual === "STARTING") {
    return { message: "Core starting" };
  }
  if (actual === "STOPPING") {
    return { message: "Core stopping" };
  }
  if (actual === "STOPPED") {
    return { message: "Monitoring stopped" };
  }
  if (actual === "DISCONNECTED" && market === undefined) {
    return { message: "Core disconnected", hint: "Click the StatusBar to view Output" };
  }
  if (actual === "RUNNING" && market === undefined) {
    return { message: "Core starting" };
  }
  return undefined;
}

function shortHeadline(parts: {
  lifecycle?: string;
  feed?: FeedStatus;
  symbolCount?: number;
  hot?: number;
  warm?: number;
  unread?: number;
  ai?: AiStatusLabel;
}): string {
  const unread =
    parts.unread !== undefined && parts.unread > 0 ? `unread=${parts.unread}` : undefined;
  if (parts.lifecycle !== undefined) {
    return ["Market Sentinel", parts.lifecycle, unread]
      .filter((part): part is string => part !== undefined)
      .join(" · ");
  }
  return [
    "Market Sentinel",
    parts.feed,
    parts.symbolCount !== undefined ? `symbols=${parts.symbolCount}` : undefined,
    parts.hot !== undefined ? `HOT=${parts.hot}` : undefined,
    parts.warm !== undefined ? `WARM=${parts.warm}` : undefined,
    parts.ai !== undefined ? `AI=${parts.ai}` : undefined,
    unread,
  ]
    .filter((part): part is string => part !== undefined)
    .join(" · ");
}

function withUnread(model: Omit<HoverModel, "unreadAlertCount">, unread: number): HoverModel {
  return { ...model, unreadAlertCount: unread };
}

export function mapHover(input: HoverInput): HoverModel {
  const enableDetails = input.enableHoverDetails !== false;
  const unread = input.unreadAlertCount ?? 0;
  const names = input.symbolNames ?? {};
  const mode = parseSymbolDisplay(input.symbolDisplay);
  const lifecycle = emptyLifecycle(input.actual, input.market);
  if (lifecycle !== undefined) {
    return withUnread(
      {
        title: "Market Sentinel",
        enableDetails,
        headline: shortHeadline({ lifecycle: lifecycle.message, unread }),
        connection: connectionLabel(input.actual, input.market),
        aiStatus: mapAiStatus(input.market, input.intelligenceMode, input.restartNeeded),
        unreadLine: `未读提醒：${unread}`,
        lastUpdate: DASH_UPDATE,
        lifecycleMessage: lifecycle.message,
        outputHint: lifecycle.hint,
        symbols: [],
      },
      unread,
    );
  }

  const market = input.market;
  if (market === undefined) {
    return withUnread(
      {
        title: "Market Sentinel",
        enableDetails,
        headline: shortHeadline({ lifecycle: "Core starting", unread }),
        connection: "启动中",
        aiStatus: mapAiStatus(undefined, input.intelligenceMode, input.restartNeeded),
        unreadLine: `未读提醒：${unread}`,
        lastUpdate: DASH_UPDATE,
        lifecycleMessage: "Core starting",
        symbols: [],
      },
      unread,
    );
  }

  if (market.watchlist_count === 0 && market.symbols.length === 0) {
    return withUnread(
      {
        title: "Market Sentinel",
        enableDetails,
        headline: "Market Sentinel · No symbols configured",
        connection: connectionLabel(input.actual, market),
        aiStatus: mapAiStatus(market, input.intelligenceMode, input.restartNeeded),
        unreadLine: `未读提醒：${unread}`,
        lastUpdate: lastUpdate(market),
        lifecycleMessage: "No symbols configured",
        outputHint: "Configure marketSentinel.watchlist to start monitoring",
        symbols: [],
      },
      unread,
    );
  }

  const { hot, warm } = countLevels(market.symbols);
  const aiStatus = mapAiStatus(market, input.intelligenceMode, input.restartNeeded);
  const replay = market.replay_complete === true;
  return withUnread(
    {
      title: "Market Sentinel",
      enableDetails,
      headline: shortHeadline({
        feed: market.feed_status,
        symbolCount: market.watchlist_count,
        hot,
        warm,
        unread,
        ai: aiStatus,
      }),
      connection: connectionLabel(input.actual, market),
      feedSource: replay ? "Replay" : market.feed_status,
      aiStatus,
      unreadLine: `未读提醒：${unread}`,
      lastUpdate: lastUpdate(market),
      replayMode: replay,
      replayStatus: replay ? "已播放完成" : undefined,
      feed: market.feed_status,
      symbolCount: market.watchlist_count,
      hotCount: hot,
      warmCount: warm,
      symbols: sortSymbols(market.symbols).map((symbol) =>
        mapSymbol(symbol, market.feed_status, names, mode),
      ),
    },
    unread,
  );
}

const DASH_UPDATE = "--";
