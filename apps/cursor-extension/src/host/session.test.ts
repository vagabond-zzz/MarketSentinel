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
    expect(commands[HOST_COMMANDS.submitSignalFeedback]).toBeTypeOf("function");
    expect(commands[HOST_COMMANDS.addSymbol]).toBeTypeOf("function");
    expect(commands[HOST_COMMANDS.removeSymbol]).toBeTypeOf("function");
    expect(commands[HOST_COMMANDS.manageWatchlist]).toBeTypeOf("function");
    await commands[HOST_COMMANDS.resetAlertBadge]?.();
    expect(controller.unreadAlertCount).toBe(0);
  });

  it("adds a symbol from the command prompt and persists watchlist identity", async () => {
    const persisted: string[][] = [];
    const controller = new HostController({
      readSettings: () => ({ watchlist: [] }),
      workspaceFolders: () => ["D:/repo"],
      logger: { host: () => undefined, core: () => undefined },
      persistWatchlist: async (items) => {
        persisted.push(items.map((item) => item.symbol));
      },
    });
    const commands = bindCommands(
      controller,
      { show: () => undefined },
      { host: () => undefined, core: () => undefined },
      undefined,
      {
        inputSymbol: async () => "600519.SH",
        pickSymbol: async () => undefined,
        pickManageAction: async () => undefined,
      },
    );
    await commands[HOST_COMMANDS.addSymbol]?.();
    expect(persisted).toEqual([["600519.SH"]]);
  });

  it("only sends user_feedback after explicit QuickPick choices", async () => {
    const logs: string[] = [];
    const logger: HostLogger = {
      host: (message) => logs.push(message),
      core: () => undefined,
    };
    const sent: Array<{ signalId: string; feedbackType: string }> = [];
    const controller = {
      signalFeedbackTargets: () => [{ id: "sig-1", label: "00700.HK alert" }],
      submitSignalFeedback: async (signalId: string, feedbackType: string) => {
        sent.push({ signalId, feedbackType });
      },
    };
    const commands = bindCommands(
      controller as never,
      { show: () => undefined },
      logger,
      {
        pickSignal: async (items) => items[0],
        pickLabel: async (items) => items.find((item) => item.value === "too_noisy"),
      },
    );
    await commands[HOST_COMMANDS.submitSignalFeedback]?.();
    expect(sent).toEqual([{ signalId: "sig-1", feedbackType: "too_noisy" }]);
  });

  it("does not send feedback when the user cancels QuickPick", async () => {
    const sent: unknown[] = [];
    const controller = {
      signalFeedbackTargets: () => [{ id: "sig-1", label: "00700.HK alert" }],
      submitSignalFeedback: async (signalId: string, feedbackType: string) => {
        sent.push({ signalId, feedbackType });
      },
    };
    const commands = bindCommands(
      controller as never,
      { show: () => undefined },
      {
        host: () => undefined,
        core: () => undefined,
      },
      {
        pickSignal: async () => undefined,
        pickLabel: async () => ({ label: "有用", value: "useful" as const }),
      },
    );
    await commands[HOST_COMMANDS.submitSignalFeedback]?.();
    expect(sent).toEqual([]);
  });
});
