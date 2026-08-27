import { describe, expect, it } from "vitest";

import type { WireMarketState, WireSignal, WireSymbolState } from "../protocol/types";
import { mapHover } from "./model";

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
  it("maps STARTING, PAUSED, and DISCONNECTED without dumping market as live", () => {
    const snapshot = market({ symbols: [symbol({ scheduler_level: "HOT" })] });
    expect(mapHover({ actual: "STARTING", market: snapshot }).lifecycleMessage).toBe("Core starting");
    expect(mapHover({ actual: "STARTING", market: snapshot }).symbols).toEqual([]);
    expect(mapHover({ actual: "PAUSED", market: snapshot }).lifecycleMessage).toBe("Monitoring paused");
    expect(mapHover({ actual: "PAUSED", market: snapshot }).symbols).toEqual([]);
    const disconnected = mapHover({ actual: "DISCONNECTED", market: snapshot });
    expect(disconnected.lifecycleMessage).toBe("Core disconnected");
    expect(disconnected.outputHint).toMatch(/Output/);
    expect(disconnected.symbols).toEqual([]);
    expect(mapHover({ actual: "STOPPING" }).lifecycleMessage).toBe("Core stopping");
    expect(mapHover({ actual: "STOPPED" }).lifecycleMessage).toBe("Monitoring stopped");
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
    expect(view.symbolCount).toBeUndefined();
    expect(view.hotCount).toBeUndefined();
    expect(view.warmCount).toBeUndefined();
    expect(view.symbols).toEqual([]);
    expect(view.headline).toBe("Market Sentinel · No symbols configured");

    const compact = mapHover({ actual: "RUNNING", enableHoverDetails: false, market: empty });
    expect(compact.headline).toBe("Market Sentinel · No symbols configured");
    expect(compact.enableDetails).toBe(false);
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

  it("shows details for HOT/WARM or active signals, and a summary line for quiet COLD", () => {
    const view = mapHover({
      actual: "RUNNING",
      market: market({
        watchlist_count: 3,
        symbols: [
          symbol({ symbol: "COLD_QUIET", scheduler_level: "COLD" }),
          symbol({
            symbol: "COLD_SIGNAL",
            scheduler_level: "COLD",
            active_signals: [signal()],
          }),
          symbol({ symbol: "WARM_1", scheduler_level: "WARM" }),
        ],
      }),
    });
    expect(view.symbols.find((item) => item.symbol === "COLD_QUIET")?.showDetails).toBe(false);
    expect(view.symbols.find((item) => item.symbol === "COLD_SIGNAL")?.showDetails).toBe(true);
    expect(view.symbols.find((item) => item.symbol === "WARM_1")?.showDetails).toBe(true);
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

  it("shows active signals with truncation and does not invent ALERT fields", () => {
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
    expect(view.symbols[0]?.signals[0]).toEqual({
      priority: "IMPORTANT",
      direction: "UP",
      family: "fam1",
      body: "sum1",
    });
    expect(view.headline).not.toMatch(/ALERT|NEW/i);
  });

  it("formats primary and secondary fields from the wire DTO", () => {
    const view = mapHover({ actual: "RUNNING", market: market() });
    const row = view.symbols[0];
    expect(row?.price).toBe("602.50");
    expect(row?.change1m).toBe("+0.80%");
    expect(row?.change5m).toBe("+1.26%");
    expect(row?.volumeRatio5m).toBe("2.63x");
    expect(row?.detailsLine).toContain("RSI14: 67.4");
    expect(row?.detailsLine).toContain("15m: +1.00%");
    expect(row?.detailsLine).toContain("Vol 1m: 1.20x");
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
    expect(view.headline).toBe("Market Sentinel · LIVE · symbols=3 · HOT=1 · WARM=1");
  });

  it("surfaces unread separately from active_signals", () => {
    const withSignals = mapHover({
      actual: "RUNNING",
      unreadAlertCount: 0,
      market: market({
        symbols: [symbol({ scheduler_level: "HOT", active_signals: [signal()] })],
      }),
    });
    expect(withSignals.unreadAlertCount).toBe(0);
    expect(withSignals.headline).not.toMatch(/unread=/);

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
    expect(withUnread.headline).toBe(
      "Market Sentinel · LIVE · symbols=3 · HOT=1 · WARM=1 · unread=2",
    );
  });
});
