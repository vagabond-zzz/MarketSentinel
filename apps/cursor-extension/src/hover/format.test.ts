import { describe, expect, it } from "vitest";

import { DASH, escapeMarkdown, formatPercent, formatPrice, formatRatio, formatRsi } from "./format";

describe("hover formatters", () => {
  it("renders missing values as --", () => {
    expect(formatPercent(null)).toBe(DASH);
    expect(formatRatio(null)).toBe(DASH);
    expect(formatRsi(null)).toBe(DASH);
    expect(formatPrice(null)).toBe(DASH);
  });

  it("formats percents like the CLI", () => {
    expect(formatPercent(0.006)).toBe("+0.60%");
    expect(formatPercent(-0.0125)).toBe("-1.25%");
    expect(formatPercent(0)).toBe("+0.00%");
  });

  it("formats ratios, RSI, and prices", () => {
    expect(formatRatio(1.8)).toBe("1.80x");
    expect(formatRsi(55.123)).toBe("55.1");
    expect(formatPrice(602.5)).toBe("602.50");
  });

  it("escapes Markdown metacharacters in Core text", () => {
    expect(escapeMarkdown("a[b](c)")).toBe("a\\[b\\]\\(c\\)");
    expect(escapeMarkdown("x*y_z")).toBe("x\\*y\\_z");
    expect(escapeMarkdown("line\nbreak")).toBe("line break");
  });
});
