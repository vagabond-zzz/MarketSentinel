import { describe, expect, it } from "vitest";

import type { WireMarketState, WireSymbolState } from "../protocol/types";
import { mapStatusBar } from "./map";

function symbol(overrides: Partial<WireSymbolState> = {}): WireSymbolState {
  return {
    symbol: "00700.HK",
    price: 1,
    scheduler_level: "COLD",
    feed_status: "LIVE",
    change_1m: null,
    change_5m: null,
    change_15m: null,
    volume_ratio_1m: null,
    volume_ratio_5m: null,
    ema5: null,
    ema20: null,
    rsi14: null,
    vwap: null,
    change_day: 0.0128,
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

const running = { actual: "RUNNING" as const, desired: "RUNNING" as const, now: 1_000 };

describe("mapStatusBar", () => {
  it("maps host disconnect and stopped to DISCONNECTED without error background tone", () => {
    expect(mapStatusBar({ ...running, actual: "DISCONNECTED" }).kind).toBe("DISCONNECTED");
    expect(mapStatusBar({ ...running, actual: "STOPPED" }).tone).toBe("default");
    expect(mapStatusBar({ ...running, actual: "STOPPED" }).text).toContain("$(error)");
    expect(mapStatusBar({ ...running, actual: "STARTING" }).kind).toBe("STARTING");
    expect(mapStatusBar({ ...running, actual: "STARTING" }).text).toContain("$(sync~spin)");
  });

  it("maps PAUSED even if the last market snapshot was HOT, keeping quotes", () => {
    const view = mapStatusBar({
      ...running,
      actual: "PAUSED",
      desired: "PAUSED",
      market: market({ symbols: [symbol({ scheduler_level: "HOT", price: 1412.3 })] }),
    });
    expect(view.kind).toBe("PAUSED");
    expect(view.text).toContain("$(debug-pause)");
    expect(view.text).toContain("1412.30");
    expect(view.text).not.toContain("MS PAUSED");
  });

  it("maps STALE/DISCONNECTED feed above HOT and ALERT but keeps quotes", () => {
    const staleHot = mapStatusBar({
      ...running,
      market: market({
        feed_status: "STALE",
        symbols: [symbol({ scheduler_level: "HOT", feed_status: "STALE", price: 1412.3 })],
      }),
      lastAlertAt: 1_000,
    });
    expect(staleHot.kind).toBe("STALE");
    expect(staleHot.tone).toBe("default");
    expect(staleHot.text).toContain("$(warning)");
    expect(staleHot.text).toContain("1412.30");
    expect(
      mapStatusBar({
        ...running,
        market: market({ feed_status: "DISCONNECTED" }),
      }).kind,
    ).toBe("STALE");
  });

  it("uses a clock icon for DELAYED feed instead of treating it as STALE", () => {
    const view = mapStatusBar({
      ...running,
      market: market({
        feed_status: "DELAYED",
        symbols: [symbol({ scheduler_level: "HOT", feed_status: "DELAYED" })],
      }),
    });
    expect(view.kind).toBe("DELAYED");
    expect(view.text).toContain("$(clock)");
    expect(view.tooltip).toContain("feed=DELAYED");
  });

  it("uses alert messages, never active_signals, for ALERT", () => {
    const withLiveSignals = mapStatusBar({
      ...running,
      market: market({
        symbols: [
          symbol({
            active_signals: [
              {
                id: "live",
                family: "tape",
                direction: "up",
                priority: "important",
                title: "t",
                summary: "s",
              },
            ],
          }),
        ],
      }),
    });
    expect(withLiveSignals.kind).toBe("NORMAL");

    const fromAlert = mapStatusBar({
      ...running,
      market: market(),
      lastAlertAt: 1_000,
      now: 2_000,
      alertHoldMs: 15_000,
    });
    expect(fromAlert.kind).toBe("ALERT");
    expect(fromAlert.text).toContain("$(bell)");
  });

  it("lets ALERT expire after the hold window", () => {
    expect(
      mapStatusBar({
        ...running,
        market: market(),
        lastAlertAt: 1_000,
        now: 20_000,
        alertHoldMs: 15_000,
      }).kind,
    ).toBe("NORMAL");
  });

  it("treats elapsed === alertHoldMs as expired so the hold timer can refresh", () => {
    const held = {
      ...running,
      market: market(),
      lastAlertAt: 1_000,
      alertHoldMs: 15_000,
    };
    expect(mapStatusBar({ ...held, now: 1_000 + 14_999 }).kind).toBe("ALERT");
    expect(mapStatusBar({ ...held, now: 1_000 + 15_000 }).kind).toBe("NORMAL");
  });

  it("maps RUNNING without MarketState to STARTING, not NORMAL", () => {
    const view = mapStatusBar({ ...running, market: undefined });
    expect(view.kind).toBe("STARTING");
    expect(view.text).toContain("启动中");
  });

  it("maps an empty watchlist to IDLE instead of STALE", () => {
    const view = mapStatusBar({
      ...running,
      market: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [] },
    });
    expect(view.kind).toBe("IDLE");
    expect(view.text).toContain("无标的");
    expect(view.tone).toBe("default");
  });

  it("keeps unread on IDLE without changing kind", () => {
    const view = mapStatusBar({
      ...running,
      market: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [] },
      unreadAlertCount: 2,
    });
    expect(view.kind).toBe("IDLE");
    expect(view.text).toContain("· 2");
    expect(view.tone).toBe("default");
  });

  it("maps Replay complete to a distinct ended state", () => {
    const view = mapStatusBar({
      ...running,
      market: market({ replay_complete: true }),
    });
    expect(view.kind).toBe("REPLAY_COMPLETE");
    expect(view.text).toBe("$(check) Replay 已结束");
  });

  it("maps a configured watchlist with DISCONNECTED feed to STALE while keeping quotes", () => {
    const view = mapStatusBar({
      ...running,
      market: market({
        feed_status: "DISCONNECTED",
        symbols: [symbol({ feed_status: "DISCONNECTED", price: 12.34, change_day: -0.0055 })],
      }),
    });
    expect(view.kind).toBe("STALE");
    expect(view.text).toContain("$(error)");
    expect(view.text).toContain("12.34");
    expect(view.text).toContain("-0.55%");
  });

  it("does not treat watchlist_count=0 with leftover symbols as IDLE", () => {
    expect(
      mapStatusBar({
        ...running,
        market: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [symbol()] },
      }).kind,
    ).toBe("STALE");
  });

  it("maps HOT over WARM over NORMAL for kind while showing quotes", () => {
    expect(
      mapStatusBar({
        ...running,
        market: market({
          symbols: [
            symbol({ scheduler_level: "WARM" }),
            symbol({ symbol: "x", scheduler_level: "HOT" }),
          ],
        }),
      }).kind,
    ).toBe("HOT");
    expect(
      mapStatusBar({
        ...running,
        market: market({ symbols: [symbol({ scheduler_level: "WARM" })] }),
      }).kind,
    ).toBe("WARM");
    const normal = mapStatusBar({ ...running, market: market() });
    expect(normal.kind).toBe("NORMAL");
    expect(normal.text).toContain("$(circle-outline)");
    expect(normal.text).toContain("00700.HK 1.00 +1.28%");
    expect(normal.text).not.toContain("MS NORMAL");
  });

  it("caps StatusBar quotes and shows +N overflow", () => {
    const view = mapStatusBar({
      ...running,
      maxSymbols: 2,
      market: market({
        watchlist_count: 4,
        symbols: [
          symbol({ symbol: "A", price: 1, change_day: 0.01 }),
          symbol({ symbol: "B", price: 2, change_day: -0.01 }),
          symbol({ symbol: "C", price: 3, change_day: 0 }),
          symbol({ symbol: "D", price: 4, change_day: 0 }),
        ],
      }),
    });
    expect(view.text).toContain("A 1.00 +1.00% | B 2.00 -1.00% | +2");
    expect(view.text).not.toContain("C 3.00");
  });

  it("shows -- when price is missing", () => {
    const view = mapStatusBar({
      ...running,
      market: market({ symbols: [symbol({ price: null, change_day: null })] }),
    });
    expect(view.text).toContain("00700.HK --");
  });

  it("uses display names on the StatusBar without changing identity", () => {
    const view = mapStatusBar({
      ...running,
      symbolNames: { "600519.SH": "贵州茅台" },
      market: market({
        symbols: [symbol({ symbol: "600519.SH", price: 1412.3, change_day: 0.0128 })],
      }),
    });
    expect(view.text).toContain("贵州茅台 1412.30 +1.28%");
    expect(view.text).not.toContain("600519.SH");
  });

  it("lets ALERT win over HOT when feed is live", () => {
    expect(
      mapStatusBar({
        ...running,
        market: market({ symbols: [symbol({ scheduler_level: "HOT" })] }),
        lastAlertAt: 1_000,
      }).kind,
    ).toBe("ALERT");
  });

  it("appends an unread badge without changing kind priority", () => {
    expect(mapStatusBar({ ...running, market: market(), unreadAlertCount: 2 }).text).toContain(
      "· 2",
    );
    const stale = mapStatusBar({
      ...running,
      market: market({ feed_status: "STALE" }),
      lastAlertAt: 1_000,
      unreadAlertCount: 3,
    });
    expect(stale.kind).toBe("STALE");
    expect(stale.text).toContain("· 3");
    expect(mapStatusBar({ ...running, market: market(), unreadAlertCount: 100 }).text).toContain(
      "· 99+",
    );
  });
});
