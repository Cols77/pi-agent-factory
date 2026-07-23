import { describe, expect, test } from "vitest";
import { buildReviewArgs, ReviewBrowser } from "../src/mission-control-review.js";
import type { FileStat } from "../src/review-diff.js";

const FILES: FileStat[] = [
  { path: "src/a.ts", status: "M", added: 3, removed: 1 },
  { path: "src/b.ts", status: "A", added: 10, removed: 0 },
];

describe("buildReviewArgs", () => {
  test("missing --start-commit returns undefined (indexOf -1 guard, not argv[0])", () => {
    // If the `=== -1` guard were missing, indexOf's -1 result would be used
    // as `argv[-1 + 1]` = argv[0] (the node executable path) -- a defined
    // string that would silently defeat this check.
    expect(buildReviewArgs(["node", "mission-control-review.ts", "--cwd", "/repo"])).toBeUndefined();
  });

  test("missing --cwd returns undefined", () => {
    expect(buildReviewArgs(["node", "mission-control-review.ts", "--start-commit", "abc123"])).toBeUndefined();
  });

  test("both flags present returns parsed args", () => {
    expect(
      buildReviewArgs(["node", "mission-control-review.ts", "--cwd", "/repo", "--start-commit", "abc123"]),
    ).toEqual({ cwd: "/repo", startCommit: "abc123" });
  });
});

describe("ReviewBrowser (browse mode)", () => {
  test("renders the changed-file list from the given FileStat[]", () => {
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123");
    const lines = browser.render(80).join("\n");
    expect(lines).toContain("2 files changed");
    expect(lines).toContain("src/a.ts");
    expect(lines).toContain("src/b.ts");
  });

  test("Down moves the selection without sending any decision", () => {
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123");
    browser.handleInput("\x1b[B"); // down
    const lines = browser.render(80);
    expect(lines.find((l) => l.startsWith("> "))).toContain("src/b.ts");
  });

  test("approve/reject keys are no-ops in browse mode (no decision channel wired)", () => {
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123");
    expect(() => browser.handleInput("a")).not.toThrow();
    expect(() => browser.handleInput("r")).not.toThrow();
    // Still showing the summary view -- no crash, no external effect.
    expect(browser.render(80).join("\n")).toContain("2 files changed");
  });

  test("invalidate() exists as a no-op (required by pi-tui's Component interface)", () => {
    const browser = new ReviewBrowser(FILES, { terminal: { rows: 24 } }, "/repo", "abc123");
    expect(() => browser.invalidate()).not.toThrow();
  });
});
