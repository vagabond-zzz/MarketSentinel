import { describe, expect, it } from "vitest";

import { parseEnableHoverDetails, parseHostSettings, parseWatchlist, resolveCoreRoot } from "./config";

describe("resolveCoreRoot", () => {
  it("uses an explicit coreRoot regardless of workspace count", () => {
    expect(resolveCoreRoot("D:/core", [])).toBe("D:/core");
    expect(resolveCoreRoot("D:/core", ["A", "B"])).toBe("D:/core");
  });

  it("falls back to the only workspace folder", () => {
    expect(resolveCoreRoot(undefined, ["D:/ws"])).toBe("D:/ws");
    expect(resolveCoreRoot("  ", ["D:/ws"])).toBe("D:/ws");
  });

  it("requires coreRoot when there is no workspace", () => {
    expect(() => resolveCoreRoot(undefined, [])).toThrow(/no workspace folder/);
  });

  it("requires coreRoot for multi-root workspaces", () => {
    expect(() => resolveCoreRoot(undefined, ["A", "B"])).toThrow(/multi-root/);
  });
});

describe("parseWatchlist", () => {
  it("accepts strings and objects", () => {
    expect(parseWatchlist(["00700.HK", { symbol: "00941.HK", enabled: false }])).toEqual([
      { symbol: "00700.HK", enabled: true },
      { symbol: "00941.HK", enabled: false },
    ]);
  });

  it("rejects a non-array", () => {
    expect(() => parseWatchlist("00700.HK")).toThrow(/array/);
  });
});

describe("parseEnableHoverDetails", () => {
  it("defaults to true and only disables on explicit false", () => {
    expect(parseEnableHoverDetails(undefined)).toBe(true);
    expect(parseEnableHoverDetails(true)).toBe(true);
    expect(parseEnableHoverDetails(false)).toBe(false);
  });
});

describe("parseHostSettings", () => {
  it("defaults provider to fake and uv to uv", () => {
    const parsed = parseHostSettings({}, ["D:/repo"]);
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.config.uvPath).toBe("uv");
      expect(parsed.config.provider).toBe("fake");
      expect(parsed.config.coreRoot).toBe("D:/repo");
    }
  });

  it("requires replayPath for replay", () => {
    const parsed = parseHostSettings({ provider: "replay" }, ["D:/repo"]);
    expect(parsed.ok).toBe(false);
  });

  it("rejects http provider", () => {
    const parsed = parseHostSettings({ provider: "http" }, ["D:/repo"]);
    expect(parsed.ok).toBe(false);
  });

  it("rejects empty uvPath", () => {
    const parsed = parseHostSettings({ uvPath: "  " }, ["D:/repo"]);
    expect(parsed.ok).toBe(false);
  });
});
