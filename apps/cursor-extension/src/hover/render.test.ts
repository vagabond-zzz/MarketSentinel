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
    change_day: 0.0128,
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
        change_day: 0.0128,
        volume_ratio_5m: null,
        rsi14: null,
      }),
    ],
    ...overrides,
  };
}

describe("renderHoverMarkdown", () => {
  it("renders a useful hover with no signal as a snapshot, not a diagnostic dump", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({
          watchlist_count: 1,
          symbols: [symbol({ scheduler_level: "COLD", active_signals: [] })],
        }),
      }),
    );
    expect(text).toContain("Market Sentinel");
    expect(text).toContain("连接：正常");
    expect(text).toContain("行情源：LIVE");
    expect(text).toContain("AI：关闭");
    expect(text).toContain("未读提醒：0");
    expect(text).toContain("00700.HK");
    expect(text).toContain("602.50 · +1.28% · COLD");
    expect(text).not.toContain("价格：");
    expect(text).not.toContain("当日：");
    expect(text).not.toContain("状态：COLD");
    expect(text).toContain("1m +0.80% | 5m +1.26% | 15m --");
    expect(text).not.toContain("规则信号");
    expect(text).toContain("连接：正常  \n行情源：LIVE");
    expect(text).toContain("涨跌幅  \n1m +0.80%");
  });

  it("separates rule summary from AI enrichment", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({
          intelligence_enabled: true,
          symbols: [
            symbol({
              active_signals: [
                signal({
                  intelligence: {
                    status: "enriched",
                    summary: "Volume led the move.",
                    confidence: 0.82,
                  },
                }),
              ],
            }),
          ],
        }),
      }),
    );
    expect(text).toContain("规则信号");
    expect(text).toContain("规则信号  \n量价同步扩张");
    expect(text).toContain("量价同步扩张");
    expect(text).toContain("AI 增强");
    expect(text).toContain("信号类型  \nprice\\_volume");
    expect(text).toContain("Volume led the move.");
    expect(text).toContain("confidence 0.82");
    expect(text.indexOf("规则信号")).toBeLessThan(text.indexOf("AI 增强"));
    expect(text).toContain("信号类型");
    expect(text).toContain("price\\_volume");
    expect(text).not.toContain("触发规则");
  });

  it("renders queued/running as processing and fallback without raw provider text", () => {
    const running = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({
          intelligence_enabled: true,
          symbols: [
            symbol({
              active_signals: [signal({ intelligence: { status: "running" } })],
            }),
          ],
        }),
      }),
    );
    expect(running).toContain("AI 增强：处理中…");
    const fallback = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({
          intelligence_enabled: true,
          symbols: [
            symbol({
              active_signals: [
                signal({
                  intelligence: {
                    status: "fallback",
                    fallback_reason: "timeout",
                    reason: "DashScope 500 body should not appear",
                  },
                }),
              ],
            }),
          ],
        }),
      }),
    );
    expect(fallback).toContain("AI 增强：本次未完成（timeout）");
    expect(fallback).not.toContain("DashScope");
  });

  it("groups metrics and separates multiple signals", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({
          symbols: [
            symbol({
              active_signals: [
                signal({ id: "a", family: "tape", summary: "first" }),
                signal({ id: "b", family: "vwap", summary: "second" }),
              ],
            }),
          ],
        }),
      }),
    );
    expect(text).toContain("---");
    expect(text).toContain("1m +0.80% | 5m +1.26% | 15m --");
    expect(text).toContain("1m -- | 5m 2.63x");
    expect(text.split("1m +0.80%").length).toBe(2);
  });

  it("renders empty-watchlist copy without Feed DISCONNECTED as the headline", () => {
    const empty = { watchlist_count: 0, feed_status: "DISCONNECTED" as const, symbols: [] };
    const text = renderHoverMarkdown(mapHover({ actual: "RUNNING", market: empty }));
    expect(text).toContain("Market Sentinel");
    expect(text).toContain("No symbols configured");
    expect(text).toContain("Configure marketSentinel.watchlist to start monitoring");
    expect(text).not.toContain("行情源：DISCONNECTED");
  });

  it("keeps STALE/DISCONNECTED feeds visible at the top", () => {
    expect(
      renderHoverMarkdown(
        mapHover({ actual: "RUNNING", market: market({ feed_status: "STALE" }) }),
      ),
    ).toContain("行情源：STALE");
    expect(
      renderHoverMarkdown(
        mapHover({ actual: "RUNNING", market: market({ feed_status: "DISCONNECTED" }) }),
      ),
    ).toContain("行情源：DISCONNECTED");
  });

  it("renders Replay complete without treating it as a live failure", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({ replay_complete: true, last_market_timestamp: 1 }),
      }),
    );
    expect(text).toContain("模式：Replay");
    expect(text).toContain("状态：已播放完成");
    expect(text).toContain("602.50");
  });

  it("labels last_market_timestamp as UTC+8 market time, not host wall-clock update", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        market: market({ last_market_timestamp: 1_704_067_200 + 6 * 3600 + 30 * 60 }),
      }),
    );
    expect(text).toContain("最后行情：14:30:00（UTC+8）");
    expect(text).not.toContain("最后更新");
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
    expect(text).toContain("fam1");
    expect(text).toContain("fam3");
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
    expect(text).toBe("Market Sentinel · LIVE · symbols=2 · HOT=1 · WARM=0 · AI=关闭");
    expect(text).not.toContain("价格：");
  });

  it("shows unread at the top when count is positive", () => {
    const text = renderHoverMarkdown(
      mapHover({
        actual: "RUNNING",
        unreadAlertCount: 2,
        market: market(),
      }),
    );
    expect(text).toContain("未读提醒：2");
    expect(text.indexOf("未读提醒：2")).toBeLessThan(text.indexOf("00700.HK"));
  });
});
