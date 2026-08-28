import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const extRoot = path.resolve(here, "..");
const pkgPath = path.join(extRoot, "package.json");
const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
const version = typeof pkg.version === "string" ? pkg.version : "";
if (!version) {
  console.error("extension package.json is missing version");
  process.exit(1);
}
const vsixName = `market-sentinel-${version}.vsix`;
const vsixPath = path.join(extRoot, vsixName);

if (!fs.existsSync(vsixPath)) {
  console.error(`missing ${vsixPath}`);
  process.exit(1);
}

const listing = execFileSync("tar", ["-tf", vsixPath], { encoding: "utf8" });
const files = listing
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter((line) => line.length > 0);
const joined = files.join("\n");
const forbidden = [
  "node_modules/",
  ".venv/",
  "/src/",
  "vitest/",
  "Market_Sentinel.zip",
  ".git/",
  "tests/",
  "fixtures/",
];
for (const needle of forbidden) {
  if (joined.includes(needle)) {
    console.error(`VSIX contains forbidden path fragment: ${needle}`);
    process.exit(1);
  }
}
if (!files.some((file) => file === "extension/package.json" || file.endsWith("/package.json"))) {
  console.error("VSIX is missing package.json");
  process.exit(1);
}
if (!files.some((file) => file.endsWith("out/extension.js"))) {
  console.error("VSIX is missing out/extension.js");
  process.exit(1);
}

const bytes = fs.statSync(vsixPath).size;
console.log(`VSIX ${vsixName}`);
console.log(`files ${files.length}`);
console.log(`bytes ${bytes}`);
