import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import type { ChildProcess, SpawnOptions } from "node:child_process";

import { describe, expect, it, vi } from "vitest";

import { JsonlDecoder } from "../ipc/jsonl";
import { ProcessManager } from "../ipc/process";
import type { WatchlistItem } from "../protocol/types";
import { HostController } from "./controller";
import type { HostLogger, RawSettings } from "./types";

class FakeChild extends EventEmitter {
  stdin = new PassThrough();
  stdout = new PassThrough();
  stderr = new PassThrough();
  exitCode: number | null = null;
  kill = vi.fn(() => {
    this.exitCode = 1;
    this.emit("exit", 1, null);
    return true;
  });
}

function asChild(child: FakeChild): ChildProcess {
  return child as unknown as ChildProcess;
}

function scriptDaemon(
  child: FakeChild,
  log: unknown[],
  options: { protocolVersion?: number; hangWatchlist?: boolean; failGetState?: boolean } = {},
): void {
  const decoder = new JsonlDecoder();
  child.stdin.on("data", (chunk: Buffer | string) => {
    for (const line of decoder.push(chunk)) {
      const command = JSON.parse(line) as {
        type: string;
        request_id: string;
        items?: WatchlistItem[];
      };
      log.push(command);
      const version = options.protocolVersion ?? 1;
      if (command.type === "hello") {
        child.stdout.write(
          JSON.stringify({
            protocol_version: version,
            type: "ready",
            request_id: command.request_id,
            core_version: "0.2.0",
          }) + "\n",
        );
      } else if (command.type === "set_watchlist") {
        const items = command.items ?? [];
        if (options.hangWatchlist) {
          return;
        }
        if (items.length > 10) {
          child.stdout.write(
            JSON.stringify({
              protocol_version: 1,
              type: "error",
              request_id: command.request_id,
              code: "watchlist_full",
              message: "watchlist limit is 10",
            }) + "\n",
          );
          return;
        }
        child.stdout.write(
          JSON.stringify({
            protocol_version: 1,
            type: "ack",
            request_id: command.request_id,
            watchlist_count: items.length,
          }) + "\n",
        );
      } else if (command.type === "get_state") {
        if (options.failGetState) {
          child.stdout.write(
            JSON.stringify({
              protocol_version: 1,
              type: "error",
              request_id: command.request_id,
              code: "internal",
              message: "state unavailable",
            }) + "\n",
          );
          return;
        }
        child.stdout.write(
          JSON.stringify({
            protocol_version: 1,
            type: "state",
            request_id: command.request_id,
            state: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [] },
          }) + "\n",
        );
      } else if (command.type === "shutdown") {
        child.stdout.write(
          JSON.stringify({
            protocol_version: 1,
            type: "shutdown_ack",
            request_id: command.request_id,
          }) + "\n",
        );
        child.exitCode = 0;
        child.emit("exit", 0, null);
      } else {
        child.stdout.write(
          JSON.stringify({
            protocol_version: 1,
            type: "ack",
            request_id: command.request_id,
          }) + "\n",
        );
      }
    }
  });
}

function createLogger(): { logger: HostLogger; lines: string[] } {
  const lines: string[] = [];
  return {
    lines,
    logger: {
      host: (message) => lines.push(`[host] ${message}`),
      core: (message) => lines.push(`[core] ${message}`),
    },
  };
}

function wireSymbol(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    symbol: "00700.HK",
    price: 602.5,
    scheduler_level: "COLD",
    feed_status: "LIVE",
    change_1m: 0.008,
    change_5m: 0.0126,
    change_15m: null,
    volume_ratio_1m: null,
    volume_ratio_5m: 2.63,
    ema5: null,
    ema20: null,
    rsi14: 67.4,
    vwap: null,
    active_signals: [],
    ...overrides,
  };
}

function writeState(child: FakeChild | undefined, state: Record<string, unknown>): void {
  child?.stdout.write(
    JSON.stringify({
      protocol_version: 1,
      type: "state",
      state,
    }) + "\n",
  );
}

function writeAlert(
  child: FakeChild | undefined,
  candidates: Array<Record<string, unknown>>,
): void {
  child?.stdout.write(
    JSON.stringify({
      protocol_version: 1,
      type: "alert",
      candidates,
      market_timestamp: 1,
    }) + "\n",
  );
}

function alertCandidate(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "a1",
    symbol: "00700.HK",
    family: "price_volume",
    direction: "up",
    priority: "important",
    title: "alert",
    summary: "edge",
    ...overrides,
  };
}

interface Harness {
  controller: HostController;
  children: FakeChild[];
  commands: unknown[];
  spawned: { command: string; args: string[]; options: SpawnOptions }[];
  managers: ProcessManager[];
  settings: RawSettings;
  folders: string[];
  waits: number[];
  lines: string[];
}

function createHarness(
  extras: {
    script?: (child: FakeChild, generation: number) => void;
    settings?: RawSettings;
    folders?: string[];
    onUiSnapshot?: (snapshot: { statusBar: { kind: string; text: string } }) => void;
    onAlertEdge?: (message: { candidates: unknown[] }) => void;
    now?: () => number;
    alertHoldMs?: number;
    setTimeoutFn?: typeof setTimeout;
    clearTimeoutFn?: typeof clearTimeout;
  } = {},
): Harness {
  const children: FakeChild[] = [];
  const commands: unknown[] = [];
  const spawned: Harness["spawned"] = [];
  const managers: ProcessManager[] = [];
  const waits: number[] = [];
  const { logger, lines } = createLogger();
  const settings: RawSettings = { watchlist: [], ...extras.settings };
  const folders = extras.folders ?? ["D:/repo"];
  const controller = new HostController({
    readSettings: () => settings,
    workspaceFolders: () => folders,
    logger,
    delay: async (ms) => {
      waits.push(ms);
    },
    helloTimeoutMs: 80,
    defaultTimeoutMs: 80,
    now: extras.now,
    alertHoldMs: extras.alertHoldMs,
    setTimeoutFn: extras.setTimeoutFn,
    clearTimeoutFn: extras.clearTimeoutFn,
    onUiSnapshot: extras.onUiSnapshot,
    onAlertEdge: extras.onAlertEdge,
    createManager: (options) => {
      const manager = new ProcessManager(options);
      managers.push(manager);
      return manager;
    },
    spawnFn: (command, args, options) => {
      spawned.push({ command, args: [...args], options });
      const child = new FakeChild();
      children.push(child);
      const generation = children.length;
      if (extras.script !== undefined) {
        extras.script(child, generation);
      } else {
        scriptDaemon(child, commands);
      }
      return asChild(child);
    },
  });
  return { controller, children, commands, spawned, managers, settings, folders, waits, lines };
}

describe("HostController", () => {
  it("starts with valid config and records core_version without comparing host version", async () => {
    const harness = createHarness();
    await harness.controller.start();
    expect(harness.controller.actualState).toBe("RUNNING");
    expect(harness.controller.desiredState).toBe("RUNNING");
    expect(harness.controller.lastCoreVersion).toBe("0.2.0");
    expect(harness.commands.map((item) => (item as { type: string }).type)).toEqual([
      "hello",
      "set_watchlist",
      "start",
      "get_state",
    ]);
    expect(harness.lines.some((line) => line.includes("core_version=0.2.0"))).toBe(true);
  });

  it("does not throw the host when start fails", async () => {
    const harness = createHarness({
      script: (child) => {
        queueMicrotask(() => child.emit("exit", 1, null));
      },
    });
    await expect(harness.controller.start()).resolves.toBeUndefined();
    expect(harness.controller.actualState).toBe("DISCONNECTED");
    expect(harness.waits).toEqual([]);
  });

  it("shutdown is idempotent", async () => {
    const harness = createHarness();
    await harness.controller.start();
    await harness.controller.shutdown();
    await harness.controller.shutdown();
    expect(harness.controller.actualState).toBe("STOPPED");
  });

  it("pause sets desired PAUSED and does not spawn when already disconnected", async () => {
    const harness = createHarness();
    await harness.controller.pause();
    expect(harness.controller.desiredState).toBe("PAUSED");
    expect(harness.spawned).toHaveLength(0);
  });

  it("does not auto-restart when the core crashes while PAUSED", async () => {
    const harness = createHarness();
    await harness.controller.start();
    await harness.controller.pause();
    expect(harness.controller.actualState).toBe("PAUSED");
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.controller.actualState).toBe("DISCONNECTED");
    });
    expect(harness.controller.desiredState).toBe("PAUSED");
    expect(harness.waits).toEqual([]);
    expect(harness.spawned).toHaveLength(1);
  });

  it("resume of a live paused daemon sends resume, not a new handshake", async () => {
    const harness = createHarness();
    await harness.controller.start();
    await harness.controller.pause();
    await harness.controller.resume();
    expect(harness.controller.actualState).toBe("RUNNING");
    expect(harness.commands.map((item) => (item as { type: string }).type)).toEqual([
      "hello",
      "set_watchlist",
      "start",
      "get_state",
      "pause",
      "resume",
    ]);
    expect(harness.spawned).toHaveLength(1);
  });

  it("resume from disconnected spawns hello → set_watchlist → start, not resume", async () => {
    const harness = createHarness();
    await harness.controller.pause();
    await harness.controller.resume();
    expect(harness.controller.actualState).toBe("RUNNING");
    expect(harness.commands.map((item) => (item as { type: string }).type)).toEqual([
      "hello",
      "set_watchlist",
      "start",
      "get_state",
    ]);
  });

  it("auto-restarts with 1s/3s/10s backoff and stops after 3 attempts", async () => {
    const harness = createHarness({
      script: (child, generation) => {
        if (generation === 1) {
          scriptDaemon(child, harness.commands);
          return;
        }
        queueMicrotask(() => child.emit("exit", 1, null));
      },
    });
    await harness.controller.start();
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.waits).toEqual([1000, 3000, 10000]);
      expect(harness.controller.actualState).toBe("DISCONNECTED");
    });
    expect(harness.spawned.length).toBe(4);
  });

  it("resets the retry counter after a successful reconnect", async () => {
    const harness = createHarness();
    await harness.controller.start();
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.controller.actualState).toBe("RUNNING");
      expect(harness.managers.length).toBe(2);
    });
    expect(harness.waits).toEqual([1000]);
    harness.children[1]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.managers.length).toBe(3);
      expect(harness.controller.actualState).toBe("RUNNING");
    });
    expect(harness.waits).toEqual([1000, 1000]);
  });

  it("uses a fresh ProcessManager after restart", async () => {
    const harness = createHarness({
      script: (child, generation) => {
        if (generation === 1) {
          scriptDaemon(child, harness.commands);
          return;
        }
        scriptDaemon(child, harness.commands);
      },
    });
    await harness.controller.start();
    const first = harness.managers[0];
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.managers.length).toBe(2);
    });
    expect(harness.managers[1]).toBeDefined();
    expect(harness.managers[1]).not.toBe(first);
  });

  it("hot-applies watchlist and keeps last ack when Core rejects", async () => {
    const harness = createHarness({
      settings: { watchlist: [{ symbol: "AAA.HK", enabled: true }] },
    });
    await harness.controller.start();
    expect(harness.controller.lastAcknowledgedWatchlist).toEqual([
      { symbol: "AAA.HK", enabled: true },
    ]);
    harness.settings.watchlist = [{ symbol: "BBB.HK", enabled: true }];
    await harness.controller.onConfigurationChanged(["watchlist"]);
    expect(harness.controller.lastAcknowledgedWatchlist).toEqual([
      { symbol: "BBB.HK", enabled: true },
    ]);
    harness.settings.watchlist = Array.from({ length: 11 }, (_, index) => ({
      symbol: `S${index}.HK`,
      enabled: true,
    }));
    await harness.controller.onConfigurationChanged(["watchlist"]);
    expect(harness.controller.lastAcknowledgedWatchlist).toEqual([
      { symbol: "BBB.HK", enabled: true },
    ]);
    expect(harness.lines.some((line) => line.includes("rejected"))).toBe(true);
  });

  it("marks restartNeeded for coreRoot/provider changes without restarting", async () => {
    const harness = createHarness();
    await harness.controller.start();
    harness.settings.coreRoot = "D:/other";
    harness.settings.provider = "replay";
    harness.settings.replayPath = "fix.jsonl";
    await harness.controller.onConfigurationChanged(["coreRoot", "provider", "replayPath"]);
    expect(harness.controller.restartNeeded).toBe(true);
    expect(harness.spawned).toHaveLength(1);
    expect(harness.lines.some((line) => line.includes("restart core to apply"))).toBe(true);
  });

  it("treats longbridge as a restart-needed provider choice without secrets", async () => {
    const harness = createHarness();
    await harness.controller.start();
    harness.settings.provider = "longbridge";
    await harness.controller.onConfigurationChanged(["provider"]);
    expect(harness.controller.restartNeeded).toBe(true);
    expect(harness.spawned).toHaveLength(1);
    expect(harness.lines.join("\n")).not.toMatch(/LONGBRIDGE_/);
  });

  it("restartCore while PAUSED does not spawn a ticking daemon", async () => {
    const harness = createHarness();
    await harness.controller.start();
    await harness.controller.pause();
    const before = harness.spawned.length;
    await harness.controller.restartCore();
    expect(harness.controller.desiredState).toBe("PAUSED");
    expect(harness.controller.actualState).toBe("STOPPED");
    expect(harness.spawned.length).toBe(before);
  });

  it("does not spawn without coreRoot when there is no workspace", async () => {
    const harness = createHarness({ folders: [], settings: {} });
    await harness.controller.start();
    expect(harness.spawned).toHaveLength(0);
    expect(harness.controller.actualState).toBe("DISCONNECTED");
    expect(harness.controller.lastError).toMatch(/coreRoot/);
  });

  it("does not pick a folder in a multi-root workspace without coreRoot", async () => {
    const harness = createHarness({ folders: ["A", "B"] });
    await harness.controller.start();
    expect(harness.spawned).toHaveLength(0);
    expect(harness.controller.lastError).toMatch(/multi-root/);
  });

  it("uses a single workspace folder as coreRoot", async () => {
    const harness = createHarness({ folders: ["D:/only"] });
    await harness.controller.start();
    expect(harness.spawned[0]?.args).toContain("D:/only");
  });

  it("reports uv ENOENT with uvPath and coreRoot", async () => {
    const harness = createHarness({
      settings: { uvPath: "D:/missing/uv.exe", coreRoot: "D:/repo" },
      folders: [],
      script: (child) => {
        queueMicrotask(() => {
          const error = Object.assign(new Error("spawn D:/missing/uv.exe ENOENT"), {
            code: "ENOENT",
          });
          child.emit("error", error);
        });
      },
    });
    await harness.controller.start();
    expect(harness.controller.actualState).toBe("DISCONNECTED");
    expect(harness.controller.lastError).toMatch(/uvPath=D:\/missing\/uv.exe/);
    expect(harness.controller.lastError).toMatch(/coreRoot=D:\/repo/);
  });

  it("rejects a protocol_version mismatch via existing guards", async () => {
    const harness = createHarness({
      script: (child) => scriptDaemon(child, harness.commands, { protocolVersion: 2 }),
    });
    await harness.controller.start();
    expect(harness.controller.actualState).toBe("DISCONNECTED");
  });

  it("maps StatusBar from host lifecycle, feed, scheduler level, and alert messages", async () => {
    const views: string[] = [];
    const harness = createHarness({
      onUiSnapshot: (snapshot) => {
        views.push(snapshot.statusBar.kind);
      },
    });
    await harness.controller.start();
    expect(harness.controller.statusBarModel().kind).toBe("IDLE");

    harness.children[0]?.stdout.write(
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
                  priority: "important",
                  title: "t",
                  summary: "s",
                },
              ],
            },
          ],
        },
      }) + "\n",
    );
    expect(harness.controller.statusBarModel().kind).toBe("HOT");

    harness.children[0]?.stdout.write(
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
        market_timestamp: 1,
      }) + "\n",
    );
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");

    await harness.controller.pause();
    expect(harness.controller.statusBarModel().kind).toBe("PAUSED");
    expect(views).toContain("IDLE");
    expect(views).toContain("HOT");
    expect(views).toContain("ALERT");
    expect(views).toContain("PAUSED");
  });

  it("maps RUNNING without a MarketState snapshot to STARTING, not NORMAL", async () => {
    const harness = createHarness({
      script: (child) => scriptDaemon(child, harness.commands, { failGetState: true }),
    });
    await harness.controller.start();
    expect(harness.controller.actualState).toBe("RUNNING");
    expect(harness.controller.statusBarModel().kind).toBe("STARTING");
  });

  it("clears ALERT when the hold timer fires at elapsed === alertHoldMs", async () => {
    let now = 1_000;
    const timers: Array<() => void> = [];
    const harness = createHarness({
      now: () => now,
      alertHoldMs: 15_000,
      setTimeoutFn: ((callback: () => void) => {
        timers.push(callback);
        return 1 as unknown as ReturnType<typeof setTimeout>;
      }) as typeof setTimeout,
      clearTimeoutFn: () => undefined,
    });
    await harness.controller.start();
    harness.children[0]?.stdout.write(
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
              scheduler_level: "COLD",
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
              active_signals: [],
            },
          ],
        },
      }) + "\n",
    );
    harness.children[0]?.stdout.write(
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
        market_timestamp: 1,
      }) + "\n",
    );
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");
    now = 1_000 + 15_000;
    timers.at(-1)?.();
    expect(harness.controller.statusBarModel().kind).toBe("NORMAL");
  });

  it("builds HoverModel from state without turning active_signals into ALERT", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 2,
      feed_status: "LIVE",
      symbols: [
        wireSymbol({
          scheduler_level: "HOT",
          active_signals: [
            {
              id: "live",
              family: "price_volume",
              direction: "up",
              priority: "important",
              title: "t",
              summary: "量价同步扩张",
            },
          ],
        }),
        wireSymbol({ symbol: "600519.SH", scheduler_level: "COLD" }),
      ],
    });
    const snapshot = harness.controller.uiSnapshot();
    expect(snapshot.statusBar.kind).toBe("HOT");
    expect(snapshot.hover.feed).toBe("LIVE");
    expect(snapshot.hover.symbols.map((item) => item.symbol)).toEqual(["00700.HK", "600519.SH"]);
    expect(snapshot.hover.symbols[0]?.signals[0]?.family).toBe("price_volume");
    expect(snapshot.hover.headline).not.toMatch(/ALERT|NEW/);
  });

  it("maps STALE feed into Hover without looking live", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "STALE",
      symbols: [wireSymbol({ feed_status: "STALE", scheduler_level: "HOT" })],
    });
    expect(harness.controller.statusBarModel().kind).toBe("STALE");
    expect(harness.controller.hoverModel().feed).toBe("STALE");
    expect(harness.controller.hoverModel().lifecycleMessage).toBeUndefined();
  });

  it("uses starting-style Hover when RUNNING has no MarketState", async () => {
    const harness = createHarness({
      script: (child) => scriptDaemon(child, harness.commands, { failGetState: true }),
    });
    await harness.controller.start();
    expect(harness.controller.actualState).toBe("RUNNING");
    expect(harness.controller.hoverModel().lifecycleMessage).toBe("Core starting");
    expect(harness.controller.hoverModel().symbols).toEqual([]);
  });

  it("shows paused and disconnected Hover copy instead of last market prices", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol({ scheduler_level: "HOT" })],
    });
    await harness.controller.pause();
    expect(harness.controller.hoverModel().lifecycleMessage).toBe("Monitoring paused");
    expect(harness.controller.hoverModel().symbols).toEqual([]);
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.controller.actualState).toBe("DISCONNECTED");
    });
    expect(harness.controller.hoverModel().lifecycleMessage).toBe("Core disconnected");
    expect(harness.controller.hoverModel().outputHint).toMatch(/Output/);
  });

  it("hot-applies enableHoverDetails without restarting Core", async () => {
    const harness = createHarness();
    await harness.controller.start();
    const before = harness.spawned.length;
    const commandsBefore = harness.commands.length;
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol()],
    });
    harness.settings.enableHoverDetails = false;
    await harness.controller.onConfigurationChanged(["enableHoverDetails"]);
    expect(harness.spawned).toHaveLength(before);
    expect(harness.commands).toHaveLength(commandsBefore);
    expect(harness.controller.restartNeeded).toBe(false);
    expect(harness.controller.hoverModel().enableDetails).toBe(false);
    expect(harness.controller.hoverModel().headline).toBe(
      "Market Sentinel · LIVE · symbols=1 · HOT=0 · WARM=0",
    );
  });

  it("does not extend ALERT hold when Hover is read", async () => {
    let now = 1_000;
    const harness = createHarness({
      now: () => now,
      alertHoldMs: 15_000,
      setTimeoutFn: (() => 1 as unknown as ReturnType<typeof setTimeout>) as typeof setTimeout,
      clearTimeoutFn: () => undefined,
    });
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol()],
    });
    harness.children[0]?.stdout.write(
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
        market_timestamp: 1,
      }) + "\n",
    );
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");
    now = 1_000 + 10_000;
    harness.controller.hoverModel();
    harness.controller.uiSnapshot();
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");
    now = 1_000 + 15_000;
    expect(harness.controller.statusBarModel().kind).toBe("NORMAL");
    expect(harness.controller.unreadAlertCount).toBe(1);
    expect(harness.controller.statusBarModel().text).toBe("MS NORMAL · 1");
  });

  it("increments unread only from unsolicited alert candidates", async () => {
    const edges: number[] = [];
    const harness = createHarness({
      onAlertEdge: (message) => edges.push(message.candidates.length),
    });
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [
        wireSymbol({
          scheduler_level: "HOT",
          active_signals: [
            {
              id: "live",
              family: "price_volume",
              direction: "up",
              priority: "critical",
              title: "t",
              summary: "s",
            },
          ],
        }),
      ],
    });
    expect(harness.controller.unreadAlertCount).toBe(0);
    expect(harness.controller.statusBarModel().kind).toBe("HOT");

    writeAlert(harness.children[0], [alertCandidate()]);
    expect(harness.controller.unreadAlertCount).toBe(1);
    writeAlert(harness.children[0], [
      alertCandidate({ id: "a2" }),
      alertCandidate({ id: "a3" }),
      alertCandidate({ id: "a4" }),
    ]);
    expect(harness.controller.unreadAlertCount).toBe(4);
    writeAlert(harness.children[0], [alertCandidate({ id: "a1" })]);
    expect(harness.controller.unreadAlertCount).toBe(5);
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol({ scheduler_level: "WARM" })],
    });
    expect(harness.controller.unreadAlertCount).toBe(5);
    expect(edges).toEqual([1, 3, 1]);
    expect(
      harness.lines.some((line) =>
        line.includes("alert candidate symbol=00700.HK priority=important family=price_volume"),
      ),
    ).toBe(true);
  });

  it("keeps unread across Core crash/restart and ignores new active_signals", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol()],
    });
    writeAlert(harness.children[0], [alertCandidate()]);
    expect(harness.controller.unreadAlertCount).toBe(1);
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.controller.actualState).toBe("RUNNING");
      expect(harness.managers.length).toBe(2);
    });
    expect(harness.controller.unreadAlertCount).toBe(1);
    expect(harness.controller.statusBarModel().kind).not.toBe("ALERT");
    writeState(harness.children[1], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [
        wireSymbol({
          active_signals: [
            {
              id: "live",
              family: "price_volume",
              direction: "up",
              priority: "critical",
              title: "t",
              summary: "s",
            },
          ],
        }),
      ],
    });
    expect(harness.controller.unreadAlertCount).toBe(1);
    writeAlert(harness.children[1], [alertCandidate({ id: "after-restart" })]);
    expect(harness.controller.unreadAlertCount).toBe(2);
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");
  });

  it("resets unread without clearing transient ALERT or Core state", async () => {
    let now = 1_000;
    const harness = createHarness({
      now: () => now,
      alertHoldMs: 15_000,
      setTimeoutFn: (() => 1 as unknown as ReturnType<typeof setTimeout>) as typeof setTimeout,
      clearTimeoutFn: () => undefined,
    });
    await harness.controller.start();
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol({ scheduler_level: "HOT" })],
    });
    writeAlert(harness.children[0], [alertCandidate(), alertCandidate({ id: "a2" })]);
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");
    expect(harness.controller.statusBarModel().text).toBe("MS ALERT · 2");
    harness.controller.resetAlertBadge();
    expect(harness.controller.unreadAlertCount).toBe(0);
    expect(harness.controller.statusBarModel().kind).toBe("ALERT");
    expect(harness.controller.statusBarModel().text).toBe("MS ALERT");
    expect(harness.controller.hoverModel().symbols[0]?.level).toBe("HOT");
    now = 1_000 + 15_000;
    expect(harness.controller.statusBarModel().kind).toBe("HOT");
  });

  it("keeps unread when Core reports an empty watchlist", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate()]);
    expect(harness.controller.unreadAlertCount).toBe(1);
    writeState(harness.children[0], {
      watchlist_count: 0,
      feed_status: "DISCONNECTED",
      symbols: [],
    });
    expect(harness.controller.unreadAlertCount).toBe(1);
    expect(harness.controller.statusBarModel().kind).toBe("IDLE");
    expect(harness.controller.statusBarModel().text).toBe("MS IDLE · 1");
    expect(harness.controller.hoverModel().lifecycleMessage).toBe("No symbols configured");
    harness.controller.resetAlertBadge();
    expect(harness.controller.unreadAlertCount).toBe(0);
    expect(harness.controller.statusBarModel().text).toBe("MS IDLE");
  });

  it("hot-applies alertToast without restarting Core", async () => {
    const harness = createHarness();
    await harness.controller.start();
    const before = harness.spawned.length;
    harness.settings.alertToast = "critical";
    await harness.controller.onConfigurationChanged(["alertToast"]);
    expect(harness.spawned).toHaveLength(before);
    expect(harness.controller.restartNeeded).toBe(false);
  });

  it("sends one alert_presented command per candidate independent of toast", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [
      alertCandidate({ id: "c1" }),
      alertCandidate({ id: "c2" }),
      alertCandidate({ id: "c3" }),
    ]);
    await vi.waitFor(() => {
      const presented = (
        harness.commands as Array<{ type?: string; action?: string; signal_id?: string }>
      ).filter((item) => item.type === "host_interaction" && item.action === "alert_presented");
      expect(presented).toHaveLength(3);
      expect(presented.map((item) => item.signal_id)).toEqual(["c1", "c2", "c3"]);
    });
    expect(harness.controller.unreadAlertCount).toBe(3);
  });

  it("sends one alert_badge_reset and never fabricates alert_dismissed", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate()]);
    harness.controller.resetAlertBadge();
    await vi.waitFor(() => {
      const actions = (
        harness.commands as Array<{ type?: string; action?: string }>
      ).filter((item) => item.type === "host_interaction");
      expect(actions.some((item) => item.action === "alert_badge_reset")).toBe(true);
      expect(actions.some((item) => item.action === "alert_dismissed")).toBe(false);
    });
  });

  it("does not record signal_opened from hover", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate()]);
    harness.controller.hoverModel();
    harness.controller.uiSnapshot();
    const opened = (harness.commands as Array<{ type?: string; action?: string }>).filter(
      (item) => item.type === "host_interaction" && item.action === "signal_opened",
    );
    expect(opened).toHaveLength(0);
    const feedback = (harness.commands as Array<{ type?: string }>).filter(
      (item) => item.type === "user_feedback",
    );
    expect(feedback).toHaveLength(0);
  });

  it("sends user_feedback without title, workspace, or free text", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate({ id: "sig-9", title: "secret title" })]);
    await harness.controller.submitSignalFeedback("sig-9", "useful");
    await vi.waitFor(() => {
      const sent = (
        harness.commands as Array<{
          type?: string;
          signal_id?: string;
          feedback_type?: string;
          title?: string;
          workspace?: string;
        }>
      ).filter((item) => item.type === "user_feedback");
      expect(sent).toHaveLength(1);
      expect(sent[0]?.signal_id).toBe("sig-9");
      expect(sent[0]?.feedback_type).toBe("useful");
      expect(sent[0]).not.toHaveProperty("title");
      expect(sent[0]).not.toHaveProperty("summary");
      expect(sent[0]).not.toHaveProperty("workspace");
      expect(sent[0]).not.toHaveProperty("comment");
    });
  });

  it("does not treat badge reset as not_useful feedback", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate()]);
    harness.controller.resetAlertBadge();
    const feedback = (harness.commands as Array<{ type?: string; feedback_type?: string }>).filter(
      (item) => item.type === "user_feedback",
    );
    expect(feedback).toHaveLength(0);
  });

  it("clears feedback targets on restartCore and does not send stale user_feedback", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate({ id: "sig-A" })]);
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).toContain("sig-A");
    await harness.controller.restartCore();
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).not.toContain(
      "sig-A",
    );
    await harness.controller.submitSignalFeedback("sig-A", "useful");
    const sent = (harness.commands as Array<{ type?: string; signal_id?: string }>).filter(
      (item) => item.type === "user_feedback",
    );
    expect(sent).toHaveLength(0);
    expect(harness.lines.some((line) => line.includes("stale"))).toBe(true);
  });

  it("clears presented feedback targets on unexpected disconnect", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate({ id: "sig-A" })]);
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).toContain("sig-A");
    harness.children[0]?.emit("exit", 1, null);
    await vi.waitFor(() => {
      expect(harness.controller.actualState).toBe("RUNNING");
      expect(harness.managers.length).toBe(2);
    });
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).not.toContain(
      "sig-A",
    );
  });

  it("clears feedback targets on shutdown", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate({ id: "sig-A" })]);
    await harness.controller.shutdown();
    expect(harness.controller.signalFeedbackTargets()).toEqual([]);
  });

  it("keeps same-run presented targets after the signal is no longer active", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate({ id: "sig-A" })]);
    writeState(harness.children[0], {
      watchlist_count: 1,
      feed_status: "LIVE",
      symbols: [wireSymbol({ active_signals: [] })],
    });
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).toContain("sig-A");
    await harness.controller.submitSignalFeedback("sig-A", "too_noisy");
    await vi.waitFor(() => {
      const sent = (harness.commands as Array<{ type?: string; signal_id?: string }>).filter(
        (item) => item.type === "user_feedback" && item.signal_id === "sig-A",
      );
      expect(sent).toHaveLength(1);
    });
  });

  it("does not clear feedback targets on pause and resume of the same Core", async () => {
    const harness = createHarness();
    await harness.controller.start();
    writeAlert(harness.children[0], [alertCandidate({ id: "sig-A" })]);
    await harness.controller.pause();
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).toContain("sig-A");
    await harness.controller.resume();
    expect(harness.controller.signalFeedbackTargets().map((item) => item.id)).toContain("sig-A");
    expect(harness.spawned).toHaveLength(1);
    await harness.controller.submitSignalFeedback("sig-A", "useful");
    await vi.waitFor(() => {
      const sent = (harness.commands as Array<{ type?: string }>).filter(
        (item) => item.type === "user_feedback",
      );
      expect(sent).toHaveLength(1);
    });
  });
});
