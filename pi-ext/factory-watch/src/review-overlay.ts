import { spawnSync } from "node:child_process";
import { Key, matchesKey } from "@earendil-works/pi-tui";
import { renderDiff } from "@earendil-works/pi-coding-agent";
// .ts (not .js) relative imports -- this file is now also loaded via a
// plain `node <file>.ts` import chain (mission-control-review.ts), and only
// the .ts sources exist on disk (no compiled .js output), so a ".js"
// specifier fails Node's real module resolution with ERR_MODULE_NOT_FOUND.
// Other files (e.g. index.ts) still import this same module tree with
// ".js" specifiers for vitest -- each import statement resolves
// independently, so this doesn't affect those.
import { computeFileDiffText, computeImplementingFileDiffText } from "./review-diff.ts";
import type { FileStat } from "./review-diff.ts";
import { resolveEditorLaunch } from "./review-editor-launch.ts";
import type { UiApi } from "./pi-types.js";

export function hasCodeOnPath(platform: NodeJS.Platform = process.platform): boolean {
  const finder = platform === "win32" ? "where" : "which";
  const result = spawnSync(finder, ["code"], { encoding: "utf-8" });
  return result.status === 0;
}

export interface TuiLike {
  terminal: { rows: number };
}

export type ReviewAction =
  | { type: "comment"; file: string }
  | { type: "edit"; file: string }
  | { type: "approve" }
  | { type: "reject" };

type ViewState = { mode: "summary" } | { mode: "file"; index: number; scrollOffset: number };

function formatStatLine(file: FileStat, commented: boolean): string {
  const tag = commented ? "   [commented]" : "";
  return `${file.status}  ${file.path.padEnd(28)} +${file.added}/-${file.removed}${tag}`;
}

export class ReviewOverlay {
  private view: ViewState = { mode: "summary" };
  private selectedIndex = 0;
  private diffLineCache = new Map<string, string[]>();
  private readonly files: FileStat[];
  private readonly comments: Map<string, string>;
  private readonly tui: TuiLike;
  private readonly cwd: string;
  private readonly startCommit: string;
  private readonly onAction: (action: ReviewAction) => void;
  // Already-done mode: per-file diffs come from the deliverables' implementing
  // commits (computeImplementingFileDiffText) rather than start_commit..working
  // tree, and `banner` is shown atop the summary.
  private readonly implementing: boolean;
  private readonly banner: string;

  // Explicit field assignment, not TypeScript constructor parameter
  // properties -- this file is now also loaded via a plain `node <file>.ts`
  // import chain (mission-control-review.ts), and Node's strip-only TS
  // execution rejects parameter properties with
  // ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX. vitest's esbuild-based resolution and
  // the pi host's extension loader both tolerated the old syntax, which is
  // why this went unnoticed until a real `node <file>.ts` entry point
  // imported it.
  constructor(
    files: FileStat[],
    comments: Map<string, string>,
    tui: TuiLike,
    cwd: string,
    startCommit: string,
    onAction: (action: ReviewAction) => void,
    opts: { implementing?: boolean; banner?: string } = {},
  ) {
    this.files = files;
    this.comments = comments;
    this.tui = tui;
    this.cwd = cwd;
    this.startCommit = startCommit;
    this.onAction = onAction;
    this.implementing = opts.implementing ?? false;
    this.banner = opts.banner ?? "";
  }

  private currentFile(): FileStat {
    return this.files[this.selectedIndex]!;
  }

  private getViewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  private diffLinesFor(file: FileStat): string[] {
    let cached = this.diffLineCache.get(file.path);
    if (cached === undefined) {
      const diffText = this.implementing
        ? computeImplementingFileDiffText(this.cwd, file.path)
        : computeFileDiffText(this.cwd, this.startCommit, file.path);
      // renderDiff colorizes via pi-coding-agent's global theme singleton, which
      // is only initialized by the interactive host (initTheme()) -- never by
      // this extension. Fall back to the raw diff text if that global isn't
      // ready (e.g. under test, or if the host hasn't initialized a theme yet)
      // rather than letting the whole overlay crash on an uncaught throw.
      let rendered: string;
      try {
        rendered = renderDiff(diffText);
      } catch {
        rendered = diffText;
      }
      cached = rendered.split("\n");
      this.diffLineCache.set(file.path, cached);
    }
    return cached;
  }

  handleInput(data: string): void {
    if (this.view.mode === "file") {
      const view = this.view;
      const viewportHeight = this.getViewportHeight();
      if (matchesKey(data, Key.down)) {
        view.scrollOffset += 1;
      } else if (matchesKey(data, Key.up)) {
        view.scrollOffset -= 1;
      } else if (matchesKey(data, Key.pageDown)) {
        view.scrollOffset += viewportHeight;
      } else if (matchesKey(data, Key.pageUp)) {
        view.scrollOffset -= viewportHeight;
      } else if (matchesKey(data, Key.home)) {
        view.scrollOffset = 0;
      } else if (matchesKey(data, Key.end)) {
        view.scrollOffset = Number.MAX_SAFE_INTEGER;
      } else if (matchesKey(data, Key.escape) || data === "q") {
        this.view = { mode: "summary" };
      } else if (data === "c") {
        this.onAction({ type: "comment", file: this.files[view.index]!.path });
      } else if (data === "e") {
        this.onAction({ type: "edit", file: this.files[view.index]!.path });
      }
      return;
    }

    if (matchesKey(data, Key.escape) || data === "q") {
      return; // no-op at the summary -- see Global Constraints
    }
    if (data === "\r" || data === "\n") {
      // Guard against an empty `files` list: computeReviewFiles can (rarely,
      // now that the diff-range bug is fixed) legitimately report zero
      // files, and `this.files[this.selectedIndex]` would be undefined --
      // entering "file" mode here used to crash render()/diffLinesFor() with
      // a TypeError reading `.path` off that undefined entry.
      if (this.files.length > 0) {
        this.view = { mode: "file", index: this.selectedIndex, scrollOffset: 0 };
      }
    } else if (matchesKey(data, Key.down) || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, this.files.length - 1);
    } else if (matchesKey(data, Key.up) || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if (data === "c") {
      if (this.files.length > 0) {
        this.onAction({ type: "comment", file: this.currentFile().path });
      }
    } else if (data === "e") {
      if (this.files.length > 0) {
        this.onAction({ type: "edit", file: this.currentFile().path });
      }
    } else if (data === "a") {
      this.onAction({ type: "approve" });
    } else if (data === "r") {
      this.onAction({ type: "reject" });
    }
  }

  render(width: number): string[] {
    if (this.view.mode === "summary") {
      const lines: string[] = [];
      if (this.banner) {
        lines.push(this.banner, "");
      }
      lines.push(`Task: ${this.files.length} files changed`, "");
      this.files.forEach((f, i) => {
        const prefix = i === this.selectedIndex ? "> " : "  ";
        lines.push(prefix + formatStatLine(f, this.comments.has(f.path)));
      });
      lines.push("", "↑↓ select  Enter open  c comment  e edit  a approve  r reject");
      return lines;
    }

    const view = this.view;
    const file = this.files[view.index]!;
    const allLines = this.diffLinesFor(file);
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, allLines.length - viewportHeight);
    view.scrollOffset = Math.min(Math.max(0, view.scrollOffset), maxOffset);
    const visible = allLines.slice(view.scrollOffset, view.scrollOffset + viewportHeight);
    const lastShown = Math.min(view.scrollOffset + viewportHeight, allLines.length);
    const footer =
      `${file.path} -- line ${view.scrollOffset + 1}-${lastShown} of ${allLines.length} ` +
      "(arrows/PgUp/PgDn/Home/End, c comment, e edit, q back) --";
    return [...visible, footer];
  }
}

export interface ReviewDecisionResult {
  decision: "approve" | "reject";
  comments: Record<string, string>;
}

export async function runReviewLoop(
  ui: UiApi,
  cwd: string,
  taskId: string,
  startCommit: string,
  files: FileStat[],
  opts: { implementing?: boolean; banner?: string } = {},
): Promise<ReviewDecisionResult> {
  const comments = new Map<string, string>();

  for (;;) {
    const action = await ui.custom<ReviewAction>((tui, _theme, _keybindings, done) => {
      return new ReviewOverlay(files, comments, tui, cwd, startCommit, done, opts) as unknown as ReturnType<
        Parameters<UiApi["custom"]>[0]
      >;
    });

    if (action.type === "comment") {
      const text = await ui.editor(`Comment on ${action.file}`, comments.get(action.file));
      if (text !== undefined) {
        comments.set(action.file, text);
      }
      continue;
    }

    if (action.type === "edit") {
      const plan = resolveEditorLaunch(process.env, hasCodeOnPath());
      if (!plan.ok) {
        ui.notify(plan.error, "error");
        continue;
      }
      if (plan.useTmux) {
        const signal = `review-edit-${Date.now()}`;
        spawnSync(
          "tmux",
          ["split-window", "-h", `${plan.command} ${action.file}; tmux wait-for -S ${signal}`],
          { cwd },
        );
        spawnSync("tmux", ["wait-for", signal], { cwd });
      } else {
        spawnSync(plan.command, [...plan.args, action.file], { cwd, stdio: "ignore" });
      }
      // The next ui.custom() call below constructs a fresh ReviewOverlay with
      // an empty diffLineCache, so re-opening it naturally recomputes this
      // file's diff against the (possibly now-edited) working tree -- no
      // separate "refresh" step needed.
      continue;
    }

    if (action.type === "reject") {
      if (comments.size === 0) {
        ui.notify("reject requires at least one comment", "error");
        continue;
      }
      const confirmed = await ui.confirm("Reject task?", `${taskId}: send back for another dev iteration?`);
      if (!confirmed) {
        continue;
      }
      return { decision: "reject", comments: Object.fromEntries(comments) };
    }

    // approve
    const confirmed = await ui.confirm("Approve task?", `${taskId}: mark this task done?`);
    if (!confirmed) {
      continue;
    }
    return { decision: "approve", comments: Object.fromEntries(comments) };
  }
}
