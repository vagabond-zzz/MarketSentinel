import { describe, expect, it } from "vitest";

import { findRepoRoot, processExists, resolveUv } from "../integration/env";
import { HostController } from "./controller";
import type { HostLogger } from "./types";

const uvPath = resolveUv();

function createLogger(): HostLogger {
  return {
    host: () => undefined,
    core: () => undefined,
  };
}

describe("HostController ↔ Python daemon", () => {
  it.skipIf(uvPath === undefined)(
    "hello → set_watchlist → start → pause → resume → shutdown",
    async () => {
      const repo = findRepoRoot();
      const controller = new HostController({
        readSettings: () => ({
          coreRoot: repo,
          uvPath,
          watchlist: [{ symbol: "00700.HK", enabled: true }],
          provider: "fake",
        }),
        workspaceFolders: () => [repo],
        logger: createLogger(),
        helloTimeoutMs: 20_000,
        defaultTimeoutMs: 10_000,
      });
      try {
        await controller.start();
        expect(controller.actualState).toBe("RUNNING");
        const pid = controller.lastPid;
        await controller.pause();
        expect(controller.actualState).toBe("PAUSED");
        await controller.resume();
        expect(controller.actualState).toBe("RUNNING");
        await controller.shutdown();
        expect(controller.actualState).toBe("STOPPED");
        if (pid !== undefined) {
          expect(processExists(pid)).toBe(false);
        }
      } catch (error) {
        await controller.shutdown().catch(() => undefined);
        throw error;
      }
    },
    40_000,
  );
});
