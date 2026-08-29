import { describe, expect, it } from "vitest";

import { planAddSymbol, planRemoveSymbol, watchlistsEqual } from "./watchlistEdit";

describe("watchlist edit", () => {
  it("adds a trimmed symbol and rejects empty, duplicate, and overflow", () => {
    const added = planAddSymbol([], "  600519.SH  ");
    expect(added).toEqual({ ok: true, items: [{ symbol: "600519.SH", enabled: true }] });
    expect(planAddSymbol([], "   ").ok).toBe(false);
    expect(planAddSymbol([{ symbol: "600519.SH", enabled: true }], "600519.SH").ok).toBe(false);
    const ten = Array.from({ length: 10 }, (_, index) => ({
      symbol: `S${index}.SH`,
      enabled: true,
    }));
    expect(planAddSymbol(ten, "NEW.SH").ok).toBe(false);
  });

  it("removes by canonical symbol id", () => {
    const current = [
      { symbol: "600519.SH", enabled: true },
      { symbol: "000001.SZ", enabled: true },
    ];
    expect(planRemoveSymbol(current, "600519.SH")).toEqual({
      ok: true,
      items: [{ symbol: "000001.SZ", enabled: true }],
    });
    expect(planRemoveSymbol(current, "missing").ok).toBe(false);
  });

  it("treats symbol and enabled as watchlist identity for no-op compares", () => {
    const items = [
      { symbol: "A.SH", enabled: false },
      { symbol: "B.SH", enabled: true },
    ];
    expect(watchlistsEqual(items, items.map((item) => ({ ...item })))).toBe(true);
    expect(watchlistsEqual(items, [{ symbol: "A.SH", enabled: true }, items[1]!])).toBe(false);
  });
});
