import { describe, expect, it } from "vitest";

import { ProcessManager } from "./process";
import { findRepoRoot, processExists, resolveUv, stderrLooksLikeJsonl } from "../integration/env";

const uvPath = resolveUv();

describe("Python ↔ Node IPC", () => {
  it.skipIf(uvPath === undefined)(
    "hello → set_watchlist → start → state → pause → resume → get_state → shutdown",
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
        expect(manager.phase).toBe("RUNNING");
        const first = await manager.getState();
        expect(first.type).toBe("state");
        expect(first.protocol_version).toBe(1);
        expect(first.request_id).toBeDefined();
        expect(first.state.watchlist_count).toBe(1);
        expect(first.state.symbols[0]?.symbol).toBe("00700.HK");
        expect(first.state.symbols[0]?.scheduler_level).toMatch(/^(COLD|WARM|HOT)$/);
        await manager.pause();
        await manager.resume();
        const second = await manager.getState();
        expect(second.type).toBe("state");
        expect(second.protocol_version).toBe(1);
        const pid = manager.lastPid;
        expect(pid).toBeDefined();
        expect(manager.ipc?.pendingCount).toBe(0);
        await manager.shutdown();
        expect(manager.phase).toBe("STOPPED");
        expect(manager.ipc).toBeUndefined();
        expect(stderrLooksLikeJsonl(stderr)).toBe(false);
        if (pid !== undefined) {
          expect(processExists(pid)).toBe(false);
        }
      } catch (error) {
        await manager.shutdown().catch(() => undefined);
        throw new Error(`${String(error)}\nstderr:\n${stderr.join("")}`);
      }
    },
    30_000,
  );
});
