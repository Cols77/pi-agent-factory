import { spawnSync } from "node:child_process";
import { visibleWidth } from "@earendil-works/pi-tui";
import { describe, expect, test, vi } from "vitest";
import { ReviewOverlay, runReviewLoop } from "../src/review-overlay.js";
import { computeFileDiffText } from "../src/review-diff.js";
import type { FileStat } from "../src/review-diff.js";
import type { UiApi } from "../src/pi-types.js";
import type { ReviewGuide } from "../src/review-guide.js";

vi.mock("node:child_process", () => ({ spawnSync: vi.fn(() => ({ status: 0, stdout: "", stderr: "" })) }));
vi.mock("../src/review-diff.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/review-diff.js")>()),
  computeFileDiffText: vi.fn(() => "diff --git a/x b/x\n@@ -1 +1 @@\n-old\n+new\n"),
}));

const FILES: FileStat[] = [
  { path: "src/rtb.py", status: "M", added: 31, removed: 8 },
  { path: "tests/test_rtb.py", status: "A", added: 5, removed: 0 },
];

function fakeTui() {
  return { terminal: { rows: 24 } };
}

function makeOverlay(
  comments: Map<string, string>,
  onAction: (action: import("../src/review-overlay.js").ReviewAction) => void,
  tui: { terminal: { rows: number } } = fakeTui(),
) {
  return new ReviewOverlay(FILES, comments, tui, "/repo", "abc123", onAction);
}

function manyLineDiff(n: number): string {
  return Array.from({ length: n }, (_, i) => ` line ${i + 1}`).join("\n");
}

describe("ReviewOverlay (summary screen)", () => {
  test("renders a stats line per file with the task header", () => {
    const overlay = makeOverlay(new Map(), () => {});
    const lines = overlay.render(80).join("\n");
    expect(lines).toContain("src/rtb.py");
    expect(lines).toContain("+31/-8");
    expect(lines).toContain("tests/test_rtb.py");
    expect(lines).toContain("+5/-0");
  });

  test("marks commented files with [commented]", () => {
    const overlay = makeOverlay(new Map([["src/rtb.py", "note"]]), () => {});
    expect(overlay.render(80).join("\n")).toContain("src/rtb.py");
    expect(overlay.render(80).join("\n")).toMatch(/src\/rtb\.py.*\[commented\]/);
  });

  test("Enter opens the selected file's diff view", () => {
    const overlay = makeOverlay(new Map(), () => {});
    overlay.handleInput("\r");
    expect(overlay.render(80).join("\n")).toContain("@@ -1 +1 @@");
  });

  test("the file view windows to the terminal's row count, plus a footer", () => {
    vi.mocked(computeFileDiffText).mockReturnValueOnce(manyLineDiff(50));
    const overlay = makeOverlay(new Map(), () => {}, { terminal: { rows: 10 } });
    overlay.handleInput("\r"); // open src/rtb.py
    const lines = overlay.render(80);
    // 10 rows - 2 reserved = 8 content lines + 1 footer line = 9
    expect(lines.length).toBe(9);
    expect(lines[0]).toBe(" line 1");
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("Down/Up scroll the file view; PageDown/Home/End jump", () => {
    vi.mocked(computeFileDiffText).mockReturnValueOnce(manyLineDiff(50));
    const overlay = makeOverlay(new Map(), () => {}, { terminal: { rows: 10 } });
    overlay.handleInput("\r");
    overlay.handleInput("\x1b[B"); // Down
    expect(overlay.render(80)[0]).toBe(" line 2");
    overlay.handleInput("\x1b[A"); // Up
    expect(overlay.render(80)[0]).toBe(" line 1");
    overlay.handleInput("\x1b[F"); // End
    expect(overlay.render(80)[overlay.render(80).length - 2]).toBe(" line 50");
    overlay.handleInput("\x1b[H"); // Home
    expect(overlay.render(80)[0]).toBe(" line 1");
  });

  test("Escape/q at the summary is a no-op", () => {
    const onAction = vi.fn();
    const overlay = makeOverlay(new Map(), onAction);
    overlay.handleInput("\x1b");
    overlay.handleInput("q");
    expect(onAction).not.toHaveBeenCalled();
  });

  test("Escape from the file view returns to the summary", () => {
    const overlay = makeOverlay(new Map(), () => {});
    overlay.handleInput("\r");
    overlay.handleInput("\x1b");
    expect(overlay.render(80).join("\n")).toContain("+31/-8"); // back on summary
  });

  test("c/e/a/r emit an action for the selected file", () => {
    const onAction = vi.fn();
    const overlay = makeOverlay(new Map(), onAction);
    overlay.handleInput("c");
    expect(onAction).toHaveBeenCalledWith({ type: "comment", file: "src/rtb.py" });
    overlay.handleInput("e");
    expect(onAction).toHaveBeenCalledWith({ type: "edit", file: "src/rtb.py" });
    overlay.handleInput("a");
    expect(onAction).toHaveBeenCalledWith({ type: "approve" });
    overlay.handleInput("r");
    expect(onAction).toHaveBeenCalledWith({ type: "reject" });
  });

  // Regression test (symptom 2 -- "crashes during execution"): when
  // computeReviewFiles reports zero files (e.g. while the diff-range bug in
  // review-diff.ts was still in place, this was *every* human review, since
  // dev's changes are uncommitted at review time), Enter/c/e index into an
  // empty `files` array via non-null assertions that satisfy the compiler
  // but not the runtime, throwing "Cannot read properties of undefined
  // (reading 'path')" out of diffLinesFor/currentFile. Approve/reject must
  // keep working since they never touch `files`.
  describe("with zero files", () => {
    function makeEmptyOverlay(onAction: (action: import("../src/review-overlay.js").ReviewAction) => void) {
      return new ReviewOverlay([], new Map(), fakeTui(), "/repo", "abc123", onAction);
    }

    test("Enter does not crash and stays on the summary", () => {
      const overlay = makeEmptyOverlay(() => {});
      expect(() => overlay.handleInput("\r")).not.toThrow();
      expect(() => overlay.render(80)).not.toThrow();
      expect(overlay.render(80).join("\n")).toContain("0 files changed");
    });

    test("c/e are no-ops instead of throwing", () => {
      const onAction = vi.fn();
      const overlay = makeEmptyOverlay(onAction);
      expect(() => overlay.handleInput("c")).not.toThrow();
      expect(() => overlay.handleInput("e")).not.toThrow();
      expect(onAction).not.toHaveBeenCalled();
    });

    test("a/r still emit approve/reject", () => {
      const onAction = vi.fn();
      const overlay = makeEmptyOverlay(onAction);
      overlay.handleInput("a");
      expect(onAction).toHaveBeenCalledWith({ type: "approve" });
      overlay.handleInput("r");
      expect(onAction).toHaveBeenCalledWith({ type: "reject" });
    });
  });
});

describe("runReviewLoop", () => {
  function fakeUi(overrides: Partial<UiApi> = {}): UiApi {
    return {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn(),
      confirm: vi.fn(async () => true), editor: vi.fn(async () => "a comment"),
      custom: vi.fn(),
      ...overrides,
    };
  }

  test("approve resolves once confirmed", async () => {
    const ui = fakeUi({ custom: vi.fn(async () => ({ type: "approve" })) as unknown as UiApi["custom"] });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result).toEqual({ decision: "approve", comments: {} });
  });

  test("reject without any comment is refused and the loop continues", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "reject" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(ui.notify).toHaveBeenCalledWith(expect.stringContaining("at least one comment"), "error");
    expect(result).toEqual({ decision: "approve", comments: {} });
  });

  test("reject with a comment resolves with that comment attached", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "reject" });
    const ui = fakeUi({ custom, editor: vi.fn(async () => "needs a docstring") });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result).toEqual({
      decision: "reject", comments: { "src/rtb.py": "needs a docstring" },
    });
  });

  test("declining the confirm dialog re-opens the overlay instead of finishing", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "approve" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom, confirm: vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true) });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(custom).toHaveBeenCalledTimes(2);
    expect(result.decision).toBe("approve");
  });

  test("edit spawns the resolved GUI editor on the file, then loops back", async () => {
    const priorEnv = { ...process.env };
    process.env.VISUAL = "code -w";
    vi.mocked(spawnSync).mockReturnValue({ status: 0, stdout: "", stderr: "" } as ReturnType<typeof spawnSync>);
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "edit", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });

    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);

    expect(spawnSync).toHaveBeenCalledWith("code", ["-w", "src/rtb.py"], { cwd: "/repo", stdio: "ignore" });
    expect(result.decision).toBe("approve");
    process.env = priorEnv;
  });

  test("edit with tmux spawns split-window and wait-for, then loops back", async () => {
    const priorEnv = { ...process.env };
    process.env.VISUAL = "vim";
    process.env.TMUX = "/tmp/tmux-1000/default,1234,0";
    vi.mocked(spawnSync).mockReturnValue({ status: 0, stdout: "", stderr: "" } as ReturnType<typeof spawnSync>);
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "edit", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });

    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);

    // Verify tmux commands were called (filter out any hasCodeOnPath check calls)
    const calls = vi.mocked(spawnSync).mock.calls;
    const tmuxCalls = calls.filter(call => call[0] === "tmux");
    expect(tmuxCalls).toHaveLength(2);

    // First call: split-window -h
    const firstCall = tmuxCalls[0]!;
    expect((firstCall[1] as string[])[0]).toBe("split-window");
    expect((firstCall[1] as string[])[1]).toBe("-h");
    expect((firstCall[1] as string[])[2]).toMatch(/^vim src\/rtb\.py; tmux wait-for -S review-edit-\d+$/);
    expect(firstCall[2]).toEqual({ cwd: "/repo" });

    // Second call: wait-for <signal>
    const secondCall = tmuxCalls[1]!;
    expect((secondCall[1] as string[])[0]).toBe("wait-for");
    expect((secondCall[1] as string[])[1]).toMatch(/^review-edit-\d+$/);
    expect(secondCall[2]).toEqual({ cwd: "/repo" });

    expect(result.decision).toBe("approve");
    process.env = priorEnv;
  });

  test("edit surfaces a clear error and loops back when no GUI editor can be resolved", async () => {
    const priorEnv = { ...process.env };
    delete process.env.VISUAL;
    delete process.env.EDITOR;
    delete process.env.TMUX;
    vi.mocked(spawnSync).mockReturnValue({ status: 1, stdout: "", stderr: "" } as ReturnType<typeof spawnSync>);
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "edit", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });

    // resolveEditorLaunch's "no GUI editor" branch only fires on non-win32
    // platforms (win32 always falls back to notepad -- see
    // review-editor-launch.ts). runReviewLoop resolves hasCodeOnPath()/
    // resolveEditorLaunch() against the real process.platform, so this test
    // must pin a non-Windows platform to be deterministic when the suite runs
    // on a Windows dev machine/CI runner.
    const priorPlatform = process.platform;
    Object.defineProperty(process, "platform", { value: "linux", configurable: true });
    try {
      await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
      expect(ui.notify).toHaveBeenCalledWith(expect.stringContaining("GUI editor"), "error");
    } finally {
      Object.defineProperty(process, "platform", { value: priorPlatform, configurable: true });
      process.env = priorEnv;
    }
  });
});

describe("ReviewOverlay focus guide", () => {
  const guide: ReviewGuide = {
    confidence: "medium -- edges thin",
    validation: [{ gate: "sim", ok: true, summary: "12 passed" }],
    addressed: ["review (round 1): docstring"],
    verify: [{ item: "advance past last waypoint", file: "src/rtb.py", line: 44 }],
  };

  test("renders the guide header in the summary", () => {
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide });
    const out = overlay.render(120).join("\n");
    expect(out).toContain("medium -- edges thin");
    expect(out).toContain("12 passed");
    expect(out).toContain("advance past last waypoint");
    expect(out).toContain("[1]");
    expect(out).toContain("Already addressed this run (1)");
    expect(out).toContain("docstring");
  });

  test("digit jumps to the referenced file's diff", () => {
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide });
    overlay.handleInput("1"); // verify item 1 -> src/rtb.py (index 0 in FILES)
    // now in file view for src/rtb.py -> its diff (mocked computeFileDiffText) shows
    expect(overlay.render(80).join("\n")).toContain("@@");
  });

  test("digit for an item without a matching file is a no-op", () => {
    const g2: ReviewGuide = { verify: [{ item: "no file here" }] };
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide: g2 });
    expect(() => overlay.handleInput("1")).not.toThrow();
    expect(overlay.render(80).join("\n")).toContain("files changed"); // still on summary
  });

  test("a corrupt guide (string-shaped fields) does not break render", () => {
    const bad = { verify: "none", validation: "x", addressed: "y", confidence: "c" } as unknown as ReviewGuide;
    const overlay = new ReviewOverlay(FILES, new Map(), fakeTui(), "/repo", "abc", () => {}, { guide: bad });
    expect(() => overlay.render(80)).not.toThrow();
    expect(overlay.render(80).join("\n")).toContain("files changed"); // still usable
  });
});

describe("ReviewOverlay already-done (implementing) mode", () => {
  test("renders the banner in the summary view", () => {
    const files: FileStat[] = [{ path: "a.py", status: "A", added: 3, removed: 0 }];
    const overlay = new ReviewOverlay(
      files, new Map(), { terminal: { rows: 20 } }, "/repo", "", () => {},
      { implementing: true, banner: "This task appears already complete" },
    );
    const summary = overlay.render(80).join("\n");
    expect(summary).toContain("This task appears already complete");
  });
});

describe("ReviewOverlay line-width truncation (pi-tui hard-throws on over-width lines)", () => {
  test("file view truncates every line to the given width", () => {
    const longLine = "+" + "x".repeat(200);
    vi.mocked(computeFileDiffText).mockReturnValueOnce(`@@ -1 +1 @@\n${longLine}\n`);
    const overlay = makeOverlay(new Map(), () => {});
    overlay.handleInput("\r"); // open the diff view
    for (const line of overlay.render(80)) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(80);
    }
  });

  test("summary view truncates a long banner to the given width", () => {
    const files: FileStat[] = [{ path: "a.py", status: "A", added: 1, removed: 0 }];
    const overlay = new ReviewOverlay(
      files, new Map(), { terminal: { rows: 20 } }, "/repo", "", () => {},
      { implementing: true, banner: "This task appears already complete -- approve to mark it done, reject to re-run it." },
    );
    for (const line of overlay.render(40)) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(40);
    }
  });
});
