import { describe, expect, it } from "vitest";

import type { WireAlertCandidate } from "../protocol/types";
import {
  applyUnreadBadge,
  formatAlertDiagnostic,
  formatUnreadBadge,
  parseAlertToast,
  planCriticalToast,
} from "./state";

function candidate(overrides: Partial<WireAlertCandidate> = {}): WireAlertCandidate {
  return {
    id: "a1",
    symbol: "00700.HK",
    family: "price_volume",
    direction: "up",
    priority: "important",
    title: "breakout",
    summary: "edge",
    ...overrides,
  };
}

describe("unread badge presentation", () => {
  it("omits the badge at 0 and caps at 99+", () => {
    expect(formatUnreadBadge(0)).toBeUndefined();
    expect(formatUnreadBadge(2)).toBe("2");
    expect(formatUnreadBadge(99)).toBe("99");
    expect(formatUnreadBadge(100)).toBe("99+");
    expect(applyUnreadBadge("MS HOT", 0)).toBe("MS HOT");
    expect(applyUnreadBadge("MS HOT", 2)).toBe("MS HOT · 2");
    expect(applyUnreadBadge("MS STALE", 100)).toBe("MS STALE · 99+");
  });
});

describe("alert diagnostics and toast plan", () => {
  it("formats a short diagnostic without title or summary", () => {
    expect(formatAlertDiagnostic(candidate())).toBe(
      "alert candidate symbol=00700.HK priority=important family=price_volume",
    );
  });

  it("defaults alertToast to off and only toasts critical candidates", () => {
    expect(parseAlertToast(undefined)).toBe("off");
    expect(parseAlertToast("critical")).toBe("critical");
    expect(planCriticalToast("off", [candidate({ priority: "critical" })]).show).toBe(false);
    expect(planCriticalToast("critical", [candidate()]).show).toBe(false);
    expect(planCriticalToast("critical", [candidate({ priority: "critical", title: "crash" })])).toEqual({
      show: true,
      message: "Market Sentinel: crash",
    });
  });

  it("emits one toast for multiple critical candidates in one message", () => {
    expect(
      planCriticalToast("critical", [
        candidate({ id: "c1", priority: "critical", title: "first" }),
        candidate({ id: "c2", priority: "important", title: "ignored" }),
        candidate({ id: "c3", priority: "critical", title: "second" }),
      ]),
    ).toEqual({
      show: true,
      message: "Market Sentinel: first (+1 more)",
    });
  });
});
