import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { PROTOCOL_VERSION } from "../protocol/types";

describe("extension packaging manifest", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), "package.json"), "utf8")) as {
    name: string;
    version: string;
    publisher: string;
    main: string;
    private: boolean;
    extensionKind: string[];
    engines: { vscode: string };
    scripts: Record<string, string>;
  };

  it("has local VSIX identity fields without claiming a Marketplace publisher", () => {
    expect(pkg.name).toBe("market-sentinel");
    expect(pkg.version).toBe("0.6.5");
    expect(pkg.publisher).toBe("market-sentinel-local");
    expect(pkg.main).toBe("./out/extension.js");
    expect(pkg.engines.vscode).toBe("^1.90.0");
    expect(pkg.extensionKind).toEqual(["ui"]);
    expect(pkg.private).toBe(true);
    expect(pkg.scripts["vscode:prepublish"]).toContain("tsc");
    expect(pkg.scripts["package:vsix"]).toContain("vsce package");
    expect(PROTOCOL_VERSION).toBe(1);
    expect(pkg.version).not.toBe(String(PROTOCOL_VERSION));
  });

  it("derives the VSIX filename from package.json instead of a hardcoded version", () => {
    const script = fs.readFileSync(path.join(process.cwd(), "scripts", "audit-vsix.mjs"), "utf8");
    expect(script).toMatch(/package\.json/);
    expect(script).not.toMatch(/market-sentinel-0\.\d+\.\d+\.vsix/);
  });

  it("keeps a .vscodeignore that excludes sources, tests, and node_modules", () => {
    const ignore = fs.readFileSync(path.join(process.cwd(), ".vscodeignore"), "utf8");
    expect(ignore).toMatch(/^src\/\*\*/m);
    expect(ignore).toMatch(/^node_modules\/\*\*/m);
    expect(ignore).toContain("**/*.test.js");
    expect(ignore).toContain("**/*.test.ts");
    expect(ignore).toContain("vitest/**");
  });
});
