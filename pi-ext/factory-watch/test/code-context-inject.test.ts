import { describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  composeCodeContextMessage,
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

describe("composeCodeContextMessage", () => {
  const slice = () => "### REFERENCE (indexed) src/a.py - L1 def f(): x";
  const rootWithIndex = (): string => {
    const root = mkdtempSync(join(tmpdir(), "cci2-"));
    const dir = join(root, ".factory", "code-index");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "latest.json"), "{}", "utf-8");
    return root;
  };

  it("injects a code-context message once per (root, sessionId)", () => {
    const root = rootWithIndex();
    const collected = new Set<string>();
    const first = composeCodeContextMessage(root, "s1", collected, slice);
    expect("message" in first).toBe(true);
    const msg = (first as { message: { customType: string; content: string } }).message;
    expect(msg.customType).toBe("factory-code-context");
    expect(msg.content).toContain("REFERENCE (indexed)");
    // second call: already injected for this session
    expect(composeCodeContextMessage(root, "s1", collected, slice)).toEqual({});
  });

  it("returns {} without an index marker", () => {
    const root = mkdtempSync(join(tmpdir(), "cci2-"));
    expect(composeCodeContextMessage(root, "s1", new Set(), slice)).toEqual({});
  });

  it("returns {} for an empty slice", () => {
    const root = rootWithIndex();
    expect(composeCodeContextMessage(root, "s1", new Set(), () => "")).toEqual({});
  });

  it("returns {} when the root is not a string (regression: object-vs-string bug)", () => {
    // resolveProjectRoot returns { root, method }; passing the object used to throw
    // ERR_INVALID_ARG_TYPE inside hasCodeIndex and abort the whole injection.
    const objectRoot = { root: "C:/proj", method: "git" };
    expect(() =>
      composeCodeContextMessage(objectRoot as unknown as string, "s1", new Set(), slice),
    ).not.toThrow();
    expect(composeCodeContextMessage(objectRoot as unknown as string, "s1", new Set(), slice)).toEqual({});
  });
});