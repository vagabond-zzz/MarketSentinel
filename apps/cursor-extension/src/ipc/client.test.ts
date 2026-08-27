import { afterEach, describe, expect, it, vi } from "vitest";

import type { AlertMessage, StateMessage } from "../protocol/types";
import { IpcClient } from "./client";
import { IpcDisconnectedError, IpcTimeoutError, ProtocolError } from "./errors";

function emptyState() {
  return { watchlist_count: 0, feed_status: "DISCONNECTED" as const, symbols: [] };
}

function createClient(requestId?: () => string) {
  const written: string[] = [];
  const errors: ProtocolError[] = [];
  const states: StateMessage[] = [];
  const alerts: AlertMessage[] = [];
  let n = 0;
  const client = new IpcClient({
    write: (line) => {
      written.push(line);
    },
    helloTimeoutMs: 40,
    defaultTimeoutMs: 40,
    requestId: requestId ?? (() => `id${++n}`),
  });
  client.onProtocolError((error) => errors.push(error));
  client.onState((message) => states.push(message));
  client.onAlert((message) => alerts.push(message));
  return { client, written, errors, states, alerts };
}

function parseWritten(line: string): { type: string; request_id: string } {
  return JSON.parse(line) as { type: string; request_id: string };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("IpcClient", () => {
  it("matches request_id for ready", async () => {
    const { client, written } = createClient();
    const pending = client.request({ type: "hello", host: "test" });
    const sent = parseWritten(written[0] ?? "");
    expect(sent.type).toBe("hello");
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "ready",
        request_id: sent.request_id,
        core_version: "0.2.0",
      }) + "\n",
    );
    const ready = await pending;
    expect(ready.type).toBe("ready");
  });

  it("resolves concurrent requests out of order", async () => {
    const { client, written } = createClient();
    const first = client.request({ type: "get_state" });
    const second = client.request({ type: "get_state" });
    const id1 = parseWritten(written[0] ?? "").request_id;
    const id2 = parseWritten(written[1] ?? "").request_id;
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "state",
        request_id: id2,
        state: emptyState(),
      }) + "\n",
    );
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "state",
        request_id: id1,
        state: { ...emptyState(), watchlist_count: 1 },
      }) + "\n",
    );
    const [a, b] = await Promise.all([first, second]);
    expect(a.type === "state" && a.state.watchlist_count).toBe(1);
    expect(b.type === "state" && b.state.watchlist_count).toBe(0);
  });

  it("times out and ignores a late response", async () => {
    const { client, written, errors } = createClient();
    const first = client.request({ type: "hello" });
    const firstId = parseWritten(written[0] ?? "").request_id;
    await expect(first).rejects.toBeInstanceOf(IpcTimeoutError);
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "ready",
        request_id: firstId,
        core_version: "0.2.0",
      }) + "\n",
    );
    const second = client.request({ type: "hello" });
    const secondId = parseWritten(written[1] ?? "").request_id;
    expect(secondId).not.toBe(firstId);
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "ready",
        request_id: secondId,
        core_version: "0.2.0",
      }) + "\n",
    );
    await expect(second).resolves.toMatchObject({ type: "ready" });
    expect(errors.some((item) => item.code === "unknown_request_id")).toBe(true);
  });

  it("rejects an error response with code and request_id", async () => {
    const { client, written } = createClient();
    const pending = client.request({ type: "start" });
    const id = parseWritten(written[0] ?? "").request_id;
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "error",
        request_id: id,
        code: "not_ready",
        message: "hello is required first",
      }) + "\n",
    );
    await expect(pending).rejects.toMatchObject({
      name: "ProtocolError",
      code: "not_ready",
      requestId: id,
      message: "hello is required first",
    });
  });

  it("does not resolve a random pending request for unknown request_id", async () => {
    const { client, errors } = createClient();
    const pending = client.request({ type: "hello" });
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "ready",
        request_id: "nope",
        core_version: "0.2.0",
      }) + "\n",
    );
    expect(errors[0]?.code).toBe("unknown_request_id");
    client.dispose();
    await expect(pending).rejects.toBeInstanceOf(IpcDisconnectedError);
  });

  it("does not emit onState for a get_state response", async () => {
    const { client, written, states } = createClient();
    const pending = client.request({ type: "get_state" });
    const id = parseWritten(written[0] ?? "").request_id;
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "state",
        request_id: id,
        state: emptyState(),
      }) + "\n",
    );
    const snapshot = await pending;
    expect(snapshot.type).toBe("state");
    expect(states).toHaveLength(0);
  });

  it("routes unsolicited state and alert separately", async () => {
    const { client, states, alerts } = createClient();
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "state",
        state: {
          watchlist_count: 1,
          feed_status: "LIVE",
          symbols: [
            {
              symbol: "00700.HK",
              price: 1,
              scheduler_level: "HOT",
              feed_status: "LIVE",
              change_1m: null,
              change_5m: null,
              change_15m: null,
              volume_ratio_1m: null,
              volume_ratio_5m: null,
              ema5: null,
              ema20: null,
              rsi14: null,
              vwap: null,
              active_signals: [
                {
                  id: "live",
                  family: "tape",
                  direction: "up",
                  priority: "info",
                  title: "t",
                  summary: "s",
                },
              ],
            },
          ],
        },
      }) + "\n",
    );
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "alert",
        candidates: [
          {
            id: "a1",
            symbol: "00700.HK",
            family: "tape",
            direction: "up",
            priority: "important",
            title: "alert",
            summary: "edge",
          },
        ],
        market_timestamp: 2,
      }) + "\n",
    );
    expect(states).toHaveLength(1);
    expect(alerts).toHaveLength(1);
    expect(alerts[0]?.candidates[0]?.id).toBe("a1");
    expect(states[0]?.state.symbols[0]?.active_signals[0]?.id).toBe("live");
  });

  it("does not crash on malformed JSON", () => {
    const { client, errors } = createClient();
    expect(() => client.feed("{not json\n")).not.toThrow();
    expect(errors[0]?.code).toBe("invalid_json");
  });

  it("rejects a pending request when the matching response is malformed", async () => {
    const { client, written } = createClient();
    const pending = client.request({ type: "hello" });
    const id = parseWritten(written[0] ?? "").request_id;
    client.feed(
      JSON.stringify({
        protocol_version: 1,
        type: "ready",
        request_id: id,
      }) + "\n",
    );
    await expect(pending).rejects.toMatchObject({ code: "malformed_response", requestId: id });
  });

  it("dispose rejects pending requests", async () => {
    const { client } = createClient();
    const pending = client.request({ type: "get_state" });
    client.dispose();
    await expect(pending).rejects.toBeInstanceOf(IpcDisconnectedError);
  });
});
