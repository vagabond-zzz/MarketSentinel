import { describe, expect, it } from "vitest";

import { JsonlDecoder } from "./jsonl";

describe("JsonlDecoder", () => {
  it("decodes a complete line in one chunk", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push('{"a":1}\n')).toEqual(['{"a":1}']);
  });

  it("buffers a half line until the rest arrives", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push('{"a":')).toEqual([]);
    expect(decoder.push("1}\n")).toEqual(['{"a":1}']);
  });

  it("splits multiple lines in one chunk", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push('{"a":1}\n{"b":2}\n')).toEqual(['{"a":1}', '{"b":2}']);
  });

  it("does not emit a trailing line without newline", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push('{"a":1}')).toEqual([]);
  });

  it("strips CR from CRLF", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push('{"a":1}\r\n')).toEqual(['{"a":1}']);
  });

  it("ignores empty lines", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push("\n\n{\"a\":1}\n\n")).toEqual(['{"a":1}']);
  });

  it("ignores empty CRLF lines", () => {
    const decoder = new JsonlDecoder();
    expect(decoder.push("\r\n{\"a\":1}\r\n")).toEqual(['{"a":1}']);
  });
});
