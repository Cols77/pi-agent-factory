import { describe, expect, test } from "vitest";
import { parseAllow, toRepoRelative, isPathAllowed } from "../src/allow.js";

describe("parseAllow", () => {
  test("splits, trims, drops empties", () => {
    expect(parseAllow(" src/**, tests/** ,")).toEqual(["src/**", "tests/**"]);
  });
  test("undefined yields empty", () => {
    expect(parseAllow(undefined)).toEqual([]);
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
});
