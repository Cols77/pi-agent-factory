import { afterEach, describe, expect, test } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  parseReviewPlansArgs,
  readSurfacePref,
  writeSurfacePref,
} from "../src/review-surface.js";

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
