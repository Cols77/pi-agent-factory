import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "vitest";
import { DEFAULT_CONTEXT, readContext, setFeed, writeContext } from "../src/session-policy.js";
import { composeContext, headFeed } from "../src/session-feeds.js";
import { addNote, emptyMemory, memoryPath, writeMemory } from "../src/session-memory.js";

const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) {
    try {
      execFileSync(process.platform === "win32" ? "rmdir" : "rm", ["-rf", d]);
    } catch {
      // ignore
    }
  }
});

function makeDir(): string {
  const d = mkdtempSync(join(tmpdir(), "pif-ctx-"));
  dirs.push(d);
  return d;
}

function makeGitRepo(root: string): void {
  execFileSync("git", ["init", "-q"], { cwd: root });
  execFileSync("git", ["config", "user.email", "t@e"], { cwd: root });
  execFileSync("git", ["config", "user.name", "t"], { cwd: root });
  writeFileSync(join(root, "a.txt"), "hi\n", "utf-8");
  execFileSync("git", ["add", "-A"], { cwd: root });
  execFileSync("git", ["commit", "-q", "-m", "first commit"], { cwd: root });
}

describe("session-policy", () => {
  test("absent policy returns the deterministic default", () => {
    const c = readContext(makeDir());
    expect(c.schema).toBe(1);
    expect(c.enabledFeeds).toEqual(["memory", "head"]);
    expect(c.memory.ttlHours).toBe(24);
  });

  test("write + read round-trips", () => {
    const root = makeDir();
    const c = setFeed(readContext(root), "head", false);
    writeContext(root, c);
    const back = readContext(root);
    expect(back.enabledFeeds).toEqual(["memory"]);
  });

  test("setFeed toggles deterministically and preserves when unchanged", () => {
    const c = readContext(makeDir());
    const off = setFeed(c, "head", false);
    expect(off.enabledFeeds).toEqual(["memory"]);
    // flipping again to the same state returns the same object (no-op)
    expect(setFeed(off, "head", false)).toBe(off);
  });
});

describe("session-feeds", () => {
  test("headFeed returns null on a non-git root (skip, never throw)", () => {
    expect(headFeed(makeDir(), 5, "2026-08-14T10:00:00.000Z")).toBeNull();
  });

  test("headFeed returns branch + HEAD + recent commits on a git repo", () => {
    const root = makeDir();
    makeGitRepo(root);
    const block = headFeed(root, 5, "2026-08-14T10:00:00.000Z");
    expect(block).not.toBeNull();
    expect(block).toContain("branch:");
    expect(block).toContain("HEAD:");
    expect(block).toContain("first commit");
  });

  test("composeContext assembles only enabled feeds and skips empty ones", () => {
    const root = makeDir(); // non-git, no memory store
    const all = composeContext(root, ["memory", "head"], DEFAULT_CONTEXT.memory, 5, "2026-08-14T10:00:00.000Z");
    // neither feed produces content here => nothing to inject
    expect(all.markdown).toBeNull();
    expect(all.skipped.sort()).toEqual(["head", "memory"]);
  });

  test("composeContext includes a memory note when present and head is off", () => {
    const root = makeDir();
    mkdirSync(join(root, ".pi", "factory"), { recursive: true });
    let store = emptyMemory();
    store = addNote(store, { topic: "task:T-1", text: "next", actor: "a" }, DEFAULT_CONTEXT.memory, "2026-08-14T09:00:00.000Z");
    writeMemory(root, store);
    const got = composeContext(root, ["memory"], DEFAULT_CONTEXT.memory, 5, "2026-08-14T10:00:00.000Z");
    expect(got.markdown).not.toBeNull();
    expect(got.included).toEqual(["memory"]);
    expect(got.markdown).toContain("task:T-1");
    expect(existsSync(memoryPath(root))).toBe(true);
  });
});
