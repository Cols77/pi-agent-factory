import { describe, expect, test } from "vitest";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readContextPacket, renderPacketSlice, contextPacketPath } from "../src/context-packet.js";

function writePacket(cwd: string, sessionId: string): string {
  const dir = join(cwd, "sessions", ".factory-transcripts", sessionId);
  mkdirSync(dir, { recursive: true });
  const p = contextPacketPath(cwd, sessionId);
  writeFileSync(
    p,
    JSON.stringify({
      task_id: "T-001",
      primary_files: ["src/mod.py"],
      reference_files: ["src/lib.py"],
      files: {
        "src/lib.py": {
          primary: false,
          kind: "signatures",
          content: null,
          signatures: [{ kind: "function", name: "alpha", signature: "def alpha(a, b)", line: 3, summary: "Returns a+b." }],
        },
        "src/mod.py": { primary: true, kind: "content", content: "def alpha(a, b):\n    return a + b\n", signatures: [] },
      },
      missing: [],
      truncated: false,
    }),
    "utf-8",
  );
  return p;
}

describe("readContextPacket", () => {
  test("reads a persisted packet; returns null when absent", () => {
    const cwd = mkdtempSync(join(tmpdir(), "ctxpkt-"));
    expect(readContextPacket(cwd, "missing-sess")).toBeNull();
    const p = writePacket(cwd, "s1");
    const packet = readContextPacket(cwd, "s1");
    expect(packet).not.toBeNull();
    expect(packet!.primary_files).toEqual(["src/mod.py"]);
    expect(packet!.files?.["src/mod.py"]).toBeDefined();
  });
});

describe("renderPacketSlice", () => {
  test("renders primary content and reference signatures deterministically", () => {
    const packet = {
      primary_files: ["src/mod.py"],
      reference_files: ["src/lib.py"],
      files: {
        "src/lib.py": { primary: false, kind: "signatures", content: null, signatures: [{ kind: "function", name: "alpha", signature: "def alpha(a, b)", line: 3, summary: "Returns a+b." }] },
        "src/mod.py": { primary: true, kind: "content", content: "def alpha(a, b):\n    return a + b\n", signatures: [] },
      },
      missing: [],
      truncated: false,
    };
    const out = renderPacketSlice(packet);
    expect(out).toContain("## Context packet");
    expect(out).toContain("PRIMARY — src/mod.py");
    expect(out).toContain("def alpha(a, b)");
    expect(out).toContain("L3 def alpha(a, b) — Returns a+b.");
  });

  test("bounds output to the char cap", () => {
    const packet = {
      primary_files: ["big.py"],
      reference_files: [],
      files: { "big.py": { primary: true, kind: "content", content: "y\n".repeat(200000), signatures: [] } },
      missing: [],
      truncated: false,
    };
    const out = renderPacketSlice(packet, 200);
    expect(out.length).toBeLessThanOrEqual(400);
  });
});
