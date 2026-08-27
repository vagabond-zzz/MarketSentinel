import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

describe("extension manifest", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), "package.json"), "utf8")) as {
    activationEvents: string[];
    contributes: { commands: Array<{ command: string }>; configuration: unknown };
    capabilities: { untrustedWorkspaces: { supported: boolean; description: string } };
  };

  it("activates onStartupFinished and explicit commands, never *", () => {
    expect(pkg.activationEvents).toContain("onStartupFinished");
    expect(pkg.activationEvents).toContain("onCommand:marketSentinel.pause");
    expect(pkg.activationEvents).toContain("onCommand:marketSentinel.resume");
    expect(pkg.activationEvents).toContain("onCommand:marketSentinel.restartCore");
    expect(pkg.activationEvents).toContain("onCommand:marketSentinel.showOutput");
    expect(pkg.activationEvents).not.toContain("*");
  });

  it("does not register StatusBar or resetAlertBadge", () => {
    const ids = pkg.contributes.commands.map((item) => item.command);
    expect(ids).toEqual([
      "marketSentinel.pause",
      "marketSentinel.resume",
      "marketSentinel.restartCore",
      "marketSentinel.showOutput",
    ]);
    expect(JSON.stringify(pkg.contributes)).not.toContain("statusBar");
    expect(ids).not.toContain("marketSentinel.resetAlertBadge");
  });

  it("defaults enableHoverDetails to true as a host-only setting", () => {
    const properties = (
      pkg.contributes.configuration as {
        properties: Record<string, { type: string; default: unknown }>;
      }
    ).properties;
    expect(properties["marketSentinel.enableHoverDetails"]).toEqual(
      expect.objectContaining({ type: "boolean", default: true }),
    );
  });

  it("requires a trusted workspace because it spawns a local Python Core", () => {
    expect(pkg.capabilities.untrustedWorkspaces.supported).toBe(false);
    expect(pkg.capabilities.untrustedWorkspaces.description).toMatch(/Python Core/);
  });
});
