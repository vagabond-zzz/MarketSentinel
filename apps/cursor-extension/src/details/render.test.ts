import { describe, expect, it } from "vitest";

import type { HoverModel } from "../hover/model";
import { renderDetailsBody, renderDetailsDocument } from "./render";

function model(): HoverModel {
  return {
    title: "Market Sentinel",
    enableDetails: true,
    headline: "Market Sentinel · NORMAL",
    connection: "正常",
    feedSource: "NORMAL",
    aiStatus: "已增强",
    unreadLine: "未读提醒：1",
    lastUpdate: "14:30:00",
    unreadAlertCount: 1,
    feed: "NORMAL",
    symbolCount: 2,
    hotCount: 1,
    warmCount: 0,
    symbols: [
      {
        symbol: "600519.SH",
        displayName: "贵州茅台 <script>alert(1)</script>",
        level: "HOT",
        price: "1500.00",
        changeDay: "+1.20%",
        change1m: "+0.80%",
        change5m: "+1.10%",
        change15m: "+1.50%",
        volumeRatio1m: "2.00x",
        volumeRatio5m: "1.50x",
        ema5: "1495.00",
        ema20: "1488.00",
        rsi14: "64.0",
        vwap: "1492.00",
        vwapBias: "当前位于 VWAP 上方",
        sessionHighObs: "1501.00",
        sessionLowObs: "1478.00",
        sessionHighRef: "1490.00",
        sessionLowRef: "1470.00",
        signals: [
          {
            priority: "IMPORTANT",
            direction: "up",
            family: "price_volume",
            body: "规则 <b>不可注入</b>",
            ruleLabel: "规则信号",
            aiLabel: "AI 增强",
            aiBody: "模型 & 摘要",
            aiMeta: "状态：已增强 · confidence 0.82",
          },
        ],
        moreSignals: 0,
      },
      {
        symbol: "000001.SZ",
        displayName: "平安银行 (000001.SZ)",
        level: "COLD",
        price: "11.20",
        changeDay: "-0.88%",
        change1m: "+0.00%",
        change5m: "-0.10%",
        change15m: "-0.20%",
        volumeRatio1m: "0.90x",
        volumeRatio5m: "0.85x",
        ema5: "11.22",
        ema20: "11.25",
        rsi14: "48.0",
        vwap: "11.23",
        sessionHighObs: "11.35",
        sessionLowObs: "11.10",
        sessionHighRef: "11.32",
        sessionLowRef: "11.08",
        signals: [],
        moreSignals: 0,
      },
    ],
  };
}

describe("details renderer", () => {
  it("renders multi-symbol cards, signal sections, and escapes user/model content", () => {
    const html = renderDetailsBody(model());
    expect(html).toContain("贵州茅台 &lt;script&gt;alert(1)&lt;/script&gt;");
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("平安银行 (000001.SZ)");
    expect(html).toContain("规则信号");
    expect(html).toContain("AI 增强");
    expect(html).toContain("模型 &amp; 摘要");
    expect(html).toContain("涨跌幅");
    expect(html).toContain("技术指标");
  });

  it("renders a CSP-protected document with message-driven live refresh", () => {
    const html = renderDetailsDocument("vscode-webview://test", "nonce123", model());
    expect(html).toContain("default-src 'none'");
    expect(html).toContain("script-src 'nonce-nonce123'");
    expect(html).toContain('script nonce="nonce123"');
    expect(html).toContain("window.addEventListener('message'");
    expect(html).toContain("requestAnimationFrame(() => window.scrollTo(scrollX, scrollY))");
  });
});
