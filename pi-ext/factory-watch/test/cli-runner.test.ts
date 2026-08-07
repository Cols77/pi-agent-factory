import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { runJsonCli } from "../src/cli-runner.js";

const SUB = ["run", "python", "-m", "factory.system", "scope", "--json"];

describe("runJsonCli", () => {
  test("parses stdout into a value on the success path", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ scopes: [], errors: [] }), stderr: "" });
    const result = runJsonCli<{ scopes: unknown[]; errors: unknown[] }>("/repo", "uv", SUB);
    expect(result).toEqual({ ok: true, value: { scopes: [], errors: [] } });
  });

  test("reports a non-zero exit instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "", stderr: "boom" });
    const result = runJsonCli("/repo", "uv", SUB);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("exited 1");
      expect(result.error).toContain("boom");
    }
  });

  test("reports unparsable stdout instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "not json", stderr: "" });
    const result = runJsonCli("/repo", "uv", SUB);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("could not parse");
  });

  test("reports a missing binary instead of throwing", () => {
    spawnSync.mockReturnValue({ error: new Error("spawnSync uv ENOENT"), status: null, stdout: "", stderr: "" });
    const result = runJsonCli("/repo", "uv", SUB);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("ENOENT");
  });

  test("passes bin/args/cwd through to spawnSync unmodified", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
    runJsonCli("/some/repo", "uv", SUB);
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      SUB,
      expect.objectContaining({ cwd: "/some/repo", encoding: "utf-8" }),
    );
  });
});
