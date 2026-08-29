import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import type { ChildProcess, SpawnOptions } from "node:child_process";

import { describe, expect, it, vi } from "vitest";

import type { WatchlistItem } from "../protocol/types";
import { IpcDisconnectedError, ProtocolError } from "./errors";
import { JsonlDecoder } from "./jsonl";
import { ProcessManager, type ProcessManagerOptions } from "./process";

class FakeChild extends EventEmitter {
  stdin = new PassThrough();
  stdout = new PassThrough();
  stderr = new PassThrough();
  exitCode: number | null = null;
  killed = false;
  kill = vi.fn(() => {
    this.killed = true;
    this.exitCode = 1;
    this.emit("exit", 1, null);
    return true;
  });
}

function asChild(child: FakeChild): ChildProcess {
  return child as unknown as ChildProcess;
}

function scriptDaemon(child: FakeChild, log: unknown[]): void {
  const decoder = new JsonlDecoder();
  child.stdin.on("data", (chunk: Buffer | string) => {
    for (const line of decoder.push(chunk)) {
      const command = JSON.parse(line) as {
        type: string;
        request_id: string;
        items?: WatchlistItem[];
      };
      log.push(command);
      if (command.type === "hello") {
        child.stdout.write(
          JSON.stringify({
            protocol_version: 1,
            type: "ready",
            request_id: command.request_id,
            core_version: "0.2.0",
          }) + "\n",
        );
      } else if (command.type === "set_watchlist") {
        const items = command.items ?? [];
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

function managerWith(
  onChild?: (child: FakeChild) => void,
  extras: Partial<ProcessManagerOptions> = {},
) {
  const children: FakeChild[] = [];
  const commands: unknown[] = [];
  const spawned: { command: string; args: string[]; options: SpawnOptions }[] = [];
  const manager = new ProcessManager({
    coreRoot: "D:/repo",
    uvPath: "uv",
    helloTimeoutMs: 200,
    defaultTimeoutMs: 200,
    spawnFn: (command, args, options) => {
      spawned.push({ command, args: [...args], options });
      const child = new FakeChild();
      children.push(child);
      onChild?.(child);
      scriptDaemon(child, commands);
      return asChild(child);
    },
    ...extras,
  });
  return { manager, children, commands, spawned };
}

describe("ProcessManager", () => {
  it("spawns uv with argv array and shell false", async () => {
    const { manager, spawned } = managerWith();
    await manager.start([]);
    expect(spawned[0]?.command).toBe("uv");
    expect(spawned[0]?.args).toEqual([
      "run",
      "--directory",
      "D:/repo",
      "market-sentinel",
      "--provider",
      "fake",
      "daemon",
    ]);
    expect(spawned[0]?.options.shell).toBe(false);
  });

  it("passes explicit intelligence CLI flags and omits them on inherit", async () => {
    const on = managerWith(undefined, { intelligence: "on" });
    await on.manager.start([]);
    expect(on.spawned[0]?.args).toContain("--intelligence");
    const off = managerWith(undefined, { intelligence: "off" });
    await off.manager.start([]);
    expect(off.spawned[0]?.args).toContain("--no-intelligence");
    const inherit = managerWith(undefined, { intelligence: "inherit" });
    await inherit.manager.start([]);
    expect(inherit.spawned[0]?.args).not.toContain("--intelligence");
    expect(inherit.spawned[0]?.args).not.toContain("--no-intelligence");
    const unset = managerWith();
    await unset.manager.start([]);
    expect(unset.spawned[0]?.args).not.toContain("--intelligence");
    expect(unset.spawned[0]?.args).not.toContain("--no-intelligence");
  });

  it("spawns longbridge provider without secrets on argv", async () => {
    const { manager, spawned } = managerWith(undefined, { provider: "longbridge" });
    await manager.start([]);
    expect(spawned[0]?.args).toEqual([
      "run",
      "--directory",
      "D:/repo",
      "market-sentinel",
      "--provider",
      "longbridge",
      "daemon",
    ]);
    expect(spawned[0]?.args).not.toContain("--extra");
    expect(spawned[0]?.args.join(" ")).not.toMatch(/extra live/);
    expect(spawned[0]?.args.join(" ")).not.toMatch(/LONGBRIDGE_/);
    expect(JSON.stringify(spawned[0]?.options.env ?? {})).not.toMatch(/LONGBRIDGE_/);
  });

  it("sends hello then set_watchlist then start", async () => {
    const { manager, commands } = managerWith();
    await manager.start([{ symbol: "00700.HK", enabled: true }]);
    expect(commands.map((item) => (item as { type: string }).type)).toEqual([
      "hello",
      "set_watchlist",
      "start",
    ]);
    expect((commands[0] as { host_version: string }).host_version).toBe("0.6.0");
    expect(manager.phase).toBe("RUNNING");
  });

  it("allows an empty watchlist", async () => {
    const { manager, commands } = managerWith();
    await manager.start([]);
    const setWatch = commands[1] as { type: string; items: unknown[] };
    expect(setWatch.items).toEqual([]);
  });

  it("rejects when Core reports watchlist_full", async () => {
    const { manager } = managerWith();
    const items = Array.from({ length: 11 }, (_, index) => ({
      symbol: `S${index}.HK`,
      enabled: true,
    }));
    await expect(manager.start(items)).rejects.toMatchObject({ code: "watchlist_full" });
    expect(manager.phase).toBe("DISCONNECTED");
  });

  it("updates watchlist only after ack", async () => {
    const { manager } = managerWith();
    await manager.start([{ symbol: "AAA.HK", enabled: true }]);
    await manager.setWatchlist([{ symbol: "BBB.HK", enabled: true }]);
    expect(manager.acknowledgedWatchlist).toEqual([{ symbol: "BBB.HK", enabled: true }]);
  });

  it("keeps last acknowledged watchlist when setWatchlist fails", async () => {
    const { manager } = managerWith();
    await manager.start([{ symbol: "AAA.HK", enabled: true }]);
    const tooMany = Array.from({ length: 11 }, (_, index) => ({
      symbol: `S${index}.HK`,
      enabled: true,
    }));
    await expect(manager.setWatchlist(tooMany)).rejects.toBeInstanceOf(ProtocolError);
    expect(manager.acknowledgedWatchlist).toEqual([{ symbol: "AAA.HK", enabled: true }]);
  });

  it("gracefully shuts down after shutdown_ack", async () => {
    const { manager, children } = managerWith();
    await manager.start([]);
    await manager.shutdown();
    expect(manager.phase).toBe("STOPPED");
    expect(children[0]?.kill).not.toHaveBeenCalled();
  });

  it("is idempotent when the child is already gone", async () => {
    const manager = new ProcessManager({ coreRoot: "D:/repo" });
    await manager.shutdown();
    await manager.shutdown();
    expect(manager.phase).toBe("STOPPED");
  });

  it("kills the child if shutdown times out", async () => {
    const { manager, children } = managerWith(undefined, {
      delay: async () => undefined,
      shutdownGraceMs: 5,
    });
    await manager.start([]);
    children[0]?.stdin.removeAllListeners("data");
    await manager.shutdown();
    expect(children[0]?.kill).toHaveBeenCalled();
    expect(manager.phase).toBe("STOPPED");
  });

  it("rejects pending requests when the child exits", async () => {
    const { manager, children } = managerWith();
    await manager.start([]);
    children[0]?.stdin.removeAllListeners("data");
    const pending = manager.getState();
    children[0]?.emit("exit", 1, null);
    await expect(pending).rejects.toBeInstanceOf(IpcDisconnectedError);
    expect(manager.phase).toBe("DISCONNECTED");
  });

  it("rejects pending requests when stdout closes", async () => {
    const { manager, children } = managerWith();
    await manager.start([]);
    children[0]?.stdin.removeAllListeners("data");
    const pending = manager.getState();
    children[0]?.stdout.end();
    await expect(pending).rejects.toBeInstanceOf(IpcDisconnectedError);
    expect(manager.phase).toBe("DISCONNECTED");
  });

  it("restartOnce uses a new client; old request ids cannot resolve it", async () => {
    const children: FakeChild[] = [];
    const ids: string[] = [];
    const protocolErrors: { code: string; requestId?: string }[] = [];
    let generation = 0;
    const manager = new ProcessManager({
      coreRoot: "D:/repo",
      helloTimeoutMs: 500,
      defaultTimeoutMs: 500,
      requestId: () => {
        const id = `id-${ids.length}`;
        ids.push(id);
        return id;
      },
      onProtocolError: (error) => protocolErrors.push(error),
      spawnFn: () => {
        generation += 1;
        const child = new FakeChild();
        children.push(child);
        scriptDaemon(child, []);
        return asChild(child);
      },
    });
    await manager.start([{ symbol: "00700.HK", enabled: true }]);
    const firstClient = manager.ipc;
    children[0]?.stdin.removeAllListeners("data");
    const stale = manager.getState();
    const staleId = ids[ids.length - 1];
    children[0]?.emit("exit", 1, null);
    await expect(stale).rejects.toBeInstanceOf(IpcDisconnectedError);
    expect(firstClient).toBeDefined();

    await manager.restartOnce();
    expect(generation).toBe(2);
    expect(manager.ipc).not.toBe(firstClient);
    expect(manager.phase).toBe("RUNNING");
    expect(manager.acknowledgedWatchlist).toEqual([{ symbol: "00700.HK", enabled: true }]);

    children[1]?.stdout.write(
      JSON.stringify({
        protocol_version: 1,
        type: "state",
        request_id: staleId,
        state: { watchlist_count: 0, feed_status: "DISCONNECTED", symbols: [] },
      }) + "\n",
    );
    await Promise.resolve();
    expect(protocolErrors.some((item) => item.code === "unknown_request_id")).toBe(true);
    await expect(stale).rejects.toBeInstanceOf(IpcDisconnectedError);
  });

  it("never feeds stderr into the JSONL decoder", async () => {
    const stderrChunks: string[] = [];
    const states: unknown[] = [];
    const { manager, children } = managerWith(undefined, {
      onStderr: (chunk) => stderrChunks.push(chunk),
      onState: (message) => states.push(message),
    });
    await manager.start([]);
    children[0]?.stderr.write('{"protocol_version":1,"type":"state"}\n');
    await Promise.resolve();
    expect(stderrChunks.join("")).toContain("protocol_version");
    expect(states).toHaveLength(0);
  });
});
