import { describe, expect, it } from "vitest";

import {
  displaySymbol,
  parseIntelligenceMode,
  parseStatusBarMaxSymbols,
  parseSymbolDisplay,
  parseSymbolNames,
} from "./display";

describe("display helpers", () => {
  it("falls back to the canonical code when no alias exists", () => {
    expect(displaySymbol("600519.SH", {}, "nameAndCode", "hover")).toBe("600519.SH");
    expect(displaySymbol("600519.SH", {}, "name", "statusBar")).toBe("600519.SH");
  });

  it("uses alias only for UI display and never as identity", () => {
    const names = { "600519.SH": "贵州茅台" };
    expect(displaySymbol("600519.SH", names, "name", "statusBar")).toBe("贵州茅台");
    expect(displaySymbol("600519.SH", names, "nameAndCode", "hover")).toBe(
      "贵州茅台 (600519.SH)",
    );
    expect(displaySymbol("600519.SH", names, "code", "hover")).toBe("600519.SH");
    expect(displaySymbol("600519.SH", names, "nameAndCode", "statusBar")).toBe("贵州茅台");
  });

  it("parses symbolNames without inventing aliases", () => {
    expect(parseSymbolNames({ "600519.SH": "贵州茅台", skip: 1, "": "x" })).toEqual({
      "600519.SH": "贵州茅台",
    });
    expect(parseSymbolNames("nope")).toEqual({});
  });

  it("parses display mode, intelligence mode, and statusBar max symbols", () => {
    expect(parseSymbolDisplay(undefined)).toBe("nameAndCode");
    expect(parseSymbolDisplay("code")).toBe("code");
    expect(parseIntelligenceMode(undefined)).toBe("off");
    expect(parseIntelligenceMode("inherit")).toBe("inherit");
    expect(parseStatusBarMaxSymbols(undefined)).toBe(2);
    expect(parseStatusBarMaxSymbols(1)).toBe(1);
    expect(parseStatusBarMaxSymbols(9)).toBe(3);
    expect(parseStatusBarMaxSymbols(0)).toBe(1);
  });
});
