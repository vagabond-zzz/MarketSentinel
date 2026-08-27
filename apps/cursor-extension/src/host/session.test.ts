import { describe, expect, it } from "vitest";

import { HostController } from "./controller";
import { bindCommands, HOST_COMMANDS } from "./session";
import type { HostLogger } from "./types";

describe("bindCommands", () => {
  it("maps pause/resume/restartCore/showOutput", async () => {
    const logs: string[] = [];
    const logger: HostLogger = {
      host: (message) => logs.push(message),
      core: () => undefined,
    };
    const shown: string[] = [];
    const controller = new HostController({
      readSettings: () => ({}),
      workspaceFolders: () => [],
      logger,
    });
    const commands = bindCommands(controller, { show: () => shown.push("show") }, logger);
    await commands[HOST_COMMANDS.pause]?.();
    expect(controller.desiredState).toBe("PAUSED");
    await commands[HOST_COMMANDS.showOutput]?.();
    expect(shown).toEqual(["show"]);
    expect(commands[HOST_COMMANDS.resume]).toBeTypeOf("function");
    expect(commands[HOST_COMMANDS.restartCore]).toBeTypeOf("function");
    expect(commands[HOST_COMMANDS.resetAlertBadge]).toBeTypeOf("function");
    await commands[HOST_COMMANDS.resetAlertBadge]?.();
    expect(controller.unreadAlertCount).toBe(0);
  });
});
