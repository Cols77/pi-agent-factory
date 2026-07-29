import { spawnSync } from "node:child_process";
import type { Component } from "@earendil-works/pi-tui";
import { Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";
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
import type { ReviewGuide } from "./review-guide.ts";
import { annotationsForFile, anchorForRow, findAnnotation, mapDiffRows } from "./review-model.ts";
import type { Annotation, DiffRowMeta } from "./review-model.ts";

export function hasCodeOnPath(platform: NodeJS.Platform = process.platform): boolean {
  const finder = platform === "win32" ? "where" : "which";
  const result = spawnSync(finder, ["code"], { encoding: "utf-8" });
  return result.status === 0;
}

export interface TuiLike {
  terminal: { rows: number };
}

export type ReviewAction =
  | { type: "comment"; file: string; line?: number; side?: "old" | "new" }
  | { type: "fileComment"; file: string }
  | { type: "edit"; file: string }
  | { type: "toggleReviewed"; file: string }
  | { type: "viewComments" }
  | { type: "approve" }
  | { type: "reject" };

type ViewState =
  | { mode: "summary" }
  | { mode: "file"; index: number; scrollOffset: number; cursor: number };

function formatStatLine(file: FileStat, count: number, reviewed: boolean): string {
  const check = reviewed ? "✓ " : "  ";
  const badge = count > 0 ? `  (${count})` : "";
  return `${check}${file.status}  ${file.path.padEnd(28)} +${file.added}/-${file.removed}${badge}`;
}

export class ReviewOverlay {
  private view: ViewState = { mode: "summary" };
  private selectedIndex = 0;
  private diffLineCache = new Map<string, string[]>();
  private rowMetaCache = new Map<string, DiffRowMeta[]>();
  private readonly files: FileStat[];
  private readonly annotations: Annotation[];
  private readonly reviewed: Set<string>;
  private readonly tui: TuiLike;
  private readonly cwd: string;
  private readonly startCommit: string;
  private readonly onAction: (action: ReviewAction) => void;
  // Already-done mode: per-file diffs come from the deliverables' implementing
  // commits (computeImplementingFileDiffText) rather than start_commit..working
  // tree, and `banner` is shown atop the summary.
  private readonly implementing: boolean;
  private readonly banner: string;
  private readonly guide: ReviewGuide | null;

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
    annotations: Annotation[],
    reviewed: Set<string>,
    tui: TuiLike,
    cwd: string,
    startCommit: string,
    onAction: (action: ReviewAction) => void,
    opts: { implementing?: boolean; banner?: string; guide?: ReviewGuide } = {},
  ) {
    this.files = files;
    this.annotations = annotations;
    this.reviewed = reviewed;
    this.tui = tui;
    this.cwd = cwd;
    this.startCommit = startCommit;
    this.onAction = onAction;
    this.implementing = opts.implementing ?? false;
    this.banner = opts.banner ?? "";
    this.guide = opts.guide ?? null;
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
      const rawLines = diffText.split("\n");
      // renderDiff colorizes via pi-coding-agent's global theme singleton, which
      // is only initialized by the interactive host (initTheme()) -- never by
      // this extension. Fall back to the raw diff text if that global isn't
      // ready (e.g. under test, or if the host hasn't initialized a theme yet)
      // rather than letting the whole overlay crash on an uncaught throw.
      let rendered: string[];
      try {
        rendered = renderDiff(diffText).split("\n");
      } catch {
        rendered = rawLines;
      }
      // Anchoring requires 1:1 alignment between rendered rows and the raw
      // diff lines mapDiffRows() walks. If renderDiff changed the line count
      // (e.g. it collapsed/expanded something), fall back to file-level-only
      // anchoring (all-meta) rather than mis-anchoring a comment onto the
      // wrong line.
      const meta =
        rendered.length === rawLines.length
          ? mapDiffRows(rawLines)
          : rawLines.map(() => ({ kind: "meta" as const }));
      this.rowMetaCache.set(file.path, meta);
      cached = rendered;
      this.diffLineCache.set(file.path, cached);
    }
    return cached;
  }

  private guideLines(width: number): string[] {
    const g = this.guide;
    if (g === null) return [];
    const lines: string[] = [];
    if (g.confidence) lines.push(`Confidence: ${g.confidence}`);
    if (Array.isArray(g.validation) && g.validation.length > 0) {
      lines.push(
        "Validation: " +
          g.validation
            .map((v) => `${v.gate} ${v.summary ?? ""}${v.ok === false ? " ✗" : v.ok ? " ✓" : ""}`.trim())
            .join("   "),
      );
    }
    if (Array.isArray(g.addressed) && g.addressed.length > 0) {
      lines.push(`Already addressed this run (${g.addressed.length}): ${g.addressed.join("; ")}`);
    }
    if (Array.isArray(g.verify) && g.verify.length > 0) {
      lines.push("", "Verify before approving:");
      g.verify.slice(0, 9).forEach((v, i) => {
        const loc = v.file ? `  ${v.file}${v.line ? `:${v.line}` : ""}` : "";
        lines.push(`  [${i + 1}] ${v.item}${loc}`);
      });
    }
    if (lines.length > 0) lines.push("");
    return lines.map((l) => truncateToWidth(l, width));
  }

  private followCursor(view: Extract<ViewState, { mode: "file" }>, viewportHeight: number): void {
    if (view.cursor < view.scrollOffset) {
      view.scrollOffset = view.cursor;
    } else if (view.cursor >= view.scrollOffset + viewportHeight) {
      view.scrollOffset = view.cursor - viewportHeight + 1;
    }
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
      } else if (data === "j") {
        const total = this.diffLinesFor(this.files[view.index]!).length;
        view.cursor = Math.min(view.cursor + 1, Math.max(0, total - 1));
        this.followCursor(view, viewportHeight);
      } else if (data === "k") {
        view.cursor = Math.max(view.cursor - 1, 0);
        this.followCursor(view, viewportHeight);
      } else if (data === "c") {
        // Ensure rowMetaCache is populated even if this file hasn't been
        // rendered yet (e.g. 'c' pressed immediately after opening).
        this.diffLinesFor(this.files[view.index]!);
        const meta = this.rowMetaCache.get(this.files[view.index]!.path) ?? [];
        const { line, side } = anchorForRow(meta, view.cursor);
        this.onAction({ type: "comment", file: this.files[view.index]!.path, line, side });
      } else if (data === "C") {
        this.onAction({ type: "fileComment", file: this.files[view.index]!.path });
      } else if (data === "v") {
        // Reviewed is a summary-level concept (see the summary branch below);
        // file-mode `v` instead opens the comment overview, matching the
        // summary binding for consistency.
        this.onAction({ type: "viewComments" });
      } else if (data === "e") {
        this.onAction({ type: "edit", file: this.files[view.index]!.path });
      }
      return;
    }

    if (matchesKey(data, Key.escape) || data === "q") {
      return; // no-op at the summary -- see Global Constraints
    }
    if (/^[1-9]$/.test(data)) {
      const v = Array.isArray(this.guide?.verify) ? this.guide?.verify?.[Number(data) - 1] : undefined;
      const idx = v?.file ? this.files.findIndex((f) => f.path === v.file) : -1;
      if (idx >= 0) {
        this.view = { mode: "file", index: idx, scrollOffset: 0, cursor: 0 };
      }
      return;
    }
    if (data === "\r" || data === "\n") {
      // Guard against an empty `files` list: computeReviewFiles can (rarely,
      // now that the diff-range bug is fixed) legitimately report zero
      // files, and `this.files[this.selectedIndex]` would be undefined --
      // entering "file" mode here used to crash render()/diffLinesFor() with
      // a TypeError reading `.path` off that undefined entry.
      if (this.files.length > 0) {
        this.view = { mode: "file", index: this.selectedIndex, scrollOffset: 0, cursor: 0 };
      }
    } else if (matchesKey(data, Key.down) || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, this.files.length - 1);
    } else if (matchesKey(data, Key.up) || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if (data === "c") {
      if (this.files.length > 0) {
        this.onAction({ type: "comment", file: this.currentFile().path });
      }
    } else if (data === " ") {
      if (this.files.length > 0) {
        this.onAction({ type: "toggleReviewed", file: this.currentFile().path });
      }
    } else if (data === "v") {
      this.onAction({ type: "viewComments" });
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
      const lines: string[] = [...this.guideLines(width)];
      if (this.banner) {
        lines.push(this.banner, "");
      }
      lines.push(`Task: ${this.files.length} files changed`, "");
      this.files.forEach((f, i) => {
        const prefix = i === this.selectedIndex ? "> " : "  ";
        const count = annotationsForFile(this.annotations, f.path).length;
        lines.push(prefix + formatStatLine(f, count, this.reviewed.has(f.path)));
      });
      lines.push(
        "",
        "↑↓ select  Enter open  c comment  C file comment  space reviewed  v comments  a approve  r reject",
      );
      // pi-tui hard-throws (TUI.doRender) if any rendered line's visible width
      // exceeds the terminal width -- long diff lines / a long banner / a long
      // file path would otherwise crash the whole session. Truncate every line.
      return lines.map((line) => truncateToWidth(line, width));
    }

    const view = this.view;
    const file = this.files[view.index]!;
    const allLines = this.diffLinesFor(file);
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, allLines.length - viewportHeight);
    view.scrollOffset = Math.min(Math.max(0, view.scrollOffset), maxOffset);
    view.cursor = Math.min(Math.max(0, view.cursor), Math.max(0, allLines.length - 1));
    const visible = allLines
      .slice(view.scrollOffset, view.scrollOffset + viewportHeight)
      .map((line, i) => {
        const rowIndex = view.scrollOffset + i;
        const marker = rowIndex === view.cursor ? "> " : "  ";
        return marker + line;
      });
    const lastShown = Math.min(view.scrollOffset + viewportHeight, allLines.length);
    const footer =
      `${file.path} -- line ${view.scrollOffset + 1}-${lastShown} of ${allLines.length} ` +
      "(arrows/PgUp/PgDn/Home/End scroll, j/k cursor, c comment, C file comment, v comments, e edit, q back) --";
    // See the summary branch: every line must fit the terminal width or
    // pi-tui throws. Diff lines especially can be arbitrarily long.
    return [...visible, footer].map((line) => truncateToWidth(line, width));
  }
}

// Read-only browsable list of every annotation across all files, opened from
// the summary screen's `v` key. Deliberately minimal (per the task brief,
// jump-to-file on Enter is optional polish) -- Enter/Escape/q all just close
// the overlay and hand control back to runReviewLoop's ui.custom() loop.
export class CommentListOverlay implements Component {
  private selectedIndex = 0;
  private scrollOffset = 0;
  private readonly annotations: Annotation[];
  private readonly tui: TuiLike;
  private readonly onDone: () => void;

  // Explicit field assignment, not TypeScript constructor parameter
  // properties -- see ReviewOverlay's constructor comment above for why
  // (this module is also loaded via a plain `node <file>.ts` import chain).
  constructor(annotations: Annotation[], tui: TuiLike, onDone: () => void) {
    this.annotations = annotations;
    this.tui = tui;
    this.onDone = onDone;
  }

  // No cached render state beyond the selection/scroll above -- required
  // (non-optional) by pi-tui's Component interface.
  invalidate(): void {}

  private getViewportHeight(): number {
    // Reserve two rows for the title and the footer line.
    return Math.max(1, this.tui.terminal.rows - 4);
  }

  private followSelection(viewportHeight: number): void {
    if (this.selectedIndex < this.scrollOffset) {
      this.scrollOffset = this.selectedIndex;
    } else if (this.selectedIndex >= this.scrollOffset + viewportHeight) {
      this.scrollOffset = this.selectedIndex - viewportHeight + 1;
    }
  }

  handleInput(data: string): void {
    if (matchesKey(data, Key.escape) || data === "q" || data === "\r" || data === "\n") {
      this.onDone();
      return;
    }
    if (this.annotations.length === 0) return;
    const viewportHeight = this.getViewportHeight();
    if (matchesKey(data, Key.down) || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, this.annotations.length - 1);
      this.followSelection(viewportHeight);
    } else if (matchesKey(data, Key.up) || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
      this.followSelection(viewportHeight);
    }
  }

  render(width: number): string[] {
    const viewportHeight = this.getViewportHeight();
    const lines: string[] = [`Comments (${this.annotations.length})`, ""];
    const visible = this.annotations.slice(this.scrollOffset, this.scrollOffset + viewportHeight);
    visible.forEach((a, i) => {
      const rowIndex = this.scrollOffset + i;
      const prefix = rowIndex === this.selectedIndex ? "> " : "  ";
      const loc = `${a.file}${a.line ? ":" + a.line : ""}`;
      const firstLine = a.body.split("\n")[0] ?? "";
      lines.push(`${prefix}${loc}  ${a.severity ?? ""}  ${firstLine}`);
    });
    lines.push("", "↑↓ select  Enter/Esc/q close");
    // See ReviewOverlay.render's comment -- pi-tui hard-throws on any
    // over-width line.
    return lines.map((line) => truncateToWidth(line, width));
  }
}

export interface ReviewDecisionResult {
  decision: "approve" | "reject";
  annotations: Annotation[];
  reviewedFiles: string[];
}

export async function runReviewLoop(
  ui: UiApi,
  cwd: string,
  taskId: string,
  startCommit: string,
  files: FileStat[],
  opts: { implementing?: boolean; banner?: string; guide?: ReviewGuide } = {},
): Promise<ReviewDecisionResult> {
  const annotations: Annotation[] = [];
  const reviewed = new Set<string>();

  for (;;) {
    const action = await ui.custom<ReviewAction>((tui, _theme, _keybindings, done) => {
      return new ReviewOverlay(files, annotations, reviewed, tui, cwd, startCommit, done, opts) as unknown as ReturnType<
        Parameters<UiApi["custom"]>[0]
      >;
    });

    if (action.type === "comment" || action.type === "fileComment") {
      const anchor: { file: string; line?: number; side?: "old" | "new" } =
        action.type === "comment" ? action : { file: action.file };
      const existing = findAnnotation(annotations, anchor.file, anchor.line, anchor.side);
      const text = await ui.editor(
        `Comment on ${anchor.file}${anchor.line ? ":" + anchor.line : ""}`,
        existing?.body,
      );
      if (text !== undefined) {
        if (existing) {
          existing.body = text;
        } else {
          annotations.push({ file: anchor.file, line: anchor.line, side: anchor.side, body: text });
        }
      }
      continue;
    }

    if (action.type === "toggleReviewed") {
      if (reviewed.has(action.file)) {
        reviewed.delete(action.file);
      } else {
        reviewed.add(action.file);
      }
      continue;
    }

    if (action.type === "viewComments") {
      if (annotations.length === 0) {
        ui.notify("no comments yet", "info");
        continue;
      }
      await ui.custom<void>(
        (tui, _theme, _keybindings, done) =>
          new CommentListOverlay(annotations, tui, () => done(undefined)) as unknown as ReturnType<
            Parameters<UiApi["custom"]>[0]
          >,
        { overlay: true, overlayOptions: { width: "80%", maxHeight: "80%", anchor: "center" } },
      );
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
      if (annotations.length === 0) {
        ui.notify("reject requires at least one comment", "error");
        continue;
      }
      const confirmed = await ui.confirm("Reject task?", `${taskId}: send back for another dev iteration?`);
      if (!confirmed) {
        continue;
      }
      return { decision: "reject", annotations, reviewedFiles: [...reviewed] };
    }

    // approve
    const confirmed = await ui.confirm("Approve task?", `${taskId}: mark this task done?`);
    if (!confirmed) {
      continue;
    }
    return { decision: "approve", annotations, reviewedFiles: [...reviewed] };
  }
}
