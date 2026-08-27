import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["out/**", "node_modules/**", ".vscode-test/**", "vitest.config.ts", "eslint.config.mjs", "vitest/**", "src/test/**", "scripts/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
