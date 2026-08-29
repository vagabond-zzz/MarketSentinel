import { formatDirection } from "../hover/format";
import type { HoverModel, HoverSignalView, HoverSymbolView } from "../hover/model";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fixedClass(value: string, allowed: readonly string[], fallback: string): string {
  const normalized = value.toLowerCase();
  return allowed.includes(normalized) ? normalized : fallback;
}

function renderSignal(signal: HoverSignalView): string {
  const priority = fixedClass(signal.priority, ["notice", "important", "critical"], "notice");
  const ai =
    signal.aiLabel.length === 0
      ? ""
      : `<div class="signal-block ai-block">
          <div class="section-label">${escapeHtml(signal.aiLabel)}</div>
          ${signal.aiBody !== undefined ? `<div class="body-copy">${escapeHtml(signal.aiBody)}</div>` : ""}
          ${signal.aiMeta !== undefined ? `<div class="muted">${escapeHtml(signal.aiMeta)}</div>` : ""}
        </div>`;
  return `<article class="signal-card ${priority}">
      <div class="signal-title">
        <span class="priority">${escapeHtml(signal.priority)}</span>
        <span class="direction">${escapeHtml(formatDirection(signal.direction))}</span>
        <span>${escapeHtml(signal.family)}</span>
      </div>
      <div class="signal-block">
        <div class="section-label">${escapeHtml(signal.ruleLabel)}</div>
        <div class="body-copy">${escapeHtml(signal.body)}</div>
      </div>
      ${ai}
      <div class="signal-type"><span class="muted">信号类型</span><span>${escapeHtml(signal.family)}</span></div>
    </article>`;
}

function renderMetricGroup(title: string, rows: string[]): string {
  return `<section class="metric-group">
      <div class="section-label">${escapeHtml(title)}</div>
      ${rows.map((row) => `<div class="metric-row">${escapeHtml(row)}</div>`).join("")}
    </section>`;
}

function renderSymbol(symbol: HoverSymbolView): string {
  const level = fixedClass(symbol.level, ["hot", "warm", "cold"], "cold");
  const feed = symbol.feedStatus !== undefined ? `<span class="chip">${escapeHtml(symbol.feedStatus)}</span>` : "";
  const code = symbol.displayName.includes(symbol.symbol) ? "" : `<div class="symbol-code">${escapeHtml(symbol.symbol)}</div>`;
  const signals = symbol.signals.map(renderSignal).join("");
  const moreSignals =
    symbol.moreSignals > 0
      ? `<div class="muted more-signals">还有 ${symbol.moreSignals} 个 active signals 未展开</div>`
      : "";
  const vwap = symbol.vwapBias !== undefined ? `VWAP ${symbol.vwap} · ${symbol.vwapBias}` : `VWAP ${symbol.vwap}`;
  return `<section class="symbol-card">
      <header class="symbol-header">
        <div>
          <div class="symbol-name">${escapeHtml(symbol.displayName)}</div>
          ${code}
        </div>
        <div class="quote-block">
          <div class="price">${escapeHtml(symbol.price)}</div>
          <div class="day-change">${escapeHtml(symbol.changeDay)}</div>
        </div>
      </header>
      <div class="chips"><span class="chip level ${level}">${escapeHtml(symbol.level)}</span>${feed}</div>
      ${signals.length > 0 ? `<div class="signals">${signals}${moreSignals}</div>` : ""}
      <div class="metrics-grid">
        ${renderMetricGroup("涨跌幅", [`1m ${symbol.change1m}  ·  5m ${symbol.change5m}  ·  15m ${symbol.change15m}`])}
        ${renderMetricGroup("成交", [`1m ${symbol.volumeRatio1m}  ·  5m ${symbol.volumeRatio5m}`])}
        ${renderMetricGroup("技术指标", [
          `EMA5 ${symbol.ema5}  ·  EMA20 ${symbol.ema20}  ·  RSI14 ${symbol.rsi14}`,
          vwap,
        ])}
        ${renderMetricGroup("日内区间", [
          `高 ${symbol.sessionHighObs} / 前高 ${symbol.sessionHighRef}`,
          `低 ${symbol.sessionLowObs} / 前低 ${symbol.sessionLowRef}`,
        ])}
      </div>
    </section>`;
}

function renderTopMeta(model: HoverModel): string {
  const items: string[] = [];
  if (model.connection !== undefined) items.push(`连接：${model.connection}`);
  if (model.feedSource !== undefined) items.push(`行情源：${model.feedSource}`);
  if (model.aiStatus !== undefined) items.push(`AI：${model.aiStatus}`);
  if (model.unreadLine !== undefined) items.push(model.unreadLine);
  if (model.lastUpdate !== undefined) {
    items.push(model.lastUpdate === "--" ? "最后行情：--" : `最后行情：${model.lastUpdate}（UTC+8）`);
  }
  if (model.replayMode === true) {
    items.push(`Replay：${model.replayStatus ?? "运行中"}`);
  }
  return items.map((item) => `<span class="meta-chip">${escapeHtml(item)}</span>`).join("");
}

export function renderDetailsBody(model: HoverModel): string {
  const lifecycle =
    model.symbols.length === 0 && model.lifecycleMessage !== undefined
      ? `<section class="empty-state">
          <div class="empty-title">${escapeHtml(model.lifecycleMessage)}</div>
          ${model.outputHint !== undefined ? `<div class="muted">${escapeHtml(model.outputHint)}</div>` : ""}
        </section>`
      : "";
  return `<main class="page">
      <header class="page-header">
        <div>
          <div class="eyebrow">MARKET SENTINEL</div>
          <h1>行情详情</h1>
        </div>
        <div class="meta-row">${renderTopMeta(model)}</div>
      </header>
      ${lifecycle}
      <div class="symbols-grid">${model.symbols.map(renderSymbol).join("")}</div>
    </main>`;
}

export function renderDetailsDocument(cspSource: string, nonce: string, model: HoverModel): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';" />
  <title>Market Sentinel · 行情详情</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    html { scroll-behavior: auto; }
    body {
      margin: 0;
      padding: 0;
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      line-height: 1.55;
    }
    .page { max-width: 1500px; margin: 0 auto; padding: 24px 28px 56px; }
    .page-header {
      position: sticky;
      top: 0;
      z-index: 3;
      display: flex;
      gap: 18px;
      align-items: flex-end;
      justify-content: space-between;
      padding: 8px 0 16px;
      margin-bottom: 18px;
      background: color-mix(in srgb, var(--vscode-editor-background) 94%, transparent);
      border-bottom: 1px solid var(--vscode-panel-border);
      backdrop-filter: blur(8px);
    }
    .eyebrow { color: var(--vscode-descriptionForeground); font-size: 11px; letter-spacing: .14em; }
    h1 { margin: 2px 0 0; font-size: 24px; font-weight: 650; }
    .meta-row { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
    .meta-chip, .chip {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border: 1px solid var(--vscode-panel-border);
      border-radius: 999px;
      color: var(--vscode-descriptionForeground);
      background: var(--vscode-editorWidget-background);
      white-space: nowrap;
    }
    .symbols-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(390px, 100%), 1fr));
      gap: 16px;
      align-items: start;
    }
    .symbol-card {
      min-width: 0;
      padding: 18px;
      border: 1px solid var(--vscode-panel-border);
      border-radius: 10px;
      background: var(--vscode-sideBar-background);
      box-shadow: 0 1px 2px color-mix(in srgb, var(--vscode-widget-shadow) 35%, transparent);
    }
    .symbol-header { display: flex; gap: 16px; justify-content: space-between; align-items: flex-start; }
    .symbol-name { font-size: 18px; font-weight: 650; overflow-wrap: anywhere; }
    .symbol-code { margin-top: 2px; color: var(--vscode-descriptionForeground); font-size: 12px; }
    .quote-block { text-align: right; white-space: nowrap; }
    .price { font-family: var(--vscode-editor-font-family); font-size: 21px; font-weight: 650; }
    .day-change { color: var(--vscode-descriptionForeground); font-family: var(--vscode-editor-font-family); }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .level.hot { border-color: var(--vscode-testing-iconFailed); color: var(--vscode-testing-iconFailed); }
    .level.warm { border-color: var(--vscode-editorWarning-foreground); color: var(--vscode-editorWarning-foreground); }
    .signals { display: grid; gap: 10px; margin-top: 16px; }
    .signal-card {
      overflow: hidden;
      border: 1px solid var(--vscode-panel-border);
      border-left-width: 3px;
      border-radius: 8px;
      background: var(--vscode-editor-background);
    }
    .signal-card.critical { border-left-color: var(--vscode-testing-iconFailed); }
    .signal-card.important { border-left-color: var(--vscode-editorWarning-foreground); }
    .signal-card.notice { border-left-color: var(--vscode-textLink-foreground); }
    .signal-title {
      display: flex;
      gap: 8px;
      align-items: center;
      padding: 9px 11px;
      border-bottom: 1px solid var(--vscode-panel-border);
      font-family: var(--vscode-editor-font-family);
      font-weight: 600;
    }
    .priority { font-size: 11px; color: var(--vscode-descriptionForeground); }
    .direction { font-size: 16px; }
    .signal-block { padding: 10px 11px; }
    .signal-block + .signal-block { border-top: 1px dashed var(--vscode-panel-border); }
    .ai-block { background: color-mix(in srgb, var(--vscode-textLink-foreground) 6%, transparent); }
    .section-label { margin-bottom: 4px; font-size: 12px; font-weight: 650; color: var(--vscode-descriptionForeground); }
    .body-copy { white-space: pre-wrap; overflow-wrap: anywhere; }
    .signal-type { display: flex; gap: 8px; padding: 8px 11px; border-top: 1px solid var(--vscode-panel-border); font-size: 12px; }
    .metrics-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }
    .metric-group { min-width: 0; padding: 10px 11px; border: 1px solid var(--vscode-panel-border); border-radius: 8px; background: var(--vscode-editor-background); }
    .metric-row { font-family: var(--vscode-editor-font-family); overflow-wrap: anywhere; }
    .metric-row + .metric-row { margin-top: 3px; }
    .muted { color: var(--vscode-descriptionForeground); }
    .more-signals { padding: 3px 1px; font-size: 12px; }
    .empty-state { padding: 28px; border: 1px dashed var(--vscode-panel-border); border-radius: 10px; text-align: center; }
    .empty-title { margin-bottom: 4px; font-size: 16px; font-weight: 600; }
    @media (max-width: 720px) {
      .page { padding: 16px 14px 40px; }
      .page-header { position: static; display: block; }
      .meta-row { justify-content: flex-start; margin-top: 10px; }
      .metrics-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div id="content">${renderDetailsBody(model)}</div>
  <script nonce="${nonce}">
    const content = document.getElementById('content');
    window.addEventListener('message', (event) => {
      const message = event.data;
      if (!message || message.type !== 'render' || typeof message.html !== 'string') return;
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;
      content.innerHTML = message.html;
      requestAnimationFrame(() => window.scrollTo(scrollX, scrollY));
    });
  </script>
</body>
</html>`;
}
