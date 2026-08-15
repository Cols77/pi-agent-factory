import { describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  hasCodeIndex,
  indexMarkerPath,
  shouldInject,
} from "../src/code-context-inject.js";

describe("code-context-inject", () => {
  it("indexMarkerPath points under .factory/code-index", () => {
    const normalized = indexMarkerPath("C:/proj").split("\\").join("/");
    expect(normalized).toBe("C:/proj/.factory/code-index/latest.json");
  });

  it("hasCodeIndex is false without a marker, true with one", () => {
    const root = mkdtempSync(join(tmpdir(), "cci-"));
    expect(hasCodeIndex(root)).toBe(false);
    const dir = join(root, ".factory", "code-index");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "latest.json"), "{}", "utf-8");
    expect(hasCodeIndex(root)).toBe(true);
  });

  it("shouldInject injects once per (root, sessionId) and never again", () => {
    const collected = new Set<string>();
    expect(shouldInject(collected, "C:/a", "s1")).toBe(true);
    expect(shouldInject(collected, "C:/a", "s1")).toBe(false); // same session
    expect(shouldInject(collected, "C:/a", "s2")).toBe(true); // new session
    expect(shouldInject(collected, "C:/b", "s1")).toBe(true); // new project
  });

  it("shouldInject refuses to gate without a session id or root", () => {
    const collected = new Set<string>();
    expect(shouldInject(collected, "", "s1")).toBe(false);
    expect(shouldInject(collected, "C:/a", undefined)).toBe(false);
    expect(collected.size).toBe(0);
  });
});