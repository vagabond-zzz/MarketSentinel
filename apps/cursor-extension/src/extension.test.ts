import { afterEach, describe, expect, it } from "vitest";

import { activate, deactivate } from "./extension";
import { HOST_COMMANDS } from "./host/types";
import { resetVscodeMock, vscodeState } from "../vitest/vscode-mock";

describe("extension adapter", () => {
  afterEach(async () => {
    await deactivate();
    resetVscodeMock();
  });

  it("activates without a workspace, registers commands, and shuts down idempotently", async () => {
    const context = { subscriptions: [] as Array<{ dispose: () => void }> };
    await activate(context as never);
    expect(vscodeState.commands.has(HOST_COMMANDS.pause)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.resume)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.restartCore)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.showOutput)).toBe(true);
    expect(vscodeState.outputLines.some((line) => line.startsWith("[host]"))).toBe(true);
    await vscodeState.commands.get(HOST_COMMANDS.showOutput)?.();
    expect(vscodeState.outputShown).toBe(true);
    await deactivate();
    await deactivate();
  });
});
