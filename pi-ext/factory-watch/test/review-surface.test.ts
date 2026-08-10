import { afterEach, describe, expect, test } from "vitest";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  buildBrowserUrl,
  parseReviewPlansArgs,
  readSurfacePref,
  writeSurfacePref,
  readLayoutPref,
  writeLayoutPref,
} from "../src/review-surface.js";
import { DEFAULT_LAYOUT } from "../src/review-layout.js";

const dirs: string[] = [];
function tmp() {
  const d = mkdtempSync(join(tmpdir(), "surf-"));
  dirs.push(d);
  return d;
}
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

describe("surface pref", () => {
  test("defaults to terminal when unset", () => {
    expect(readSurfacePref(tmp())).toBe("terminal");
  });
  test("round-trips a written pref", () => {
    const d = tmp();
    writeSurfacePref(d, "browser");
    expect(readSurfacePref(d)).toBe("browser");
  });
  test("garbage file falls back to terminal", () => {
    const d = tmp();
    // sessions/ may not exist yet; writeSurfacePref must create it, so write then corrupt
    writeSurfacePref(d, "browser");
    writeFileSync(join(d, "sessions", ".factory-review-surface.json"), "not json");
    expect(readSurfacePref(d)).toBe("terminal");
  });
});

describe("parseReviewPlansArgs", () => {
  test("defaults to prompting", () => {
    expect(parseReviewPlansArgs("")).toEqual({ surface: null, stop: false });
  });
  test("recognises --browser, --terminal and --stop", () => {
    expect(parseReviewPlansArgs("--browser").surface).toBe("browser");
    expect(parseReviewPlansArgs("--terminal").surface).toBe("terminal");
    expect(parseReviewPlansArgs("--stop").stop).toBe(true);
  });
});

describe("buildBrowserUrl", () => {
  test("keeps the base server URL deterministic when no focus is supplied", () => {
    expect(buildBrowserUrl("http://127.0.0.1:4321")).toBe("http://127.0.0.1:4321/");
  });

  test("adds task/run focus in a deterministic and safely encoded order", () => {
    expect(buildBrowserUrl("http://127.0.0.1:4321", {
      taskId: "T 001/?",
      runId: "run#2",
    })).toBe("http://127.0.0.1:4321/?task=T+001%2F%3F&run=run%232");
  });
});

describe("surface preference keys", () => {
  test("docs and review preferences are independent", () => {
    const d = tmp();
    writeSurfacePref(d, "browser", "docs");
    expect(readSurfacePref(d, "docs")).toBe("browser");
    // choosing browser for docs must not redirect where code review opens
    expect(readSurfacePref(d)).toBe("terminal");
  });
  test("the default key keeps its existing behaviour", () => {
    const d = tmp();
    writeSurfacePref(d, "browser");
    expect(readSurfacePref(d)).toBe("browser");
  });
});

describe("layout preference", () => {
  test("round-trips through the surface preference file", () => {
    const cwd = tmp();
    writeLayoutPref(cwd, { collapsed: ["tree"], zoomed: "diff" });
    expect(readLayoutPref(cwd)).toEqual({ collapsed: ["tree"], zoomed: "diff" });
  });

  test("does not disturb the surface preference stored in the same file", () => {
    const cwd = tmp();
    writeSurfacePref(cwd, "browser");
    writeLayoutPref(cwd, { collapsed: ["comments"], zoomed: null });
    expect(readSurfacePref(cwd)).toBe("browser");
  });

  test("a missing file yields the default layout", () => {
    expect(readLayoutPref(tmp())).toEqual(DEFAULT_LAYOUT);
  });

  test("a corrupt stored layout yields the default rather than throwing", () => {
    const cwd = tmp();
    mkdirSync(join(cwd, "sessions"), { recursive: true });
    writeFileSync(join(cwd, "sessions", ".factory-review-surface.json"),
      '{"layout":{"collapsed":["bogus"],"zoomed":"nope"}}', "utf-8");
    expect(readLayoutPref(cwd)).toEqual(DEFAULT_LAYOUT);
  });
});
