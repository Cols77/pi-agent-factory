import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import {
  freshSessionJsonl,
  grillResultPath,
  grillSessionPath,
  readFreshExplainerSummary,
} from "../src/grill.js";

describe("grill helper module", () => {
  test("grillResultPath points into the per-session transcript dir", () => {
    expect(grillResultPath("/repo", "sess-1")).toBe(
      join("/repo", "sessions", ".factory-transcripts", "sess-1", "grill-result.json"),
    );
  });

  test("grillSessionPath is a timestamped jsonl beside the result file", () => {
    const now = new Date("2026-08-12T10:20:30.123Z");
    expect(grillSessionPath("/repo", "sess-1", now)).toBe(
      join(
        "/repo",
        "sessions",
        ".factory-transcripts",
        "sess-1",
        "grill-2026-08-12T10-20-30-123Z.jsonl",
      ),
    );
  });

  test("readFreshExplainerSummary returns the 'none' note when the dir is missing", () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-none-"));
    expect(readFreshExplainerSummary(cwd)).toBe(
      "No visual explainers present yet -- generate one via visual-explainer/diagram-design.",
    );
  });

  test("readFreshExplainerSummary returns the 'none' note when the dir is empty", () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-empty-"));
    mkdirSync(join(cwd, "docs", "visual-explain"), { recursive: true });
    expect(readFreshExplainerSummary(cwd)).toBe(
      "No visual explainers present yet -- generate one via visual-explainer/diagram-design.",
    );
  });

  test("readFreshExplainerSummary lists markdown explainers by base name", () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-list-"));
    mkdirSync(join(cwd, "docs", "visual-explain"), { recursive: true });
    writeFileSync(join(cwd, "docs", "visual-explain", "rtb.md"), "# x", "utf-8");
    writeFileSync(join(cwd, "docs", "visual-explain", "graph.md"), "# y", "utf-8");
    // non-markdown siblings must be ignored
    writeFileSync(join(cwd, "docs", "visual-explain", "rtb.svg"), "<svg/>", "utf-8");
    expect(readFreshExplainerSummary(cwd)).toBe(
      "Visual explainers present in docs/visual-explain/: graph, rtb. " +
        "Reuse one whose dependency fingerprint matches the current code; " +
        "otherwise generate a new explainer via visual-explainer/diagram-design.",
    );
  });

  test("freshSessionJsonl renders a v3 session header plus a single seeded user message", () => {
    const now = new Date("2026-08-12T10:20:30.000Z");
    let i = 0;
    const newId = () => `id-${i++}`;
    const jsonl = freshSessionJsonl("the seed", "/repo", now, newId);
    const [headerLine, messageLine] = jsonl.trim().split("\n");
    const header = JSON.parse(headerLine!);
    const msg = JSON.parse(messageLine!);
    expect(header).toEqual({
      type: "session",
      version: 3,
      id: "id-0",
      timestamp: now.toISOString(),
      cwd: "/repo",
    });
    expect(msg.type).toBe("message");
    expect(msg.parentId).toBeNull();
    expect(msg.id).toBe("id-1");
    expect(msg.message.role).toBe("user");
    expect(msg.message.content).toEqual([{ type: "text", text: "the seed" }]);
  });
});
