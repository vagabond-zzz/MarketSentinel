import { describe, expect, it } from "vitest";
import * as vscode from "vscode";

import { mapHover } from "../hover/model";
import { MarkdownString, vscodeState } from "../../vitest/vscode-mock";
import { HOST_COMMANDS } from "../host/types";
import type { WireMarketState, WireSymbolState } from "../protocol/types";
import { applyStatusBar } from "./adapter";
import { mapStatusBar } from "./map";

function symbol(overrides: Partial<WireSymbolState> = {}): WireSymbolState {
  return {
    symbol: "00700.HK",
    price: 602.5,
    scheduler_level: "COLD",
    feed_status: "LIVE",
    change_1m: 0.008,
    change_5m: 0.0126,
    change_15m: null,
    volume_ratio_1m: null,
    volume_ratio_5m: 2.63,
    ema5: null,
    ema20: null,
    rsi14: 67.4,
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

function apply(kindInput: Parameters<typeof mapStatusBar>[0], hoverActual = kindInput.actual) {
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  const status = mapStatusBar(kindInput);
  const hover = mapHover({
    actual: hoverActual,
    market: kindInput.market,
    unreadAlertCount: kindInput.unreadAlertCount,
  });
  applyStatusBar(item, status, hover);
  return { item, status, hover };
}

describe("StatusBarItem adapter", () => {
  it("never applies error or warning StatusBar backgrounds", () => {
    apply({ ...running, actual: "DISCONNECTED" });
    expect(vscodeState.statusBar.backgroundColor).toBeUndefined();
    apply({
      ...running,
      market: market({ feed_status: "STALE", symbols: [symbol({ feed_status: "STALE" })] }),
    });
    expect(vscodeState.statusBar.backgroundColor).toBeUndefined();
    apply({
      ...running,
      market: market({ symbols: [symbol({ scheduler_level: "HOT" })] }),
      lastAlertAt: 1_000,
      unreadAlertCount: 2,
    });
    expect(vscodeState.statusBar.backgroundColor).toBeUndefined();
    expect(vscodeState.statusBar.command).toBe(HOST_COMMANDS.showOutput);
    expect(vscodeState.statusBar.shown).toBe(true);
  });

  it("applies quote text and Codicon status without MS KIND as the main content", () => {
    expect(apply({ ...running, actual: "DISCONNECTED" }).status.text).toContain("$(error)");
    expect(apply({ ...running, actual: "STARTING" }).status.kind).toBe("STARTING");
    const idle = apply({
      ...running,
      market: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [] },
    });
    expect(idle.status.kind).toBe("IDLE");
    expect(vscodeState.statusBar.text).toContain("无标的");
    expect(apply({ ...running, market: market() }).status.text).toContain("602.50");
    expect(apply({ ...running, market: market() }).status.text).not.toContain("MS NORMAL");
  });

  it("shows unread badge for an alert edge and keeps Markdown untrusted", () => {
    const { status } = apply({
      ...running,
      market: market({ symbols: [symbol({ scheduler_level: "HOT" })] }),
      lastAlertAt: 1_000,
      unreadAlertCount: 2,
    });
    expect(status.kind).toBe("ALERT");
    expect(vscodeState.statusBar.text).toContain("$(bell)");
    expect(vscodeState.statusBar.text).toContain("· 2");
    expect(vscodeState.statusBar.tooltip).toBeInstanceOf(MarkdownString);
    expect((vscodeState.statusBar.tooltip as MarkdownString).isTrusted).toBe(false);
  });

  it("renders active_signals in Hover without turning them into unread", () => {
    const snapshot = market({
      symbols: [
        symbol({
          scheduler_level: "HOT",
          active_signals: [
            {
              id: "live",
              family: "price_volume",
              direction: "up",
              priority: "critical",
              title: "t",
              summary: "量价同步扩张",
            },
          ],
        }),
      ],
    });
    const { status, hover } = apply({ ...running, market: snapshot, unreadAlertCount: 0 });
    expect(status.kind).toBe("HOT");
    expect(hover.unreadAlertCount).toBe(0);
    const tooltip = vscodeState.statusBar.tooltip as MarkdownString;
    expect(tooltip.value).toContain("量价同步扩张");
    expect(tooltip.value).toContain("规则信号");
    expect(tooltip.value).not.toContain("未读提醒：1");
  });
});
