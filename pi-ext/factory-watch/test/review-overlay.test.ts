import { spawnSync } from "node:child_process";
import { visibleWidth } from "@earendil-works/pi-tui";
import { describe, expect, test, vi } from "vitest";
import { CommentListOverlay, ReviewOverlay, runReviewLoop } from "../src/review-overlay.js";
import { computeFileDiffText } from "../src/review-diff.js";
import type { FileStat } from "../src/review-diff.js";
import type { UiApi } from "../src/pi-types.js";
import type { ReviewGuide } from "../src/review-guide.js";
import type { Annotation } from "../src/review-model.js";

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
  annotations: Annotation[],
  onAction: (action: import("../src/review-overlay.js").ReviewAction) => void,
  tui: { terminal: { rows: number } } = fakeTui(),
  reviewed: Set<string> = new Set(),
) {
  return new ReviewOverlay(FILES, annotations, reviewed, tui, "/repo", "abc123", onAction);
}

function manyLineDiff(n: number): string {
  return Array.from({ length: n }, (_, i) => ` line ${i + 1}`).join("\n");
}

describe("ReviewOverlay (summary screen)", () => {
  test("renders a stats line per file with the task header", () => {
    const overlay = makeOverlay([], () => {});
    const lines = overlay.render(80).join("\n");
    expect(lines).toContain("src/rtb.py");
    expect(lines).toContain("+31/-8");
    expect(lines).toContain("tests/test_rtb.py");
    expect(lines).toContain("+5/-0");
  });

  test("summary shows a per-file annotation count badge", () => {
    const anns: Annotation[] = [
      { file: "src/rtb.py", line: 1, side: "new", body: "x" },
      { file: "src/rtb.py", line: 2, side: "new", body: "y" },
    ];
    const overlay = makeOverlay(anns, () => {});
    expect(overlay.render(80).join("\n")).toMatch(/src\/rtb\.py.*\(2\)/);
  });

  test("summary shows a reviewed checkmark for files in the reviewed set", () => {
    const overlay = makeOverlay([], () => {}, fakeTui(), new Set(["src/rtb.py"]));
    const lines = overlay.render(80);
    const rtbLine = lines.find((l) => l.includes("src/rtb.py"))!;
    const otherLine = lines.find((l) => l.includes("tests/test_rtb.py"))!;
    expect(rtbLine).toContain("✓");
    expect(otherLine).not.toContain("✓");
  });

  test("Enter opens the selected file's diff view", () => {
    const overlay = makeOverlay([], () => {});
    overlay.handleInput("\r");
    expect(overlay.render(80).join("\n")).toContain("@@ -1 +1 @@");
  });

  test("the file view windows to the terminal's row count, plus a footer", () => {
    vi.mocked(computeFileDiffText).mockReturnValueOnce(manyLineDiff(50));
    const overlay = makeOverlay([], () => {}, { terminal: { rows: 10 } });
    overlay.handleInput("\r"); // open src/rtb.py
    const lines = overlay.render(80);
    // 10 rows - 2 reserved = 8 content lines + 1 footer line = 9
    expect(lines.length).toBe(9);
    expect(lines[0]).toContain("line 1");
    // the cursor starts on row 0 and is rendered with a "> " gutter marker
    expect(lines[0]!.startsWith(">")).toBe(true);
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("Down/Up scroll the file view; PageDown/Home/End jump", () => {
    vi.mocked(computeFileDiffText).mockReturnValueOnce(manyLineDiff(50));
    const overlay = makeOverlay([], () => {}, { terminal: { rows: 10 } });
    overlay.handleInput("\r");
    overlay.handleInput("\x1b[B"); // Down
    expect(overlay.render(80)[0]).toContain("line 2");
    overlay.handleInput("\x1b[A"); // Up
    expect(overlay.render(80)[0]).toContain("line 1");
    overlay.handleInput("\x1b[F"); // End
    expect(overlay.render(80)[overlay.render(80).length - 2]).toContain("line 50");
    overlay.handleInput("\x1b[H"); // Home
    expect(overlay.render(80)[0]).toContain("line 1");
  });

  test("Escape/q at the summary is a no-op", () => {
    const onAction = vi.fn();
    const overlay = makeOverlay([], onAction);
    overlay.handleInput("\x1b");
    overlay.handleInput("q");
    expect(onAction).not.toHaveBeenCalled();
  });

  test("Escape from the file view returns to the summary", () => {
    const overlay = makeOverlay([], () => {});
    overlay.handleInput("\r");
    overlay.handleInput("\x1b");
    expect(overlay.render(80).join("\n")).toContain("+31/-8"); // back on summary
  });

  test("c/e/a/r emit an action for the selected file", () => {
    const onAction = vi.fn();
    const overlay = makeOverlay([], onAction);
    overlay.handleInput("c");
    expect(onAction).toHaveBeenCalledWith({ type: "comment", file: "src/rtb.py" });
    overlay.handleInput("e");
    expect(onAction).toHaveBeenCalledWith({ type: "edit", file: "src/rtb.py" });
    overlay.handleInput("a");
    expect(onAction).toHaveBeenCalledWith({ type: "approve" });
    overlay.handleInput("r");
    expect(onAction).toHaveBeenCalledWith({ type: "reject" });
  });

  test("space toggles reviewed and renders a check", () => {
    const actions: import("../src/review-overlay.js").ReviewAction[] = [];
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
    overlay.handleInput(" ");
    expect(actions.at(-1)).toEqual({ type: "toggleReviewed", file: "src/rtb.py" });
  });

  test("reviewed set renders a check in the summary", () => {
    const overlay = new ReviewOverlay(FILES, [], new Set(["src/rtb.py"]), fakeTui(), "/repo", "abc123", () => {});
    expect(overlay.render(80).join("\n")).toMatch(/✓.*src\/rtb\.py/);
  });

  test("v requests the comment overview", () => {
    const actions: import("../src/review-overlay.js").ReviewAction[] = [];
    const overlay = new ReviewOverlay(
      FILES,
      [{ file: "src/rtb.py", line: 1, side: "new", body: "x" }],
      new Set(),
      fakeTui(),
      "/repo",
      "abc123",
      (a) => actions.push(a),
    );
    overlay.handleInput("v");
    expect(actions.at(-1)).toEqual({ type: "viewComments" });
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
      return new ReviewOverlay([], [], new Set(), fakeTui(), "/repo", "abc123", onAction);
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

describe("ReviewOverlay (file view) per-line comments", () => {
  // The mocked diff is "diff --git a/x b/x\n@@ -1 +1 @@\n-old\n+new\n", which
  // renders (see review-model.test.ts's mapDiffRows coverage for the anchoring
  // rules) as:
  //   row 0: "diff --git a/x b/x"  (meta,  no anchor)
  //   row 1: "@@ -1 +1 @@"         (hunk,  no anchor)
  //   row 2: "-old"                (del,   anchors to {line: 1, side: "old"})
  //   row 3: "+new"                (add,   anchors to {line: 1, side: "new"})
  // Enter opens the file with the cursor on row 0. Two "j" presses walk the
  // cursor to row 2 (the "-old" row), so the resulting comment must carry
  // exactly that row's anchor -- this is the precise, non-tautological
  // assertion called for instead of the brief's `typeof line === "number" ||
  // line === undefined` placeholder (which is always true).
  test("commenting inside a file view carries the exact line anchor", () => {
    const actions: import("../src/review-overlay.js").ReviewAction[] = [];
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
    overlay.handleInput("\r"); // open src/rtb.py; cursor starts at row 0
    overlay.handleInput("j"); // cursor -> row 1 ("@@ -1 +1 @@")
    overlay.handleInput("j"); // cursor -> row 2 ("-old")
    overlay.handleInput("c");
    const last = actions.at(-1)!;
    expect(last).toEqual({ type: "comment", file: "src/rtb.py", line: 1, side: "old" });
  });

  test("commenting one row further down anchors to the add side", () => {
    const actions: import("../src/review-overlay.js").ReviewAction[] = [];
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
    overlay.handleInput("\r");
    overlay.handleInput("j"); // row 1
    overlay.handleInput("j"); // row 2 ("-old")
    overlay.handleInput("j"); // row 3 ("+new")
    overlay.handleInput("c");
    const last = actions.at(-1)!;
    expect(last).toEqual({ type: "comment", file: "src/rtb.py", line: 1, side: "new" });
  });

  test("k moves the cursor back up, changing the anchor accordingly", () => {
    const actions: import("../src/review-overlay.js").ReviewAction[] = [];
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
    overlay.handleInput("\r");
    overlay.handleInput("j");
    overlay.handleInput("j");
    overlay.handleInput("j"); // row 3 ("+new")
    overlay.handleInput("k"); // back to row 2 ("-old")
    overlay.handleInput("c");
    const last = actions.at(-1)!;
    expect(last).toEqual({ type: "comment", file: "src/rtb.py", line: 1, side: "old" });
  });

  test("C emits a file-level comment action without a line anchor", () => {
    const actions: import("../src/review-overlay.js").ReviewAction[] = [];
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", (a) => actions.push(a));
    overlay.handleInput("\r");
    overlay.handleInput("j");
    overlay.handleInput("C");
    expect(actions.at(-1)).toEqual({ type: "fileComment", file: "src/rtb.py" });
  });

  test("v inside file view requests the comment overview, not a reviewed toggle", () => {
    const onAction = vi.fn();
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", onAction);
    overlay.handleInput("\r");
    overlay.handleInput("v");
    expect(onAction).toHaveBeenCalledWith({ type: "viewComments" });
    expect(onAction).not.toHaveBeenCalledWith(expect.objectContaining({ type: "toggleReviewed" }));
  });

  test("the cursor marker moves with j/k without breaking width truncation", () => {
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc123", () => {});
    overlay.handleInput("\r");
    overlay.handleInput("j");
    const lines = overlay.render(80);
    // row 1 (the "@@ -1 +1 @@" hunk line) should now carry the marker.
    expect(lines[1]!.startsWith(">")).toBe(true);
    expect(lines[0]!.startsWith(">")).toBe(false);
    for (const line of lines) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(80);
    }
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
    expect(result).toEqual({ decision: "approve", annotations: [], reviewedFiles: [] });
  });

  test("reject without any comment is refused and the loop continues", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "reject" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(ui.notify).toHaveBeenCalledWith(expect.stringContaining("at least one comment"), "error");
    expect(result).toEqual({ decision: "approve", annotations: [], reviewedFiles: [] });
  });

  test("reject with a comment resolves with that comment attached", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "reject" });
    const ui = fakeUi({ custom, editor: vi.fn(async () => "needs a docstring") });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result).toEqual({
      decision: "reject",
      annotations: [{ file: "src/rtb.py", body: "needs a docstring" }],
      reviewedFiles: [],
    });
  });

  test("a per-line comment carries its anchor into the annotation", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py", line: 1, side: "old" })
      .mockResolvedValueOnce({ type: "reject" });
    const ui = fakeUi({ custom, editor: vi.fn(async () => "fix this line") });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result.annotations).toEqual([{ file: "src/rtb.py", line: 1, side: "old", body: "fix this line" }]);
  });

  test("re-commenting the same anchor edits the existing annotation instead of duplicating it", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py", line: 1, side: "old" })
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py", line: 1, side: "old" })
      .mockResolvedValueOnce({ type: "reject" });
    const editor = vi.fn().mockResolvedValueOnce("first draft").mockResolvedValueOnce("revised");
    const ui = fakeUi({ custom, editor });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result.annotations).toEqual([{ file: "src/rtb.py", line: 1, side: "old", body: "revised" }]);
    // the second editor call should have been pre-filled with the first draft
    expect(editor).toHaveBeenNthCalledWith(2, expect.any(String), "first draft");
  });

  test("fileComment produces a line-less annotation", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "fileComment", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "reject" });
    const ui = fakeUi({ custom, editor: vi.fn(async () => "overall looks fine") });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result.annotations).toEqual([{ file: "src/rtb.py", body: "overall looks fine" }]);
  });

  test("toggleReviewed adds and removes files from reviewedFiles", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "toggleReviewed", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "toggleReviewed", file: "tests/test_rtb.py" })
      .mockResolvedValueOnce({ type: "toggleReviewed", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(result.reviewedFiles).toEqual(["tests/test_rtb.py"]);
  });

  test("viewComments loops back without finishing", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "viewComments" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(custom).toHaveBeenCalledTimes(2);
    expect(result.decision).toBe("approve");
  });

  test("viewComments with no annotations notifies instead of opening an overlay", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "viewComments" })
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom });
    await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    expect(ui.notify).toHaveBeenCalledWith("no comments yet", "info");
    // Only the two outer ui.custom() calls for the action loop itself --
    // no third call to open the (empty) comment overview.
    expect(custom).toHaveBeenCalledTimes(2);
  });

  test("viewComments with annotations opens the comment overview overlay, then loops back", async () => {
    const custom = vi.fn()
      .mockResolvedValueOnce({ type: "comment", file: "src/rtb.py" })
      .mockResolvedValueOnce({ type: "viewComments" })
      .mockResolvedValueOnce(undefined) // the comment-overview overlay's own ui.custom() call, closed by the user
      .mockResolvedValueOnce({ type: "approve" });
    const ui = fakeUi({ custom, editor: vi.fn(async () => "needs work") });
    const result = await runReviewLoop(ui, "/repo", "T-001", "abc123", FILES);
    // 3 outer-loop calls (comment, viewComments, approve) + 1 for the
    // comment-overview overlay itself = 4 total ui.custom() invocations.
    expect(custom).toHaveBeenCalledTimes(4);
    expect(ui.notify).not.toHaveBeenCalledWith("no comments yet", "info");
    const overviewCall = custom.mock.calls[2]!;
    expect(overviewCall[1]).toEqual({
      overlay: true,
      overlayOptions: { width: "80%", maxHeight: "80%", anchor: "center" },
    });
    expect(result.decision).toBe("approve");
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

describe("CommentListOverlay", () => {
  const ANNS: Annotation[] = [
    { file: "src/rtb.py", line: 12, side: "new", body: "tighten this loop\nsecond line", severity: "must-fix" },
    { file: "tests/test_rtb.py", body: "overall solid" },
  ];

  test("renders one row per annotation with file, line, severity and first body line", () => {
    const overlay = new CommentListOverlay(ANNS, fakeTui(), () => {});
    const out = overlay.render(80).join("\n");
    expect(out).toContain("src/rtb.py:12");
    expect(out).toContain("must-fix");
    expect(out).toContain("tighten this loop");
    expect(out).not.toContain("second line"); // only the first line of a multi-line body
    expect(out).toContain("tests/test_rtb.py");
    expect(out).toContain("overall solid");
  });

  test("down/up move the selection marker between rows", () => {
    const overlay = new CommentListOverlay(ANNS, fakeTui(), () => {});
    let lines = overlay.render(80);
    expect(lines.find((l) => l.includes("src/rtb.py:12"))!.startsWith(">")).toBe(true);
    overlay.handleInput("\x1b[B"); // Down
    lines = overlay.render(80);
    expect(lines.find((l) => l.includes("src/rtb.py:12"))!.startsWith(">")).toBe(false);
    expect(lines.find((l) => l.includes("tests/test_rtb.py"))!.startsWith(">")).toBe(true);
    overlay.handleInput("\x1b[A"); // Up
    lines = overlay.render(80);
    expect(lines.find((l) => l.includes("src/rtb.py:12"))!.startsWith(">")).toBe(true);
  });

  test("selection does not move past the last or before the first row", () => {
    const overlay = new CommentListOverlay(ANNS, fakeTui(), () => {});
    overlay.handleInput("\x1b[A"); // Up at the top -- no-op
    expect(overlay.render(80).find((l) => l.includes("src/rtb.py:12"))!.startsWith(">")).toBe(true);
    overlay.handleInput("\x1b[B");
    overlay.handleInput("\x1b[B"); // Down past the last row -- clamps
    expect(overlay.render(80).find((l) => l.includes("tests/test_rtb.py"))!.startsWith(">")).toBe(true);
  });

  test("Enter, Escape, and q all close the overlay", () => {
    for (const key of ["\r", "\x1b", "q"]) {
      const onDone = vi.fn();
      const overlay = new CommentListOverlay(ANNS, fakeTui(), onDone);
      overlay.handleInput(key);
      expect(onDone).toHaveBeenCalledTimes(1);
    }
  });

  test("an empty annotation list renders without throwing and closes cleanly", () => {
    const onDone = vi.fn();
    const overlay = new CommentListOverlay([], fakeTui(), onDone);
    expect(() => overlay.render(80)).not.toThrow();
    expect(() => overlay.handleInput("\x1b[B")).not.toThrow();
    overlay.handleInput("q");
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  test("every rendered row is truncated to the given width", () => {
    const longAnns: Annotation[] = [
      { file: "src/" + "x".repeat(200) + ".py", body: "y".repeat(200) },
    ];
    const overlay = new CommentListOverlay(longAnns, fakeTui(), () => {});
    for (const line of overlay.render(80)) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(80);
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
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc", () => {}, { guide });
    const out = overlay.render(120).join("\n");
    expect(out).toContain("medium -- edges thin");
    expect(out).toContain("12 passed");
    expect(out).toContain("advance past last waypoint");
    expect(out).toContain("[1]");
    expect(out).toContain("Already addressed this run (1)");
    expect(out).toContain("docstring");
  });

  test("digit jumps to the referenced file's diff", () => {
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc", () => {}, { guide });
    overlay.handleInput("1"); // verify item 1 -> src/rtb.py (index 0 in FILES)
    // now in file view for src/rtb.py -> its diff (mocked computeFileDiffText) shows
    expect(overlay.render(80).join("\n")).toContain("@@");
  });

  test("digit for an item without a matching file is a no-op", () => {
    const g2: ReviewGuide = { verify: [{ item: "no file here" }] };
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc", () => {}, { guide: g2 });
    expect(() => overlay.handleInput("1")).not.toThrow();
    expect(overlay.render(80).join("\n")).toContain("files changed"); // still on summary
  });

  test("a corrupt guide (string-shaped fields) does not break render", () => {
    const bad = { verify: "none", validation: "x", addressed: "y", confidence: "c" } as unknown as ReviewGuide;
    const overlay = new ReviewOverlay(FILES, [], new Set(), fakeTui(), "/repo", "abc", () => {}, { guide: bad });
    expect(() => overlay.render(80)).not.toThrow();
    expect(overlay.render(80).join("\n")).toContain("files changed"); // still usable
  });
});

describe("ReviewOverlay already-done (implementing) mode", () => {
  test("renders the banner in the summary view", () => {
    const files: FileStat[] = [{ path: "a.py", status: "A", added: 3, removed: 0 }];
    const overlay = new ReviewOverlay(
      files, [], new Set(), { terminal: { rows: 20 } }, "/repo", "", () => {},
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
    const overlay = makeOverlay([], () => {});
    overlay.handleInput("\r"); // open the diff view
    for (const line of overlay.render(80)) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(80);
    }
  });

  test("summary view truncates a long banner to the given width", () => {
    const files: FileStat[] = [{ path: "a.py", status: "A", added: 1, removed: 0 }];
    const overlay = new ReviewOverlay(
      files, [], new Set(), { terminal: { rows: 20 } }, "/repo", "", () => {},
      { implementing: true, banner: "This task appears already complete -- approve to mark it done, reject to re-run it." },
    );
    for (const line of overlay.render(40)) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(40);
    }
  });
});
