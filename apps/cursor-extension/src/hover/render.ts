import { escapeMarkdown } from "./format";
import type { HoverModel, HoverSymbolView } from "./model";

function renderSymbol(symbol: HoverSymbolView): string {
  const feed = symbol.feedStatus !== undefined ? ` · ${symbol.feedStatus}` : "";
  const lines = [`${escapeMarkdown(symbol.symbol)}  ${symbol.level}${feed}`];
  if (!symbol.showDetails) {
    return lines.join("\n");
  }
  lines.push(`Price: ${symbol.price}`);
  lines.push(`1m: ${symbol.change1m} | 5m: ${symbol.change5m}`);
  lines.push(`Vol 5m: ${symbol.volumeRatio5m}`);
  for (const signal of symbol.signals) {
    lines.push(
      `[${signal.priority}][${signal.direction}] ${escapeMarkdown(signal.family)}`,
    );
    if (signal.body.length > 0) {
      lines.push(escapeMarkdown(signal.body));
    }
  }
  if (symbol.moreSignals > 0) {
    lines.push(`+${symbol.moreSignals} more active signals`);
  }
  lines.push(symbol.detailsLine);
  return lines.join("\n");
}

export function renderHoverMarkdown(model: HoverModel): string {
  if (!model.enableDetails) {
    return model.headline;
  }

  const lines = [model.title, ""];
  if (model.lifecycleMessage !== undefined) {
    lines.push(model.lifecycleMessage);
    if (model.outputHint !== undefined) {
      lines.push(model.outputHint);
    }
    return lines.join("\n").trimEnd();
  }

  if (model.feed !== undefined) {
    lines.push(`Feed: ${model.feed}`);
  }
  if (model.symbolCount !== undefined) {
    lines.push(`Symbols: ${model.symbolCount}`);
  }
  if (model.hotCount !== undefined) {
    lines.push(`HOT: ${model.hotCount}`);
  }
  if (model.warmCount !== undefined) {
    lines.push(`WARM: ${model.warmCount}`);
  }
  for (const symbol of model.symbols) {
    lines.push("");
    lines.push(renderSymbol(symbol));
  }
  return lines.join("\n").trimEnd();
}
