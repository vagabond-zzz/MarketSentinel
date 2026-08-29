import type { WatchlistItem } from "../protocol/types";
import { WATCHLIST_LIMIT } from "./display";

export type WatchlistEditResult =
  | { ok: true; items: WatchlistItem[] }
  | { ok: false; error: string };

export function planAddSymbol(current: WatchlistItem[], raw: string): WatchlistEditResult {
  const symbol = raw.trim();
  if (symbol.length === 0) {
    return { ok: false, error: "symbol must be a non-empty string" };
  }
  if (current.some((item) => item.symbol === symbol)) {
    return { ok: false, error: `duplicate symbol: ${symbol}` };
  }
  if (current.length >= WATCHLIST_LIMIT) {
    return { ok: false, error: `watchlist limit is ${WATCHLIST_LIMIT}` };
  }
  return { ok: true, items: [...current, { symbol, enabled: true }] };
}

export function planRemoveSymbol(current: WatchlistItem[], symbol: string): WatchlistEditResult {
  if (!current.some((item) => item.symbol === symbol)) {
    return { ok: false, error: `unknown symbol: ${symbol}` };
  }
  return { ok: true, items: current.filter((item) => item.symbol !== symbol) };
}
