import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { renderMarkdown } from "../src/md-render.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

function docsIn(...parts: string[]): string[] {
  const dir = join(ROOT, ...parts);
  try {
    return readdirSync(dir).filter((f) => f.endsWith(".md")).map((f) => join(dir, f));
  } catch {
    return [];
  }
}

describe("md-render against the real corpus", () => {
  const files = [
    ...docsIn("docs", "superpowers", "specs"),
    ...docsIn("docs", "superpowers", "plans"),
    ...docsIn("tasks"),
  ];

  test("finds the corpus", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  test.each(files)("renders %s without throwing and emits no raw script tag", (file) => {
    const out = renderMarkdown(readFileSync(file, "utf-8"));
    expect(out.html).not.toContain("<script>");
  });
});
