import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { ProcessManager } from "./process";

function findRepoRoot(): string {
  let dir = process.cwd();
  for (;;) {
    if (
      fs.existsSync(path.join(dir, "pyproject.toml")) &&
      fs.existsSync(path.join(dir, "src", "market_sentinel"))
    ) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      throw new Error("cannot find Market Sentinel repo root");
    }
    dir = parent;
  }
}

function resolveUv(): string | undefined {
  const probe = spawnSync("uv", ["--version"], { encoding: "utf8", shell: false });
  if (probe.status === 0) {
    return "uv";
  }
  if (process.platform === "win32") {
    const located = spawnSync("where.exe", ["uv"], { encoding: "utf8", shell: false });
    const line = located.stdout
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find((item) => item.toLowerCase().endsWith(".exe"));
    if (line !== undefined && line.length > 0) {
      return line;
    }
  }
  return undefined;
}

const uvPath = resolveUv();

describe("Python ↔ Node IPC", () => {
  it.skipIf(uvPath === undefined)(
    "hello → set_watchlist → start → get_state → shutdown",
    async () => {
      const stderr: string[] = [];
      const types: string[] = [];
      const manager = new ProcessManager({
        uvPath,
        coreRoot: findRepoRoot(),
        provider: "fake",
        helloTimeoutMs: 20_000,
        defaultTimeoutMs: 10_000,
        shutdownGraceMs: 5_000,
        onStderr: (chunk) => {
          stderr.push(chunk);
        },
        onState: () => {
          types.push("state");
        },
        onAlert: () => {
          types.push("alert");
        },
      });
      try {
        await manager.start([{ symbol: "00700.HK", enabled: true }]);
        const snapshot = await manager.getState();
        expect(snapshot.type).toBe("state");
        expect(snapshot.protocol_version).toBe(1);
        expect(snapshot.request_id).toBeDefined();
        expect(snapshot.state.watchlist_count).toBe(1);
        expect(snapshot.state.symbols[0]?.symbol).toBe("00700.HK");
        expect(snapshot.state.symbols[0]?.scheduler_level).toMatch(/^(COLD|WARM|HOT)$/);
        expect(snapshot.state.symbols[0]?.active_signals).toEqual([]);
        await manager.pause();
        await manager.resume();
        await manager.shutdown();
        expect(manager.phase).toBe("STOPPED");
      } catch (error) {
        await manager.shutdown().catch(() => undefined);
        throw new Error(`${String(error)}\nstderr:\n${stderr.join("")}`);
      }
    },
    30_000,
  );
});
