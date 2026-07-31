import { describe, expect, test } from "vitest";
import { isPidAlive, parseLock } from "../src/lock-status.js";

describe("parseLock", () => {
  test("parses a valid lock record", () => {
    const raw = JSON.stringify({ pid: 12345, started_at: "2026-07-20T10:00:00Z" });
    expect(parseLock(raw)).toEqual({ pid: 12345, started_at: "2026-07-20T10:00:00Z" });
  });
  test("returns null for malformed JSON", () => {
    expect(parseLock("not json")).toBeNull();
  });
  test("returns null when pid is missing or not a number", () => {
    expect(parseLock('{"started_at": "x"}')).toBeNull();
    expect(parseLock('{"pid": "12345", "started_at": "x"}')).toBeNull();
  });
});

describe("isPidAlive", () => {
  test("is true for the current process", () => {
    expect(isPidAlive(process.pid)).toBe(true);
  });
  test("is false for an implausible pid", () => {
    expect(isPidAlive(999_999_999)).toBe(false);
  });
});
