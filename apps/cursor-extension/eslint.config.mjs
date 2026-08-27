import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["out/**", "node_modules/**", "vitest.config.ts", "eslint.config.mjs"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
