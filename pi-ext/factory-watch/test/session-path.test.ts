import { mkdirSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { resolveSessionPath } from "../src/session-path.ts";

describe("resolveSessionPath", () => {
  test("finds the session file by uuid under any project subdir", () => {
    const root = mkdtempSync(join(tmpdir(), "sess-"));
    const proj = join(root, "--C--somewhere--");
    mkdirSync(proj, { recursive: true });
    const file = join(proj, "2026-07-23T00-00-00-000Z_abc-uuid-123.jsonl");
    writeFileSync(file, "{}\n");
    expect(resolveSessionPath("abc-uuid-123", root)).toBe(file);
  });

  test("returns null when no file matches", () => {
    const root = mkdtempSync(join(tmpdir(), "sess-"));
    expect(resolveSessionPath("nope", root)).toBeNull();
  });
});
