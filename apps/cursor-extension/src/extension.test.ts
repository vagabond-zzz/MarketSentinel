import { describe, expect, it } from "vitest";

import { activate, deactivate } from "./extension";

describe("extension skeleton", () => {
  it("activates and deactivates without UI", () => {
    expect(() => activate()).not.toThrow();
    expect(() => deactivate()).not.toThrow();
  });
});
