import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export type Surface = "terminal" | "browser";

export function surfacePrefPath(cwd: string): string {
  return join(cwd, "sessions", ".factory-review-surface.json");
}

export function readSurfacePref(cwd: string): Surface {
  try {
    const p = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as { surface?: string };
    return p.surface === "browser" ? "browser" : "terminal";
  } catch {
    return "terminal";
  }
}

export function writeSurfacePref(cwd: string, pref: Surface): void {
  try {
    const path = surfacePrefPath(cwd);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify({ surface: pref }), "utf-8");
  } catch {
    // best-effort; a failed write just means we don't remember the choice
  }
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
