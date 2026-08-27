import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export function findRepoRoot(): string {
  let dir = process.cwd();
  for (;;) {
    if (
      fs.existsSync(path.join(dir, "pyproject.toml")) &&
      fs.existsSync(path.join(dir, "src", "market_sentinel"))
    ) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      throw new Error("cannot find Market Sentinel repo root");
    }
    dir = parent;
  }
}

export function resolveUv(): string | undefined {
  const probe = spawnSync("uv", ["--version"], { encoding: "utf8", shell: false });
  if (probe.status === 0) {
    return "uv";
  }
  if (process.platform === "win32") {
    const located = spawnSync("where.exe", ["uv"], { encoding: "utf8", shell: false });
    const line = located.stdout
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find((item) => item.toLowerCase().endsWith(".exe"));
    if (line !== undefined && line.length > 0) {
      return line;
    }
  }
  return undefined;
}

export function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function stderrLooksLikeJsonl(chunks: readonly string[]): boolean {
  for (const chunk of chunks) {
    for (const line of chunk.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (trimmed.startsWith("{") && trimmed.includes("protocol_version")) {
        return true;
      }
    }
  }
  return false;
}
