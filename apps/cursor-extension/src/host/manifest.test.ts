import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

describe("extension manifest", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), "package.json"), "utf8")) as {
    activationEvents: string[];
    contributes: { commands: Array<{ command: string }>; configuration: unknown };
    capabilities: { untrustedWorkspaces: { supported: boolean; description: string } };
  };

  it("activates onStartupFinished and never *", () => {
    expect(pkg.activationEvents).toEqual(["onStartupFinished"]);
    expect(pkg.activationEvents).not.toContain("*");
  });

  it("contributes host commands without a StatusBar contribution or * activation", () => {
    const ids = pkg.contributes.commands.map((item) => item.command);
    expect(ids).toEqual([
      "marketSentinel.pause",
      "marketSentinel.resume",
      "marketSentinel.restartCore",
      "marketSentinel.showOutput",
      "marketSentinel.resetAlertBadge",
    ]);
    expect(JSON.stringify(pkg.contributes)).not.toContain("statusBar");
    expect(pkg.activationEvents).toEqual(["onStartupFinished"]);
  });

  it("defaults enableHoverDetails to true and alertToast to off as host-only settings", () => {
    const properties = (
      pkg.contributes.configuration as {
        properties: Record<string, { type: string; default: unknown; enum?: string[] }>;
      }
    ).properties;
    expect(properties["marketSentinel.enableHoverDetails"]).toEqual(
      expect.objectContaining({ type: "boolean", default: true }),
    );
    expect(properties["marketSentinel.alertToast"]).toEqual(
      expect.objectContaining({ type: "string", default: "off", enum: ["off", "critical"] }),
    );
  });

  it("requires a trusted workspace because it spawns a local Python Core", () => {
    expect(pkg.capabilities.untrustedWorkspaces.supported).toBe(false);
    expect(pkg.capabilities.untrustedWorkspaces.description).toMatch(/Python Core/);
  });
});
