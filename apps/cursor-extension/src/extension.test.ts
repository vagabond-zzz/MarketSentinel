import { afterEach, describe, expect, it, vi } from "vitest";

import { activate, deactivate, presentHostAlertToast } from "./extension";
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
    expect(vscodeState.commands.has(HOST_COMMANDS.showDetails)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.resetAlertBadge)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.submitSignalFeedback)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.addSymbol)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.removeSymbol)).toBe(true);
    expect(vscodeState.commands.has(HOST_COMMANDS.manageWatchlist)).toBe(true);
    expect(vscodeState.outputLines.some((line) => line.startsWith("[host]"))).toBe(true);
    expect(vscodeState.statusBar.shown).toBe(true);
    expect(vscodeState.statusBar.text).toContain("$(error)");
    expect(vscodeState.statusBar.command).toBe(HOST_COMMANDS.showDetails);
    expect(tooltipMarkdown().value).toContain("Core disconnected");
    await vscodeState.commands.get(HOST_COMMANDS.showOutput)?.();
    expect(vscodeState.outputShown).toBe(true);
    await vscodeState.commands.get(HOST_COMMANDS.showDetails)?.();
    expect(vscodeState.detailsPanel.shown).toBe(true);
    expect(vscodeState.detailsPanel.viewType).toBe("marketSentinel.details");
    expect(vscodeState.detailsPanel.title).toContain("行情详情");
    expect(vscodeState.detailsPanel.html).toContain("Market Sentinel · 行情详情");
    const messagesBefore = vscodeState.detailsPanel.messages.length;
    vscodeState.settings["marketSentinel.symbolDisplay"] = "code";
    vscodeState.configListeners[0]?.({
      affectsConfiguration: (key) => key === "marketSentinel.symbolDisplay",
    });
    await vi.waitFor(() => {
      expect(vscodeState.detailsPanel.messages.length).toBeGreaterThan(messagesBefore);
    });
    await deactivate();
    await deactivate();
  });

  it("updates StatusBar tooltip from HoverModel without trusting Markdown", async () => {
    const context = { subscriptions: [] as Array<{ dispose: () => void }> };
    await activate(context as never);
    const markdown = tooltipMarkdown();
    expect(markdown.value).toContain("Market Sentinel");
    expect(markdown.value).toContain("点击状态栏打开行情详情面板");
    expect(markdown.isTrusted).toBe(false);

    vscodeState.settings["marketSentinel.enableHoverDetails"] = false;
    vscodeState.configListeners[0]?.({
      affectsConfiguration: (key) => key === "marketSentinel.enableHoverDetails",
    });
    await vi.waitFor(() => {
      expect(tooltipMarkdown().value).toBe("Market Sentinel · Core disconnected");
    });
  });

  it("toasts at most one critical alert edge and never for important or off", () => {
    const critical = {
      protocol_version: 1 as const,
      type: "alert" as const,
      candidates: [
        {
          id: "c1",
          symbol: "00700.HK",
          family: "tape",
          direction: "up" as const,
          priority: "critical" as const,
          title: "first",
          summary: "s",
        },
        {
          id: "c2",
          symbol: "00700.HK",
          family: "tape",
          direction: "up" as const,
          priority: "critical" as const,
          title: "second",
          summary: "s",
        },
      ],
      market_timestamp: 1,
    };
    presentHostAlertToast(critical, "off");
    expect(vscodeState.toasts).toEqual([]);
    const important = critical.candidates[0];
    if (important === undefined) {
      throw new Error("expected a candidate");
    }
    presentHostAlertToast(
      {
        ...critical,
        candidates: [{ ...important, priority: "important", title: "nope" }],
      },
      "critical",
    );
    expect(vscodeState.toasts).toEqual([]);
    presentHostAlertToast(critical, "critical");
    expect(vscodeState.toasts).toEqual(["Market Sentinel: first (+1 more)"]);
  });
});
