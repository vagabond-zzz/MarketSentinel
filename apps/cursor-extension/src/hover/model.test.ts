import { describe, expect, it } from "vitest";

import type { WireMarketState, WireSignal, WireSymbolState } from "../protocol/types";
import { mapAiStatus, mapHover } from "./model";

function signal(overrides: Partial<WireSignal> = {}): WireSignal {
  return {
    id: "s1",
    family: "price_volume",
    direction: "up",
    priority: "important",
    title: "title",
    summary: "量价同步扩张",
    ...overrides,
  };
}

function symbol(overrides: Partial<WireSymbolState> = {}): WireSymbolState {
  return {
    symbol: "00700.HK",
    price: 602.5,
    scheduler_level: "COLD",
    feed_status: "LIVE",
    change_1m: 0.008,
    change_5m: 0.0126,
    change_15m: 0.01,
    volume_ratio_1m: 1.2,
    volume_ratio_5m: 2.63,
    ema5: 600,
    ema20: 590,
    rsi14: 67.4,
    vwap: 601.1,
    change_day: 0.0126,
    active_signals: [],
    ...overrides,
  };
}

function market(overrides: Partial<WireMarketState> = {}): WireMarketState {
  return {
    watchlist_count: 1,
    feed_status: "LIVE",
    symbols: [symbol()],
    ...overrides,
  };
}

describe("mapHover", () => {
  it("maps STARTING without dumping market as live", () => {
    const snapshot = market({ symbols: [symbol({ scheduler_level: "HOT" })] });
    expect(mapHover({ actual: "STARTING", market: snapshot }).lifecycleMessage).toBe("Core starting");
    expect(mapHover({ actual: "STARTING", market: snapshot }).symbols).toEqual([]);
    expect(mapHover({ actual: "STOPPING" }).lifecycleMessage).toBe("Core stopping");
    expect(mapHover({ actual: "STOPPED" }).lifecycleMessage).toBe("Monitoring stopped");
  });

  it("keeps last quotes when PAUSED or host-disconnected", () => {
    const snapshot = market({ symbols: [symbol({ scheduler_level: "HOT", change_day: 0.0128 })] });
    const paused = mapHover({ actual: "PAUSED", market: snapshot });
    expect(paused.connection).toBe("已暂停");
    expect(paused.symbols).toHaveLength(1);
    expect(paused.symbols[0]?.price).toBe("602.50");
    const disconnected = mapHover({ actual: "DISCONNECTED", market: snapshot });
    expect(disconnected.connection).toBe("异常");
    expect(disconnected.symbols).toHaveLength(1);
    const noMarket = mapHover({ actual: "DISCONNECTED" });
    expect(noMarket.lifecycleMessage).toBe("Core disconnected");
    expect(noMarket.outputHint).toMatch(/Output/);
    expect(noMarket.symbols).toEqual([]);
  });

  it("maps RUNNING without MarketState to a starting hover, not a normal market", () => {
    const view = mapHover({ actual: "RUNNING", market: undefined });
    expect(view.lifecycleMessage).toBe("Core starting");
    expect(view.feed).toBeUndefined();
    expect(view.symbols).toEqual([]);
    expect(view.headline).toBe("Market Sentinel · Core starting");
  });

  it("maps an empty watchlist to configuration copy instead of Feed DISCONNECTED", () => {
    const empty = { watchlist_count: 0, feed_status: "DISCONNECTED" as const, symbols: [] };
    const view = mapHover({ actual: "RUNNING", market: empty });
    expect(view.lifecycleMessage).toBe("No symbols configured");
    expect(view.outputHint).toBe("Configure marketSentinel.watchlist to start monitoring");
    expect(view.feed).toBeUndefined();
    expect(view.symbols).toEqual([]);
    expect(view.headline).toBe("Market Sentinel · No symbols configured");
  });

  it("surfaces aggregate LIVE, DELAYED, STALE, and DISCONNECTED feeds", () => {
    expect(mapHover({ actual: "RUNNING", market: market({ feed_status: "LIVE" }) }).feed).toBe("LIVE");
    expect(mapHover({ actual: "RUNNING", market: market({ feed_status: "DELAYED" }) }).feed).toBe(
      "DELAYED",
    );
    expect(mapHover({ actual: "RUNNING", market: market({ feed_status: "STALE" }) }).feed).toBe("STALE");
    expect(
      mapHover({ actual: "RUNNING", market: market({ feed_status: "DISCONNECTED" }) }).feed,
    ).toBe("DISCONNECTED");
  });

  it("orders HOT before WARM before COLD and keeps wire order within a level", () => {
    const view = mapHover({
      actual: "RUNNING",
      market: market({
        watchlist_count: 4,
        symbols: [
          symbol({ symbol: "COLD_A", scheduler_level: "COLD" }),
          symbol({ symbol: "HOT_B", scheduler_level: "HOT" }),
          symbol({ symbol: "WARM_C", scheduler_level: "WARM" }),
          symbol({ symbol: "HOT_D", scheduler_level: "HOT" }),
        ],
      }),
    });
    expect(view.symbols.map((item) => item.symbol)).toEqual(["HOT_B", "HOT_D", "WARM_C", "COLD_A"]);
    expect(view.hotCount).toBe(2);
    expect(view.warmCount).toBe(1);
  });

  it("always maps a snapshot for quiet COLD symbols so hover is useful without signals", () => {
    const view = mapHover({
      actual: "RUNNING",
      market: market({
        watchlist_count: 1,
        symbols: [symbol({ symbol: "COLD_QUIET", scheduler_level: "COLD" })],
      }),
    });
    expect(view.symbols[0]?.price).toBe("602.50");
    expect(view.symbols[0]?.changeDay).toBe("+1.26%");
    expect(view.symbols[0]?.signals).toEqual([]);
  });

  it("shows per-symbol feed status only when it differs from aggregate", () => {
    const view = mapHover({
      actual: "RUNNING",
      market: market({
        feed_status: "STALE",
        symbols: [
          symbol({ feed_status: "STALE" }),
          symbol({ symbol: "00941.HK", feed_status: "DISCONNECTED", scheduler_level: "COLD" }),
        ],
      }),
    });
    expect(view.symbols[0]?.feedStatus).toBeUndefined();
    expect(view.symbols[1]?.feedStatus).toBe("DISCONNECTED");
  });

  it("shows active signals with truncation and labels rule vs AI", () => {
    const many = [1, 2, 3, 4, 5].map((index) =>
      signal({ id: `s${index}`, family: `fam${index}`, summary: `sum${index}` }),
    );
    const view = mapHover({
      actual: "RUNNING",
      market: market({
        symbols: [symbol({ scheduler_level: "HOT", active_signals: many })],
      }),
    });
    expect(view.symbols[0]?.signals).toHaveLength(3);
    expect(view.symbols[0]?.moreSignals).toBe(2);
    expect(view.symbols[0]?.signals[0]?.ruleLabel).toBe("规则信号");
    expect(view.symbols[0]?.signals[0]?.body).toBe("sum1");
    expect(view.headline).not.toMatch(/ALERT|NEW/i);
  });

  it("formats day change separately from 1m/5m/15m", () => {
    const view = mapHover({ actual: "RUNNING", market: market() });
    const row = view.symbols[0];
    expect(row?.price).toBe("602.50");
    expect(row?.changeDay).toBe("+1.26%");
    expect(row?.change1m).toBe("+0.80%");
    expect(row?.change5m).toBe("+1.26%");
    expect(row?.change15m).toBe("+1.00%");
    expect(row?.volumeRatio5m).toBe("2.63x");
  });

  it("uses display aliases without changing the canonical symbol id", () => {
    const view = mapHover({
      actual: "RUNNING",
      symbolNames: { "600519.SH": "贵州茅台" },
      symbolDisplay: "nameAndCode",
      market: market({
        symbols: [symbol({ symbol: "600519.SH" })],
      }),
    });
    expect(view.symbols[0]?.symbol).toBe("600519.SH");
    expect(view.symbols[0]?.displayName).toBe("贵州茅台 (600519.SH)");
  });

  it("builds a short headline when hover details are disabled", () => {
    const view = mapHover({
      actual: "RUNNING",
      enableHoverDetails: false,
      market: market({
        watchlist_count: 3,
        symbols: [
          symbol({ scheduler_level: "HOT" }),
          symbol({ symbol: "b", scheduler_level: "WARM" }),
          symbol({ symbol: "c", scheduler_level: "COLD" }),
        ],
      }),
    });
    expect(view.enableDetails).toBe(false);
    expect(view.headline).toBe("Market Sentinel · LIVE · symbols=3 · HOT=1 · WARM=1 · AI=关闭");
  });

  it("surfaces unread separately from active_signals", () => {
    const withUnread = mapHover({
      actual: "RUNNING",
      unreadAlertCount: 2,
      enableHoverDetails: false,
      market: market({
        watchlist_count: 3,
        symbols: [
          symbol({ scheduler_level: "HOT" }),
          symbol({ symbol: "b", scheduler_level: "WARM" }),
          symbol({ symbol: "c", scheduler_level: "COLD" }),
        ],
      }),
    });
    expect(withUnread.unreadAlertCount).toBe(2);
    expect(withUnread.headline).toContain("unread=2");
    expect(withUnread.unreadLine).toBe("未读提醒：2");
  });

  it("maps AI status from wire without inventing model calls", () => {
    expect(mapAiStatus(market())).toBe("关闭");
    expect(mapAiStatus(market({ intelligence_enabled: true }))).toBe("已启用");
    expect(
      mapAiStatus(
        market({
          intelligence_enabled: true,
          symbols: [
            symbol({
              active_signals: [signal({ intelligence: { status: "running" } })],
            }),
          ],
        }),
      ),
    ).toBe("处理中");
    expect(
      mapAiStatus(
        market({
          intelligence_enabled: true,
          symbols: [
            symbol({
              active_signals: [signal({ intelligence: { status: "enriched", summary: "note" } })],
            }),
          ],
        }),
      ),
    ).toBe("已增强");
  });
});
