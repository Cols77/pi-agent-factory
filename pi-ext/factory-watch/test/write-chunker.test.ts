import { describe, expect, test } from "vitest";
import { splitContent, WRITE_CHUNK_THRESHOLD_CHARS } from "../src/write-chunker.js";

describe("splitContent", () => {
  test("splits content into equal-size chunks with a shorter final chunk", () => {
    expect(splitContent("abcdefghij", 4)).toEqual(["abcd", "efgh", "ij"]);
  });

  test("returns a single chunk when content is shorter than chunkSize", () => {
    expect(splitContent("abc", 100)).toEqual(["abc"]);
  });

  test("returns a single empty chunk for empty content", () => {
    expect(splitContent("", 100)).toEqual([""]);
  });

  test("throws for a non-positive chunkSize", () => {
    expect(() => splitContent("abc", 0)).toThrow("chunkSize must be positive");
    expect(() => splitContent("abc", -1)).toThrow("chunkSize must be positive");
  });

  test("WRITE_CHUNK_THRESHOLD_CHARS is a positive constant", () => {
    expect(WRITE_CHUNK_THRESHOLD_CHARS).toBeGreaterThan(0);
  });
});
