import { afterEach, describe, expect, it, vi } from "vitest";

import { activate, deactivate } from "./extension";
import { HOST_COMMANDS } from "./host/types";
import { MarkdownString, resetVscodeMock, vscodeState } from "../vitest/vscode-mock";

function tooltipMarkdown(): MarkdownString {
  const tooltip = vscodeState.statusBar.tooltip;
  expect(tooltip).toBeInstanceOf(MarkdownString);
  const markdown = tooltip as MarkdownString;
  expect(markdown.isTrusted).toBe(false);
  return markdown;
}

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
    expect(vscodeState.statusBar.shown).toBe(true);
    expect(vscodeState.statusBar.text).toContain("DISCONNECTED");
    expect(vscodeState.statusBar.command).toBe(HOST_COMMANDS.showOutput);
    expect(tooltipMarkdown().value).toContain("Core disconnected");
    await vscodeState.commands.get(HOST_COMMANDS.showOutput)?.();
    expect(vscodeState.outputShown).toBe(true);
    await deactivate();
    await deactivate();
  });

  it("updates StatusBar tooltip from HoverModel without trusting Markdown", async () => {
    const context = { subscriptions: [] as Array<{ dispose: () => void }> };
    await activate(context as never);
    const markdown = tooltipMarkdown();
    expect(markdown.value).toContain("Market Sentinel");
    expect(markdown.value).toContain("Click the StatusBar to view Output");
    expect(markdown.isTrusted).toBe(false);

    vscodeState.settings["marketSentinel.enableHoverDetails"] = false;
    vscodeState.configListeners[0]?.({
      affectsConfiguration: (key) => key === "marketSentinel.enableHoverDetails",
    });
    await vi.waitFor(() => {
      expect(tooltipMarkdown().value).toBe("Market Sentinel · Core disconnected");
    });
  });
});
