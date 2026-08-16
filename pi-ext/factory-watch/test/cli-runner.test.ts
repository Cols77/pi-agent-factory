import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
const spawn = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawn, spawnSync }));

import { runJsonCli, runJsonCliAsync } from "../src/cli-runner.js";

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

function childProcess(): EventEmitter & { stdout: PassThrough; stderr: PassThrough } {
  return Object.assign(new EventEmitter(), { stdout: new PassThrough(), stderr: new PassThrough() });
}

describe("runJsonCliAsync", () => {
  test("parses stdout into a value on the success path", async () => {
    const child = childProcess();
    spawn.mockReturnValue(child);

    const result = runJsonCliAsync<{ scopes: unknown[]; errors: unknown[] }>("/repo", "uv", SUB);
    child.stdout.end(JSON.stringify({ scopes: [], errors: [] }));
    child.stderr.end();
    child.emit("close", 0);

    await expect(result).resolves.toEqual({ ok: true, value: { scopes: [], errors: [] } });
    expect(spawn).toHaveBeenCalledWith("uv", SUB, {
      cwd: "/repo",
      stdio: ["ignore", "pipe", "pipe"],
    });
  });

  test("reports a non-zero exit instead of throwing", async () => {
    const child = childProcess();
    spawn.mockReturnValue(child);

    const result = runJsonCliAsync("/repo", "uv", SUB);
    child.stdout.end();
    child.stderr.end("boom");
    child.emit("close", 1);

    await expect(result).resolves.toMatchObject({ ok: false, error: expect.stringContaining("exited 1") });
    await expect(result).resolves.toMatchObject({ ok: false, error: expect.stringContaining("boom") });
  });

  test("reports unparsable stdout instead of throwing", async () => {
    const child = childProcess();
    spawn.mockReturnValue(child);

    const result = runJsonCliAsync("/repo", "uv", SUB);
    child.stdout.end("not json");
    child.stderr.end();
    child.emit("close", 0);

    await expect(result).resolves.toMatchObject({ ok: false, error: expect.stringContaining("could not parse") });
  });

  test("reports a launch error instead of throwing", async () => {
    const child = childProcess();
    spawn.mockReturnValue(child);

    const result = runJsonCliAsync("/repo", "uv", SUB);
    child.emit("error", new Error("spawn uv ENOENT"));

    await expect(result).resolves.toEqual({ ok: false, error: "spawn uv ENOENT" });
  });

  test("stops capturing stdout once it exceeds the 64 MiB output limit", async () => {
    const child = childProcess();
    spawn.mockReturnValue(child);

    const result = runJsonCliAsync("/repo", "uv", SUB);
    child.stdout.write(Buffer.alloc(64 * 1024 * 1024 + 1));
    child.emit("close", 0);

    await expect(result).resolves.toMatchObject({
      ok: false,
      error: expect.stringContaining("stdout exceeded"),
    });
  });
});
