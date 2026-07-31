// Real-git integration tests (no `spawnSync` mocking) for computeReviewFiles /
// computeFileDiffText. Mirrors the Python-side regression coverage in
// tests/unit/orchestrator/test_git_ops.py
// (test_subprocess_git_ops_changed_files_sees_uncommitted_changes): the
// human-review gate calls these functions with `start_commit` captured
// *before* dev runs, and dev's changes are still uncommitted at review time
// (runner.py only commits after the human approves) -- see human review flow
// in src/factory/orchestrator/runner.py.
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import {
  computeFileDiffText,
  computeImplementingFileDiffText,
  computeImplementingFiles,
  computeReviewFiles,
} from "../src/review-diff.js";

function git(cwd: string, args: string[]): void {
  const result = spawnSync("git", args, { cwd, encoding: "utf-8" });
  if (result.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${result.stderr}`);
  }
}

function headCommit(cwd: string): string {
  return spawnSync("git", ["rev-parse", "HEAD"], { cwd, encoding: "utf-8" }).stdout.trim();
}

describe("computeReviewFiles / computeFileDiffText against a real repo", () => {
  let repo: string;

  beforeEach(() => {
    repo = mkdtempSync(join(tmpdir(), "review-diff-test-"));
    git(repo, ["init", "-q"]);
    git(repo, ["config", "user.email", "t@example.com"]);
    git(repo, ["config", "user.name", "t"]);
    writeFileSync(join(repo, "a.txt"), "one\n", "utf-8");
    git(repo, ["add", "-A"]);
    git(repo, ["commit", "-q", "-m", "init"]);
  });

  afterEach(() => {
    rmSync(repo, { recursive: true, force: true });
  });

  test("reports the dev agent's uncommitted changes as of the human-review gate", () => {
    const startCommit = headCommit(repo);
    // Simulate what the dev stage actually does by the time human-review
    // runs: modify tracked files, but do NOT commit (runner.py's
    // `git_ops.commit_all` only fires once review has passed -- on human
    // approve, or at the end of an --auto run -- never while human-review
    // is still blocked waiting on a decision).
    writeFileSync(join(repo, "a.txt"), "two\n", "utf-8");

    const files = computeReviewFiles(repo, startCommit);

    expect(files.map((f) => f.path)).toEqual(["a.txt"]);
  });

  test("shows the uncommitted diff text for a single file", () => {
    const startCommit = headCommit(repo);
    writeFileSync(join(repo, "a.txt"), "two\n", "utf-8");

    const text = computeFileDiffText(repo, startCommit, "a.txt");

    expect(text).toContain("-one");
    expect(text).toContain("+two");
  });
});

describe("computeImplementingFiles / computeImplementingFileDiffText against a real repo", () => {
  let repo: string;

  beforeEach(() => {
    repo = mkdtempSync(join(tmpdir(), "impl-diff-test-"));
    git(repo, ["init", "-q"]);
    git(repo, ["config", "user.email", "t@example.com"]);
    git(repo, ["config", "user.name", "t"]);
    writeFileSync(join(repo, "a.py"), "a = 1\n", "utf-8");
    git(repo, ["add", "-A"]);
    git(repo, ["commit", "-q", "-m", "add a"]);
    writeFileSync(join(repo, "b.py"), "b = 2\n", "utf-8");
    git(repo, ["add", "-A"]);
    git(repo, ["commit", "-q", "-m", "add b"]);
  });

  afterEach(() => {
    rmSync(repo, { recursive: true, force: true });
  });

  test("computeImplementingFiles reports the last commit's stats for each deliverable", () => {
    const files = computeImplementingFiles(repo, ["a.py", "b.py"]);
    const paths = files.map((f) => f.path).sort();
    expect(paths).toEqual(["a.py", "b.py"]);
    expect(files.every((f) => f.added > 0)).toBe(true);
    expect(files.every((f) => f.status === "A")).toBe(true);
  });

  test("computeImplementingFileDiffText returns the adding commit's patch for a file", () => {
    const text = computeImplementingFileDiffText(repo, "a.py");
    expect(text).toContain("a.py");
    expect(text).toMatch(/^\+a = 1/m);
  });
});
