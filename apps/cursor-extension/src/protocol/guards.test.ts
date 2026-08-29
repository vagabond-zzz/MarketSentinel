import { describe, expect, it } from "vitest";

import { parseCoreMessage } from "./guards";

const validState = {
  watchlist_count: 1,
  feed_status: "LIVE",
  symbols: [
    {
      symbol: "00700.HK",
      price: 100,
      scheduler_level: "COLD",
      feed_status: "LIVE",
      change_1m: 0.006,
      change_5m: null,
      change_15m: null,
      volume_ratio_1m: null,
      volume_ratio_5m: 1.8,
      ema5: 100,
      ema20: 99,
      rsi14: 55,
      vwap: 100,
      active_signals: [
        {
          id: "s1",
          family: "tape",
          direction: "up",
          priority: "important",
          title: "t",
          summary: "sum",
        },
      ],
    },
  ],
};

describe("parseCoreMessage", () => {
  it("accepts ready", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "ready",
      request_id: "h1",
      core_version: "0.2.0",
    });
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.message.type).toBe("ready");
    }
  });

  it("accepts state with null numeric fields", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "state",
      request_id: "g1",
      state: validState,
    });
    expect(parsed.ok).toBe(true);
    if (parsed.ok && parsed.message.type === "state") {
      expect(parsed.message.state.symbols[0]?.change_5m).toBeNull();
      expect(parsed.message.state.symbols[0]?.price).toBe(100);
      expect(parsed.message.state.symbols[0]?.change_day).toBeNull();
      expect(parsed.message.state.replay_complete).toBe(false);
      expect(parsed.message.state.intelligence_enabled).toBe(false);
    }
  });

  it("accepts unsolicited state without request_id", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "state",
      state: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [] },
    });
    expect(parsed.ok).toBe(true);
    if (parsed.ok && parsed.message.type === "state") {
      expect(parsed.message.request_id).toBeUndefined();
    }
  });

  it("accepts alert", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "alert",
      candidates: [
        {
          id: "a1",
          symbol: "00700.HK",
          family: "tape",
          direction: "down",
          priority: "notice",
          title: "t",
          summary: "s",
        },
      ],
      market_timestamp: 1.5,
    });
    expect(parsed.ok).toBe(true);
  });

  it("rejects wrong protocol version", () => {
    const parsed = parseCoreMessage({
      protocol_version: 2,
      type: "ready",
      request_id: "h1",
      core_version: "0.2.0",
    });
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) {
      expect(parsed.requestId).toBe("h1");
    }
  });

  it("rejects missing required field", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "ready",
      request_id: "h1",
    });
    expect(parsed.ok).toBe(false);
  });

  it("rejects invalid scheduler_level", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "state",
      state: {
        watchlist_count: 1,
        feed_status: "LIVE",
        symbols: [{ ...validState.symbols[0], scheduler_level: "LUKEWARM" }],
      },
    });
    expect(parsed.ok).toBe(false);
  });

  it("rejects invalid feed_status, direction, and priority", () => {
    expect(
      parseCoreMessage({
        protocol_version: 1,
        type: "state",
        state: { watchlist_count: 0, feed_status: "OK", symbols: [] },
      }).ok,
    ).toBe(false);
    expect(
      parseCoreMessage({
        protocol_version: 1,
        type: "alert",
        candidates: [
          {
            id: "a",
            symbol: "x",
            family: "tape",
            direction: "sideways",
            priority: "info",
            title: "t",
            summary: "s",
          },
        ],
        market_timestamp: null,
      }).ok,
    ).toBe(false);
  });

  it("rejects non-object", () => {
    expect(parseCoreMessage([]).ok).toBe(false);
    expect(parseCoreMessage(null).ok).toBe(false);
  });

  it("accepts v1 state without intelligence and optional enrichment", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "state",
      request_id: "g1",
      state: validState,
    });
    expect(parsed.ok).toBe(true);
    if (parsed.ok && parsed.message.type === "state") {
      expect(parsed.message.state.symbols[0]?.active_signals[0]?.intelligence).toBeUndefined();
    }
    const enriched = structuredClone(validState);
    enriched.symbols[0].active_signals[0].intelligence = {
      status: "enriched",
      summary: "note",
      confidence: 0.8,
    };
    const withIntel = parseCoreMessage({
      protocol_version: 1,
      type: "state",
      state: enriched,
    });
    expect(withIntel.ok).toBe(true);
    if (withIntel.ok && withIntel.message.type === "state") {
      expect(withIntel.message.state.symbols[0]?.active_signals[0]?.intelligence?.summary).toBe(
        "note",
      );
    }
  });

  it("accepts additive optional v1 fields without requiring them", () => {
    const parsed = parseCoreMessage({
      protocol_version: 1,
      type: "state",
      state: {
        ...validState,
        intelligence_enabled: true,
        replay_complete: true,
        last_market_timestamp: 12.5,
        extra_ignored: true,
        symbols: [
          {
            ...validState.symbols[0],
            change_day: 0.0128,
            above_vwap: false,
            session_high_obs: 101,
            session_low_obs: 99,
            session_high_ref: 100.4,
            session_low_ref: 100,
            market_timestamp: 12.5,
          },
        ],
      },
    });
    expect(parsed.ok).toBe(true);
    if (parsed.ok && parsed.message.type === "state") {
      expect(parsed.message.state.intelligence_enabled).toBe(true);
      expect(parsed.message.state.replay_complete).toBe(true);
      expect(parsed.message.state.last_market_timestamp).toBe(12.5);
      expect(parsed.message.state.symbols[0]?.change_day).toBe(0.0128);
      expect(parsed.message.state.symbols[0]?.above_vwap).toBe(false);
    }
  });
});
