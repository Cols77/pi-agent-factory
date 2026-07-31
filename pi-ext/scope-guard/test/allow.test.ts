import { describe, expect, test } from "vitest";
import { parseAllow, toRepoRelative, isPathAllowed, containsTraversal } from "../src/allow.js";

describe("parseAllow", () => {
  test("splits, trims, drops empties", () => {
    expect(parseAllow(" src/**, tests/** ,")).toEqual(["src/**", "tests/**"]);
  });
  test("undefined yields empty", () => {
    expect(parseAllow(undefined)).toEqual([]);
  });
  test("does not split commas inside brace-expansion groups", () => {
    expect(parseAllow("src/{a,b}/**, tests/**")).toEqual(["src/{a,b}/**", "tests/**"]);
  });
});

describe("toRepoRelative", () => {
  test("normalizes backslashes", () => {
    expect(toRepoRelative("src\\drone\\x.py", "C:/repo")).toBe("src/drone/x.py");
  });
  test("strips absolute cwd prefix (windows)", () => {
    expect(toRepoRelative("C:\\repo\\src\\x.py", "C:\\repo")).toBe("src/x.py");
  });
});

describe("containsTraversal", () => {
  test("detects a literal .. segment", () => {
    expect(containsTraversal("src/../../secrets/.env")).toBe(true);
  });
  test("does not flag paths without .. segments", () => {
    expect(containsTraversal("src/drone/x.py")).toBe(false);
  });
  test("does not false-positive on dotted filenames", () => {
    expect(containsTraversal("src/..hidden/x.py")).toBe(false);
  });
});

describe("isPathAllowed", () => {
  const cwd = "C:/repo";
  test("matches a glob", () => {
    expect(isPathAllowed("src/x.py", cwd, ["src/**"])).toBe(true);
  });
  test("absolute path under cwd matches", () => {
    expect(isPathAllowed("C:\\repo\\src\\x.py", cwd, ["src/**"])).toBe(true);
  });
  test("outside allowlist is denied", () => {
    expect(isPathAllowed("secrets/.env", cwd, ["src/**"])).toBe(false);
  });
  test("empty globs deny everything", () => {
    expect(isPathAllowed("src/x.py", cwd, [])).toBe(false);
  });
  test("path traversal is explicitly denied, not incidentally", () => {
    expect(isPathAllowed("src/../../secrets/.env", cwd, ["src/**"])).toBe(false);
  });
});
