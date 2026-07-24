import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { describe, expect, test, vi } from "vitest";
import { buildReviewArgs, launchFileEditor, promptComment, ReviewBrowser } from "../src/mission-control-review.js";
import type { FileStat } from "../src/review-diff.js";

vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  return { ...actual, spawnSync: vi.fn() };
});

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

describe("launchFileEditor", () => {
  test("spawns the resolved editor on the given file and reports success", () => {
    vi.mocked(spawnSync).mockReturnValue({ status: 0 } as ReturnType<typeof spawnSync>);
    // Force a deterministic editor resolution for this test: set $VISUAL to
    // a non-terminal command so resolveEditorLaunch's fast path is used
    // without depending on the real machine having `code` on PATH.
    const prevVisual = process.env.VISUAL;
    process.env.VISUAL = "myeditor";
    try {
      const result = launchFileEditor("/repo", "/repo/src/a.ts");
      expect(result).toEqual({ ok: true });
      expect(spawnSync).toHaveBeenCalledWith(
        "myeditor", ["/repo/src/a.ts"], { cwd: "/repo", stdio: "ignore" },
      );
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
    }
  });

  // Mirrors review-overlay.test.ts's "edit surfaces a clear error ... when no
  // GUI editor can be resolved" case: with $VISUAL/$EDITOR unset,
  // resolveEditorLaunch falls back to `hasCodeOnPath()` (spawnSync("where"/
  // "which", ["code"]) -- stubbed here to report "not found" via status 1)
  // and then, on non-win32 platforms, to an explicit "no GUI editor" error.
  // win32 always resolves to notepad instead, so process.platform must be
  // pinned to a non-Windows value for this branch to be reachable
  // deterministically regardless of the machine running the suite.
  test("returns an error result when no editor can be resolved", () => {
    const prevVisual = process.env.VISUAL;
    const prevEditor = process.env.EDITOR;
    const prevTmux = process.env.TMUX;
    delete process.env.VISUAL;
    delete process.env.EDITOR;
    delete process.env.TMUX;
    vi.mocked(spawnSync).mockReturnValue({ status: 1 } as ReturnType<typeof spawnSync>);
    const priorPlatform = process.platform;
    Object.defineProperty(process, "platform", { value: "linux", configurable: true });
    try {
      const result = launchFileEditor("/repo", "/repo/src/a.ts");
      expect(result).toEqual({ ok: false, error: expect.stringContaining("GUI editor") });
    } finally {
      Object.defineProperty(process, "platform", { value: priorPlatform, configurable: true });
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
      if (prevEditor === undefined) delete process.env.EDITOR; else process.env.EDITOR = prevEditor;
      if (prevTmux === undefined) delete process.env.TMUX; else process.env.TMUX = prevTmux;
    }
  });
});

describe("promptComment", () => {
  test("writes currentText to a temp file, spawns the editor, and returns the edited content", () => {
    const prevVisual = process.env.VISUAL;
    process.env.VISUAL = "myeditor";
    vi.mocked(spawnSync).mockImplementation((_cmd, args) => {
      // Simulate the user editing the temp file: args[0] is the temp path.
      writeFileSync((args as string[])[0]!, "new comment text\n", "utf-8");
      return { status: 0 } as ReturnType<typeof spawnSync>;
    });
    try {
      const result = promptComment("/repo", "old text");
      expect(result).toEqual({ ok: true, text: "new comment text" });
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
    }
  });

  test("returns text: undefined when the edited content is empty or whitespace-only", () => {
    const prevVisual = process.env.VISUAL;
    process.env.VISUAL = "myeditor";
    vi.mocked(spawnSync).mockImplementation((_cmd, args) => {
      writeFileSync((args as string[])[0]!, "   \n", "utf-8");
      return { status: 0 } as ReturnType<typeof spawnSync>;
    });
    try {
      const result = promptComment("/repo", undefined);
      expect(result).toEqual({ ok: true, text: undefined });
    } finally {
      if (prevVisual === undefined) delete process.env.VISUAL; else process.env.VISUAL = prevVisual;
    }
  });
});
