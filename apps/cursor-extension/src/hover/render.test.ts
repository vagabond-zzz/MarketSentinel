import { describe, expect, it } from "vitest";

import type { WireMarketState, WireSignal, WireSymbolState } from "../protocol/types";
import { mapHover } from "./model";
import { renderHoverMarkdown } from "./render";

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
    scheduler_level: "HOT",
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
    active_signals: [],
    ...overrides,
  };
}

function market(overrides: Partial<WireMarketState> = {}): WireMarketState {
  return {
    watchlist_count: 2,
    feed_status: "LIVE",
    symbols: [
      symbol({ active_signals: [signal()] }),
      symbol({
        symbol: "600519.SH",
        scheduler_level: "COLD",
        price: 1400,
        change_1m: null,
        change_5m: null,
        volume_ratio_5m: null,
        rsi14: null,
      }),
    ],
    ...overrides,
  };
}

describe("renderHoverMarkdown", () => {
  it("renders a scannable LIVE hover with details only for HOT/WARM/signal symbols", () => {
    const text = renderHoverMarkdown(mapHover({ actual: "RUNNING", market: market() }));
    expect(text).toContain("Market Sentinel");
    expect(text).toContain("Feed: LIVE");
    expect(text).toContain("Symbols: 2");
    expect(text).toContain("HOT: 1");
    expect(text).toContain("00700.HK  HOT");
    expect(text).toContain("Price: 602.50");
    expect(text).toContain("1m: +0.80% | 5m: +1.26%");
    expect(text).toContain("Vol 5m: 2.63x");
    expect(text).toContain("[IMPORTANT][UP] price\\_volume");
    expect(text).toContain("量价同步扩张");
    expect(text).toContain("RSI14: 67.4");
    expect(text).toContain("600519.SH  COLD");
    expect(text).not.toMatch(/600519\.SH[\s\S]*Price:/);
  });

  it("keeps STALE/DISCONNECTED feeds visible at the top", () => {
    expect(
      renderHoverMarkdown(
        mapHover({ actual: "RUNNING", market: market({ feed_status: "STALE" }) }),
      ),
    ).toContain("Feed: STALE");
    expect(
      renderHoverMarkdown(
        mapHover({ actual: "RUNNING", market: market({ feed_status: "DISCONNECTED" }) }),
      ),
    ).toContain("Feed: DISCONNECTED");
  });

  it("renders lifecycle copy instead of last market prices", () => {
    const paused = renderHoverMarkdown(
      mapHover({ actual: "PAUSED", market: market() }),
    );
    expect(paused).toContain("Monitoring paused");
    expect(paused).not.toContain("Feed:");
    expect(paused).not.toContain("00700.HK");

    const disconnected = renderHoverMarkdown(mapHover({ actual: "DISCONNECTED" }));
    expect(disconnected).toContain("Core disconnected");
    expect(disconnected).toContain("Click the StatusBar to view Output");
  });

  it("escapes Core text so it cannot become a Markdown link", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({
          symbols: [
            symbol({
              symbol: "bad[sym]",
              active_signals: [
                signal({
                  family: "fam*ily",
                  summary: "see [docs](https://evil.example)",
                }),
              ],
            }),
          ],
        }),
      }),
    );
    expect(text).toContain("bad\\[sym\\]");
    expect(text).toContain("fam\\*ily");
    expect(text).toContain("see \\[docs\\]\\(https://evil.example\\)");
    expect(text).not.toContain("[docs](https://evil.example)");
  });

  it("truncates extra active signals", () => {
    const many = [1, 2, 3, 4, 5].map((index) =>
      signal({ id: `s${index}`, family: `fam${index}`, summary: `sum${index}` }),
    );
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({ symbols: [symbol({ active_signals: many })] }),
      }),
    );
    expect(text).toContain("[IMPORTANT][UP] fam1");
    expect(text).toContain("[IMPORTANT][UP] fam3");
    expect(text).not.toContain("fam4");
    expect(text).toContain("+2 more active signals");
  });

  it("renders the short headline when details are disabled", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        enableHoverDetails: false,
        market: market(),
      }),
    );
    expect(text).toBe("Market Sentinel · LIVE · symbols=2 · HOT=1 · WARM=0");
    expect(text).not.toContain("Price:");
  });
});
