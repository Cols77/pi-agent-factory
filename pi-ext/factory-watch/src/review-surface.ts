import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { DEFAULT_LAYOUT, normalizeLayout } from "./review-layout.js";
import type { LayoutState } from "./review-layout.js";

export type Surface = "terminal" | "browser";

// "watch" is deliberately its own key. factory-watch used to read "docs",
// so choosing Browser once for /review-plans silently changed what
// /factory-watch did -- a command whose description says it opens mission
// control. Surfaces are per-command preferences, not one global mode.
export type SurfaceKey = "review" | "docs" | "watch";

export interface BrowserFocus {
  taskId?: string;
  runId?: string;
}

export function surfacePrefPath(cwd: string): string {
  return join(cwd, "sessions", ".factory-review-surface.json");
}

export function readSurfacePref(cwd: string, key: SurfaceKey = "review"): Surface {
  try {
    const raw = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as Record<string, unknown>;
    // "surface" is the pre-existing key for code review; keep honouring it so
    // an existing preference file is not silently discarded.
    const value = key === "review" ? (raw["surface"] ?? raw["review"]) : raw[key];
    return value === "browser" ? "browser" : "terminal";
  } catch {
    return "terminal";
  }
}

export function writeSurfacePref(cwd: string, pref: Surface, key: SurfaceKey = "review"): void {
  try {
    const path = surfacePrefPath(cwd);
    mkdirSync(dirname(path), { recursive: true });
    let existing: Record<string, string> = {};
    try {
      existing = JSON.parse(readFileSync(path, "utf-8")) as Record<string, string>;
    } catch {
      existing = {};
    }
    existing[key === "review" ? "surface" : key] = pref;
    writeFileSync(path, JSON.stringify(existing), "utf-8");
  } catch {
    // best-effort; a failed write just means we don't remember the choice
  }
}

// Stored under its own "layout" key in the same file the surface preference
// uses. localStorage is not an option: the review server binds port 0, so
// every review is a new origin and a browser-stored layout would silently
// reset each time.
export function readLayoutPref(cwd: string): LayoutState {
  try {
    const raw = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as Record<string, unknown>;
    return normalizeLayout(raw["layout"]);
  } catch {
    return DEFAULT_LAYOUT;
  }
}

export function writeLayoutPref(cwd: string, state: LayoutState): void {
  try {
    const path = surfacePrefPath(cwd);
    mkdirSync(dirname(path), { recursive: true });
    let existing: Record<string, unknown> = {};
    try {
      existing = JSON.parse(readFileSync(path, "utf-8")) as Record<string, unknown>;
    } catch {
      existing = {};
    }
    existing["layout"] = normalizeLayout(state);
    writeFileSync(path, JSON.stringify(existing), "utf-8");
  } catch {
    // best-effort; a failed write just means we don't remember the layout
  }
}

export function parseReviewPlansArgs(args: string): {
  surface: Surface | null;
  stop: boolean;
} {
  const stop = /(^|\s)--stop(\s|$)/.test(args);
  if (/(^|\s)--browser(\s|$)/.test(args)) return { surface: "browser", stop };
  if (/(^|\s)--terminal(\s|$)/.test(args)) return { surface: "terminal", stop };
  return { surface: null, stop };
}

export function buildBrowserUrl(baseUrl: string, focus: BrowserFocus = {}): string {
  const url = new URL(baseUrl);
  const taskId = focus.taskId?.trim();
  const runId = focus.runId?.trim();
  if (taskId) url.searchParams.set("task", taskId);
  if (runId) url.searchParams.set("run", runId);
  return url.toString();
}

export function openInBrowser(url: string, platform: NodeJS.Platform = process.platform): void {
  let child;
  if (platform === "win32") {
    child = spawn("cmd", ["/c", "start", "", url], { detached: true, stdio: "ignore" });
  } else if (platform === "darwin") {
    child = spawn("open", [url], { detached: true, stdio: "ignore" });
  } else {
    child = spawn("xdg-open", [url], { detached: true, stdio: "ignore" });
  }
  child.unref();
}
