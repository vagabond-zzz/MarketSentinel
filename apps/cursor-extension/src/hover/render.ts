import { escapeMarkdown, formatDirection } from "./format";
import type { HoverModel, HoverSignalView, HoverSymbolView } from "./model";

/** CommonMark hard break so Cursor/VS Code tooltips do not collapse single newlines. */
function joinMarkdownLines(lines: string[]): string {
  return lines.join("  \n");
}

function renderSignal(signal: HoverSignalView): string[] {
  const lines = [
    `[${signal.priority}] ${formatDirection(signal.direction)} ${escapeMarkdown(signal.family)}`,
    "",
    signal.ruleLabel,
    escapeMarkdown(signal.body),
  ];
  if (signal.aiLabel.length > 0) {
    lines.push("");
    if (signal.aiBody === "处理中…") {
      lines.push("AI 增强：处理中…");
    } else if (signal.aiBody === "本次未完成") {
      const reason = signal.aiMeta !== undefined ? `（${signal.aiMeta}）` : "";
      lines.push(`AI 增强：本次未完成${reason}`);
    } else {
      lines.push(signal.aiLabel);
      if (signal.aiBody !== undefined && signal.aiBody.length > 0) {
        lines.push(escapeMarkdown(signal.aiBody));
      }
      if (signal.aiMeta !== undefined && signal.aiMeta.length > 0) {
        lines.push(escapeMarkdown(signal.aiMeta));
      }
    }
  }
  lines.push("");
  lines.push("信号类型");
  lines.push(escapeMarkdown(signal.family));
  return lines;
}

function renderMetrics(symbol: HoverSymbolView): string[] {
  const vwap =
    symbol.vwapBias !== undefined ? `VWAP ${symbol.vwap} · ${symbol.vwapBias}` : `VWAP ${symbol.vwap}`;
  return [
    "涨跌幅",
    `1m ${symbol.change1m} | 5m ${symbol.change5m} | 15m ${symbol.change15m}`,
    "",
    "成交",
    `1m ${symbol.volumeRatio1m} | 5m ${symbol.volumeRatio5m}`,
    "",
    "技术指标",
    `EMA5 ${symbol.ema5} | EMA20 ${symbol.ema20} | RSI14 ${symbol.rsi14}`,
    vwap,
    "",
    "日内区间",
    `高 ${symbol.sessionHighObs} / 前高 ${symbol.sessionHighRef}`,
    `低 ${symbol.sessionLowObs} / 前低 ${symbol.sessionLowRef}`,
  ];
}

function renderSymbol(symbol: HoverSymbolView): string {
  const feed = symbol.feedStatus !== undefined ? ` · ${symbol.feedStatus}` : "";
  const lines = [
    escapeMarkdown(symbol.displayName),
    `${symbol.price} · ${symbol.changeDay} · ${symbol.level}${feed}`,
  ];
  if (symbol.signals.length === 0) {
    lines.push("");
    lines.push(...renderMetrics(symbol));
    return joinMarkdownLines(lines);
  }
  lines.push("");
  for (const [index, signal] of symbol.signals.entries()) {
    if (index > 0) {
      lines.push("---");
    }
    lines.push(...renderSignal(signal));
  }
  if (symbol.moreSignals > 0) {
    lines.push(`+${symbol.moreSignals} more active signals`);
  }
  lines.push("");
  lines.push(...renderMetrics(symbol));
  return joinMarkdownLines(lines);
}

export function renderHoverMarkdown(model: HoverModel): string {
  if (!model.enableDetails) {
    return model.headline;
  }

  const lines = [model.title, ""];
  if (model.connection !== undefined) {
    lines.push(`连接：${model.connection}`);
  }
  if (model.feedSource !== undefined) {
    lines.push(`行情源：${model.feedSource}`);
  }
  if (model.aiStatus !== undefined) {
    lines.push(`AI：${model.aiStatus}`);
  }
  if (model.unreadLine !== undefined) {
    lines.push(model.unreadLine);
  }
  if (model.lastUpdate !== undefined) {
    if (model.lastUpdate === "--") {
      lines.push(`最后行情：${model.lastUpdate}`);
    } else {
      lines.push(`最后行情：${model.lastUpdate}（UTC+8）`);
    }
  }
  if (model.replayMode === true) {
    lines.push("模式：Replay");
    if (model.replayStatus !== undefined) {
      lines.push(`状态：${model.replayStatus}`);
    }
  }
  if (model.lifecycleMessage !== undefined && model.symbols.length === 0) {
    lines.push("");
    lines.push(model.lifecycleMessage);
    if (model.outputHint !== undefined) {
      lines.push(model.outputHint);
    }
    return joinMarkdownLines(lines).trimEnd();
  }
  for (const symbol of model.symbols) {
    lines.push("");
    lines.push(renderSymbol(symbol));
  }
  return joinMarkdownLines(lines).trimEnd();
}
