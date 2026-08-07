import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export type Surface = "terminal" | "browser";

export type SurfaceKey = "review" | "docs";

export interface BrowserFocus {
  taskId?: string;
  runId?: string;
}

export function surfacePrefPath(cwd: string): string {
  return join(cwd, "sessions", ".factory-review-surface.json");
}

export function readSurfacePref(cwd: string, key: SurfaceKey = "review"): Surface {
  try {
    const raw = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as Record<string, string>;
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
