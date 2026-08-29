import { isRecord } from "../protocol/guards";

export type SymbolDisplayMode = "name" | "nameAndCode" | "code";
export type IntelligenceMode = "off" | "on" | "inherit";

export const WATCHLIST_LIMIT = 10;
export const STATUS_BAR_MAX_SYMBOLS_DEFAULT = 2;
export const STATUS_BAR_MAX_SYMBOLS_MIN = 1;
export const STATUS_BAR_MAX_SYMBOLS_MAX = 3;

export function parseSymbolDisplay(raw: unknown): SymbolDisplayMode {
  if (raw === "name" || raw === "code" || raw === "nameAndCode") {
    return raw;
  }
  return "nameAndCode";
}

export function parseSymbolNames(raw: unknown): Record<string, string> {
  if (raw === undefined || raw === null) {
    return {};
  }
  if (!isRecord(raw)) {
    return {};
  }
  const names: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    const symbol = key.trim();
    if (symbol.length === 0 || typeof value !== "string") {
      continue;
    }
    const label = value.trim();
    if (label.length === 0) {
      continue;
    }
    names[symbol] = label;
  }
  return names;
}

export function parseIntelligenceMode(raw: unknown): IntelligenceMode {
  if (raw === "on" || raw === "off" || raw === "inherit") {
    return raw;
  }
  return "off";
}

export function parseStatusBarMaxSymbols(raw: unknown): number {
  const value = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(value)) {
    return STATUS_BAR_MAX_SYMBOLS_DEFAULT;
  }
  return Math.min(
    STATUS_BAR_MAX_SYMBOLS_MAX,
    Math.max(STATUS_BAR_MAX_SYMBOLS_MIN, Math.trunc(value)),
  );
}

export function displaySymbol(
  symbol: string,
  names: Record<string, string>,
  mode: SymbolDisplayMode,
  surface: "statusBar" | "hover",
): string {
  const alias = names[symbol];
  if (surface === "statusBar") {
    if (mode === "code" || alias === undefined) {
      return symbol;
    }
    return alias;
  }
  if (alias === undefined || mode === "code") {
    return symbol;
  }
  if (mode === "name") {
    return alias;
  }
  return `${alias} (${symbol})`;
}
