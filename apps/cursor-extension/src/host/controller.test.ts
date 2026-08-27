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
    onStatusBar?: (model: { kind: string }) => void;
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
    onStatusBar: extras.onStatusBar,
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
      onStatusBar: (model) => {
        views.push(model.kind);
      },
    });
    await harness.controller.start();
    expect(harness.controller.statusBarModel().kind).toBe("STALE");

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
    expect(views).toContain("STALE");
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
});
