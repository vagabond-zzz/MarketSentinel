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
  it("maps host disconnect and stopped to DISCONNECTED", () => {
    expect(mapStatusBar({ ...running, actual: "DISCONNECTED" }).kind).toBe("DISCONNECTED");
    expect(mapStatusBar({ ...running, actual: "STOPPED" }).tone).toBe("error");
    expect(mapStatusBar({ ...running, actual: "STARTING" }).kind).toBe("STARTING");
  });

  it("maps PAUSED even if the last market snapshot was HOT", () => {
    const view = mapStatusBar({
      ...running,
      actual: "PAUSED",
      desired: "PAUSED",
      market: market({ symbols: [symbol({ scheduler_level: "HOT" })] }),
    });
    expect(view.kind).toBe("PAUSED");
    expect(view.text).toBe("MS PAUSED");
  });

  it("maps STALE/DISCONNECTED feed above HOT and ALERT", () => {
    const staleHot = mapStatusBar({
      ...running,
      market: market({
        feed_status: "STALE",
        symbols: [symbol({ scheduler_level: "HOT", feed_status: "STALE" })],
      }),
      lastAlertAt: 1_000,
    });
    expect(staleHot.kind).toBe("STALE");
    expect(staleHot.tone).toBe("error");
    expect(
      mapStatusBar({
        ...running,
        market: market({ feed_status: "DISCONNECTED" }),
      }).kind,
    ).toBe("STALE");
  });

  it("does not treat DELAYED feed as STALE", () => {
    const view = mapStatusBar({
      ...running,
      market: market({
        feed_status: "DELAYED",
        symbols: [symbol({ scheduler_level: "HOT", feed_status: "DELAYED" })],
      }),
    });
    expect(view.kind).toBe("HOT");
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
    expect(view.text).toBe("MS STARTING");
  });

  it("maps HOT over WARM over NORMAL", () => {
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
    expect(mapStatusBar({ ...running, market: market() }).kind).toBe("NORMAL");
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
    expect(mapStatusBar({ ...running, market: market(), unreadAlertCount: 2 }).text).toBe(
      "MS NORMAL · 2",
    );
    expect(
      mapStatusBar({
        ...running,
        market: market({ symbols: [symbol({ scheduler_level: "HOT" })] }),
        unreadAlertCount: 2,
      }).text,
    ).toBe("MS HOT · 2");
    const stale = mapStatusBar({
      ...running,
      market: market({ feed_status: "STALE" }),
      lastAlertAt: 1_000,
      unreadAlertCount: 3,
    });
    expect(stale.kind).toBe("STALE");
    expect(stale.text).toBe("MS STALE · 3");
    expect(
      mapStatusBar({
        ...running,
        actual: "PAUSED",
        desired: "PAUSED",
        market: market(),
        unreadAlertCount: 2,
      }).text,
    ).toBe("MS PAUSED · 2");
    expect(mapStatusBar({ ...running, market: market(), unreadAlertCount: 100 }).text).toBe(
      "MS NORMAL · 99+",
    );
  });
});
