import type { Component } from "@earendil-works/pi-tui";
import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { computeReviewFiles } from "./review-diff.ts";
import type { FileStat } from "./review-diff.ts";
import { resolveEditorLaunch } from "./review-editor-launch.ts";
import { hasCodeOnPath, ReviewOverlay } from "./review-overlay.ts";
import type { TuiLike } from "./review-overlay.ts";
import { ConfirmPrompt } from "./confirm-prompt.ts";
import { reviewDecisionPath, writeReviewDecision } from "./review-protocol.ts";
import type { ReviewDecisionPayload } from "./review-protocol.ts";
import type { ReviewAction } from "./review-overlay.ts";

// Blocks on the same editor-launch mechanism runReviewLoop's "edit" action
// uses in review-overlay.ts (resolveEditorLaunch + spawnSync, including the
// tmux-split-and-wait dance) -- mirrored here rather than imported, since
// runReviewLoop's own "edit" block stays untouched (out of scope for this
// task) and there's no shared export to call into instead.
function spawnEditorBlocking(cwd: string, filePath: string): { ok: true } | { ok: false; error: string } {
  const plan = resolveEditorLaunch(process.env, hasCodeOnPath());
  if (!plan.ok) {
    return { ok: false, error: plan.error };
  }
  if (plan.useTmux) {
    const signal = `review-edit-${Date.now()}`;
    spawnSync(
      "tmux",
      ["split-window", "-h", `${plan.command} ${filePath}; tmux wait-for -S ${signal}`],
      { cwd },
    );
    spawnSync("tmux", ["wait-for", signal], { cwd });
  } else {
    spawnSync(plan.command, [...plan.args, filePath], { cwd, stdio: "ignore" });
  }
  return { ok: true };
}

export function launchFileEditor(cwd: string, filePath: string): { ok: true } | { ok: false; error: string } {
  return spawnEditorBlocking(cwd, filePath);
}

// Writes currentText (or "") to a temp file, blocks on the same
// editor-spawn mechanism as launchFileEditor, reads the (possibly edited)
// file back, deletes it, and reports "no comment" (text: undefined) when
// the result is empty/whitespace-only -- matching runReviewLoop's existing
// "comment" semantics (ui.editor() returning undefined/empty means no
// comment was recorded).
export function promptComment(
  cwd: string,
  currentText: string | undefined,
): { ok: true; text: string | undefined } | { ok: false; error: string } {
  const tmpPath = join(tmpdir(), `review-comment-${randomUUID()}.md`);
  writeFileSync(tmpPath, currentText ?? "", "utf-8");
  const result = spawnEditorBlocking(cwd, tmpPath);
  if (!result.ok) {
    unlinkSync(tmpPath);
    return result;
  }
  const text = readFileSync(tmpPath, "utf-8");
  unlinkSync(tmpPath);
  return { ok: true, text: text.trim() === "" ? undefined : text.trim() };
}

// Decision-loop wrapper around ReviewOverlay -- this task (E2) wires the
// human-review diff browser to a real approve/reject decision, deciding
// straight from a standalone terminal window (spawned by the dashboard,
// Task 10) rather than only browsing (superseding the browse-only E1
// increment from task-9-brief.md).
//
// ReviewOverlay itself isn't a full pi-tui Component -- it has no
// invalidate() (its only other caller, runReviewLoop in review-overlay.ts,
// drives it through the host's `ui.custom()` bridge via an `as unknown as`
// cast rather than tui.addChild()/tui.setFocus()). This adapter supplies the
// missing invalidate() no-op and delegates render()/handleInput() to either
// the wrapped ReviewOverlay or an active ConfirmPrompt, so it can be mounted
// directly with the real pi-tui TUI the same way
// mission-control-dashboard.ts mounts its own top-level component.
//
// comment/edit route straight to the Task 4 editor-spawn helpers
// (promptComment/launchFileEditor); approve/reject show a ConfirmPrompt
// (Task 5) and only invoke onDecision once that prompt is confirmed --
// mirroring runReviewLoop's own decision logic in review-overlay.ts (which
// this class does not touch) without depending on the ui.custom()/ui.confirm()
// host bridge runReviewLoop uses.
export class ReviewBrowser implements Component {
  private readonly overlay: ReviewOverlay;
  private readonly comments = new Map<string, string>();
  private readonly cwd: string;
  private readonly taskId: string;
  private readonly onDecision: (decision: ReviewDecisionPayload) => void;
  private activePrompt: ConfirmPrompt | null = null;
  private statusMessage: string | null = null;

  constructor(
    files: FileStat[],
    tui: TuiLike,
    cwd: string,
    startCommit: string,
    taskId: string,
    onDecision: (decision: ReviewDecisionPayload) => void,
  ) {
    this.cwd = cwd;
    this.taskId = taskId;
    this.onDecision = onDecision;
    this.overlay = new ReviewOverlay(files, this.comments, tui, cwd, startCommit, (action) =>
      this.handleAction(action),
    );
  }

  // No cached render state of its own -- delegates entirely to the wrapped
  // ReviewOverlay/ConfirmPrompt. Required (non-optional) by pi-tui's
  // Component interface so this can be passed to tui.addChild()/tui.setFocus().
  invalidate(): void {}

  private handleAction(action: ReviewAction): void {
    this.statusMessage = null;

    if (action.type === "comment") {
      const result = promptComment(this.cwd, this.comments.get(action.file));
      if (!result.ok) {
        this.statusMessage = result.error;
        return;
      }
      if (result.text === undefined) {
        this.comments.delete(action.file);
      } else {
        this.comments.set(action.file, result.text);
      }
      return;
    }

    if (action.type === "edit") {
      const result = launchFileEditor(this.cwd, action.file);
      if (!result.ok) {
        this.statusMessage = result.error;
      }
      return;
    }

    if (action.type === "reject" && this.comments.size === 0) {
      this.statusMessage = "reject requires at least one comment";
      return;
    }

    const title = action.type === "approve" ? "Approve task?" : "Reject task?";
    const message =
      action.type === "approve"
        ? `${this.taskId}: mark this task done?`
        : `${this.taskId}: send back for another dev iteration?`;
    this.activePrompt = new ConfirmPrompt(title, message, (confirmed) => {
      this.activePrompt = null;
      if (!confirmed) {
        return;
      }
      this.onDecision({ decision: action.type, comments: Object.fromEntries(this.comments) });
    });
  }

  handleInput(data: string): void {
    if (this.activePrompt !== null) {
      this.activePrompt.handleInput(data);
      return;
    }
    this.overlay.handleInput(data);
  }

  render(width: number): string[] {
    if (this.activePrompt !== null) {
      return this.activePrompt.render(width);
    }
    const lines = this.overlay.render(width);
    return this.statusMessage === null ? lines : [...lines, "", this.statusMessage];
  }
}

export interface ReviewArgs {
  cwd: string;
  startCommit: string;
  taskId: string;
  sessionId: string;
}

// indexOf returns -1 when a flag is missing; -1 + 1 = 0 would then read
// process.argv[0] (the node executable's own path -- a real, defined
// string), silently defeating the undefined check below. Treat -1
// explicitly as "not found" instead. Mirrors mission-control-dashboard.ts.
export function buildReviewArgs(argv: string[]): ReviewArgs | undefined {
  const cwdArgIndex = argv.indexOf("--cwd");
  const cwd = cwdArgIndex === -1 ? undefined : argv[cwdArgIndex + 1];
  const startCommitArgIndex = argv.indexOf("--start-commit");
  const startCommit = startCommitArgIndex === -1 ? undefined : argv[startCommitArgIndex + 1];
  const taskIdArgIndex = argv.indexOf("--task-id");
  const taskId = taskIdArgIndex === -1 ? undefined : argv[taskIdArgIndex + 1];
  const sessionIdArgIndex = argv.indexOf("--session-id");
  const sessionId = sessionIdArgIndex === -1 ? undefined : argv[sessionIdArgIndex + 1];
  if (cwd === undefined || startCommit === undefined || taskId === undefined || sessionId === undefined) {
    return undefined;
  }
  return { cwd, startCommit, taskId, sessionId };
}

// Standalone entry point -- no `pi --extension`, no LLM. Computes the
// human-review diff once and drives a real pi-tui TUI/ProcessTerminal so the
// user can browse it in a separate terminal window (spawned by the
// dashboard, Task 10). See mission-control-dashboard.ts's main() for the
// same TUI mounting sequence and the reasoning behind each call
// (TUI.start() vs terminal.start(), tui.setFocus() being required for input
// to reach the component, etc).
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  const args = buildReviewArgs(process.argv);
  if (args === undefined) {
    console.error(
      "usage: node mission-control-review.js --cwd <repo-root> --start-commit <sha> --task-id <id> --session-id <id>",
    );
    process.exit(1);
  }
  const { cwd, startCommit, taskId, sessionId } = args;

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const files = computeReviewFiles(cwd, startCommit);
  const browser = new ReviewBrowser(files, { terminal: { rows: terminal.rows } }, cwd, startCommit, taskId, (decision) => {
    writeReviewDecision(reviewDecisionPath(cwd, sessionId), decision);
    process.exit(0);
  });
  tui.addChild(browser);
  tui.setFocus(browser);
  tui.start();
}

if (process.argv[1]?.endsWith("mission-control-review.js") || process.argv[1]?.endsWith("mission-control-review.ts")) {
  void main();
}
