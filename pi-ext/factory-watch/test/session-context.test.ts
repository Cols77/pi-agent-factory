import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "vitest";
import { DEFAULT_CONTEXT, hasContext, readContext, seedContext, setFeed, setFeeds, writeContext } from "../src/session-policy.js";
import { composeContext, headFeed, ledgerFeed } from "../src/session-feeds.js";
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
    expect(c.enabledFeeds).toEqual(["memory", "head", "ledger"]);
    expect(c.memory.ttlHours).toBe(24);
  });

  test("write + read round-trips", () => {
    const root = makeDir();
    const c = setFeed(readContext(root), "head", false);
    writeContext(root, c);
    const back = readContext(root);
    expect(back.enabledFeeds).toEqual(["memory", "ledger"]);
  });

  test("setFeed toggles deterministically and preserves when unchanged", () => {
    const c = readContext(makeDir());
    const off = setFeed(c, "head", false);
    expect(off.enabledFeeds).toEqual(["memory", "ledger"]);
    // flipping again to the same state returns the same object (no-op)
    expect(setFeed(off, "head", false)).toBe(off);
  });

  test("seedContext writes exactly the picked feeds at defaults", () => {
    const s = seedContext(["head", "ledger"]);
    expect(s.schema).toBe(1);
    expect(s.enabledFeeds).toEqual(["head", "ledger"]);
    expect(s.memory.ttlHours).toBe(24); // defaults preserved
  });

  test("seedContext filters unknown feeds", () => {
    const s = seedContext(["head", "bogus" as never]);
    expect(s.enabledFeeds).toEqual(["head"]);
  });

  test("hasContext reflects whether the policy file exists", () => {
    const root = makeDir();
    expect(hasContext(root)).toBe(false);
    writeContext(root, seedContext(["memory"]));
    expect(hasContext(root)).toBe(true);
  });

  test("setFeeds replaces the exact stream set and preserves other settings", () => {
    const root = makeDir();
    writeContext(root, seedContext(["memory", "head", "ledger"]));
    const c = readContext(root);
    const next = setFeeds(c, ["head", "ledger", "trace_health"]);
    expect(next.enabledFeeds).toEqual(["head", "ledger", "trace_health"]);
    expect(next.memory.ttlHours).toBe(24); // untouched
    expect(setFeeds(c, []).enabledFeeds).toEqual([]); // none
    expect(setFeeds(c, ["head", "bogus" as never]).enabledFeeds).toEqual(["head"]); // filter
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
    const root = makeDir(); // non-git, no memory store, no factory markers, no tasks
    const all = composeContext(root, ["memory", "head", "trace_health", "ledger"], DEFAULT_CONTEXT.memory, 5, "2026-08-14T10:00:00.000Z");
    // no feed produces content (trace_health/ledger guards skip unmarked repo) => no injection
    expect(all.markdown).toBeNull();
    expect(all.skipped.sort()).toEqual(["head", "ledger", "memory", "trace_health"]);
  });

  test("ledgerFeed returns null when there is no tasks dir", () => {
    expect(ledgerFeed(makeDir(), "2026-08-14T10:00:00.000Z", 6)).toBeNull();
  });

  test("ledgerFeed groups task statuses and lists active tasks", () => {
    const root = makeDir();
    mkdirSync(join(root, "tasks"), { recursive: true });
    writeFileSync(
      join(root, "tasks", "T-042.md"),
      '---\nid: T-042\ntitle: "validation next"\nstatus: todo\ndod:\n- x\n---\nbody\n',
      "utf-8");
    writeFileSync(
      join(root, "tasks", "T-041.md"),
      '---\nid: T-041\ntitle: "hooks wired"\nstatus: done\ndod:\n- x\n---\nbody\n',
      "utf-8");
    const block = ledgerFeed(root, "2026-08-14T10:00:00.000Z", 6);
    expect(block).not.toBeNull();
    expect(block).toContain("done: 1");
    expect(block).toContain("todo: 1");
    expect(block).toContain("T-042");
    expect(block).not.toContain("T-041"); // done tasks are counts-only, not listed
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
