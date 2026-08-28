import type { ActualState } from "../host/types";
import type {
  FeedStatus,
  SchedulerLevel,
  WireMarketState,
  WireSignal,
  WireSymbolState,
} from "../protocol/types";
import { formatPercent, formatPrice, formatRatio, formatRsi } from "./format";

export const MAX_HOVER_SIGNALS = 3;

const LEVEL_ORDER: Record<SchedulerLevel, number> = {
  HOT: 0,
  WARM: 1,
  COLD: 2,
};

export interface HoverSignalView {
  priority: string;
  direction: string;
  family: string;
  body: string;
  enrichment?: string;
}

export interface HoverSymbolView {
  symbol: string;
  level: SchedulerLevel;
  feedStatus?: FeedStatus;
  showDetails: boolean;
  price: string;
  change1m: string;
  change5m: string;
  volumeRatio5m: string;
  detailsLine: string;
  signals: HoverSignalView[];
  moreSignals: number;
}

export interface HoverModel {
  title: string;
  enableDetails: boolean;
  headline: string;
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
  const enrichment =
    signal.intelligence?.status === "enriched" &&
    signal.intelligence.summary !== undefined &&
    signal.intelligence.summary.length > 0
      ? signal.intelligence.summary
      : undefined;
  return {
    priority: signal.priority.toUpperCase(),
    direction: signal.direction.toUpperCase(),
    family: signal.family,
    body: signal.summary.length > 0 ? signal.summary : signal.title,
    enrichment,
  };
}

function detailsLine(symbol: WireSymbolState): string {
  return [
    `EMA5: ${formatPrice(symbol.ema5)}`,
    `EMA20: ${formatPrice(symbol.ema20)}`,
    `RSI14: ${formatRsi(symbol.rsi14)}`,
    `VWAP: ${formatPrice(symbol.vwap)}`,
    `15m: ${formatPercent(symbol.change_15m)}`,
    `Vol 1m: ${formatRatio(symbol.volume_ratio_1m)}`,
  ].join(" · ");
}

function shouldShowDetails(symbol: WireSymbolState): boolean {
  return (
    symbol.scheduler_level === "HOT" ||
    symbol.scheduler_level === "WARM" ||
    symbol.active_signals.length > 0
  );
}

function mapSymbol(symbol: WireSymbolState, aggregateFeed: FeedStatus): HoverSymbolView {
  const shown = symbol.active_signals.slice(0, MAX_HOVER_SIGNALS);
  return {
    symbol: symbol.symbol,
    level: symbol.scheduler_level,
    feedStatus: symbol.feed_status === aggregateFeed ? undefined : symbol.feed_status,
    showDetails: shouldShowDetails(symbol),
    price: formatPrice(symbol.price),
    change1m: formatPercent(symbol.change_1m),
    change5m: formatPercent(symbol.change_5m),
    volumeRatio5m: formatRatio(symbol.volume_ratio_5m),
    detailsLine: detailsLine(symbol),
    signals: shown.map(mapSignal),
    moreSignals: Math.max(0, symbol.active_signals.length - MAX_HOVER_SIGNALS),
  };
}

function lifecycleFor(
  actual: ActualState,
  market: WireMarketState | undefined,
): { message: string; hint?: string } | undefined {
  if (actual === "STARTING") {
    return { message: "Core starting" };
  }
  if (actual === "PAUSED") {
    return { message: "Monitoring paused" };
  }
  if (actual === "DISCONNECTED") {
    return { message: "Core disconnected", hint: "Click the StatusBar to view Output" };
  }
  if (actual === "STOPPING") {
    return { message: "Core stopping" };
  }
  if (actual === "STOPPED") {
    return { message: "Monitoring stopped" };
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
  const lifecycle = lifecycleFor(input.actual, input.market);
  if (lifecycle !== undefined) {
    return withUnread(
      {
        title: "Market Sentinel",
        enableDetails,
        headline: shortHeadline({ lifecycle: lifecycle.message, unread }),
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
        lifecycleMessage: "No symbols configured",
        outputHint: "Configure marketSentinel.watchlist to start monitoring",
        symbols: [],
      },
      unread,
    );
  }

  const { hot, warm } = countLevels(market.symbols);
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
      }),
      feed: market.feed_status,
      symbolCount: market.watchlist_count,
      hotCount: hot,
      warmCount: warm,
      symbols: sortSymbols(market.symbols).map((symbol) => mapSymbol(symbol, market.feed_status)),
    },
    unread,
  );
}
