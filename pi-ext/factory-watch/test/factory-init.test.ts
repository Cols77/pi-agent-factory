import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "vitest";
import {
  BLOCK_END,
  BLOCK_START,
  buildManagedBlock,
  managedBlockIssues,
  replaceManagedBlock,
  resolveProjectRoot,
  runFactoryCheck,
  runFactoryInit,
  atomicWrite,
} from "../src/factory-init.js";
import {
  MAX_SUBAGENT_DEPTH,
  buildSubagentInvocation,
  planSubagentSpawn,
} from "../src/subagent-tool.js";
import { subagentTool } from "../src/subagent-tool.js";

const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) {
    try {
      execFileSync(process.platform === "win32" ? "rmdir" : "rm", ["-rf", d]); // best-effort
    } catch {
      // ignore
    }
  }
});

function makeDir(): string {
  const d = mkdtempSync(join(tmpdir(), "pif-init-"));
  dirs.push(d);
  return d;
}

function writeSampleRepo(root: string): void {
  writeFileSync(join(root, "README.md"), "# sample\n\nThis is a sample project purpose.", "utf-8");
  writeFileSync(
    join(root, "pyproject.toml"),
    '[tool.pytest.ini_options]\nmarkers = ["unit: fast", "sim: slow"]\n',
    "utf-8",
  );
  mkdirSync(join(root, ".factory"), { recursive: true });
  writeFileSync(
    join(root, ".factory", "factory.yaml"),
    "gates:\n  unit:\n    - { cmd: \"uv run pytest -m unit\" }\n",
    "utf-8",
  );
}

// 1. Initialisation of an empty temporary repository.
test("initialises an empty repository (profile + managed AGENTS.md block)", () => {
  const root = makeDir();
  const r = runFactoryInit({ root, mode: "init" });
  expect(r.status).toBe("changed");
  expect(r.reload).toBe(true);

  const agents = readFileSync(join(root, "AGENTS.md"), "utf-8");
  expect(agents).toContain(BLOCK_START);
  expect(agents).toContain(BLOCK_END);

  const profile = JSON.parse(
    readFileSync(join(root, ".pi", "factory", "project-profile.json"), "utf-8"),
  ) as { schema: number; project_root: string };
  expect(profile.schema).toBe(2);
  expect(profile.project_root).toBe(root);
});

// 2. Initialisation when a user-owned AGENTS.md already exists.
test("initialises when a user-owned AGENTS.md already exists without clobbering it", () => {
  const root = makeDir();
  writeSampleRepo(root);
  writeFileSync(join(root, "AGENTS.md"), "# My repo\n\nmy human rules here\n", "utf-8");
  const r = runFactoryInit({ root, mode: "init" });
  expect(r.status).toBe("changed");
  const agents = readFileSync(join(root, "AGENTS.md"), "utf-8");
  expect(agents).toContain("my human rules here");
  expect(agents).toContain(BLOCK_START);
});

// 3. Preservation of content outside managed markers (byte-for-byte).
test("preserves all content outside the managed markers byte-for-byte", () => {
  const root = makeDir();
  writeSampleRepo(root);
  const preamble = "# Repo\n\ncustom intro\n\n";
  const tail = "\n\n## Notes\n\nappended by a human\n";
  const existing = `${preamble}${BLOCK_START}\n# Project (factory bootstrap)\nostale\n${BLOCK_END}${tail}`;
  writeFileSync(join(root, "AGENTS.md"), existing, "utf-8");
  runFactoryInit({ root, mode: "refresh" });

  const agents = readFileSync(join(root, "AGENTS.md"), "utf-8");
  expect(agents.startsWith(preamble)).toBe(true);
  expect(agents.endsWith(tail)).toBe(true);
  // exactly one managed block
  expect(agents.split(BLOCK_START).length - 1).toBe(1);
  expect(agents.split(BLOCK_END).length - 1).toBe(1);
});

// 4. Idempotent second execution.
test("second run without repo changes produces no file changes", () => {
  const root = makeDir();
  writeSampleRepo(root);
  runFactoryInit({ root, mode: "init" });
  const agents1 = readFileSync(join(root, "AGENTS.md"), "utf-8");
  const profile1 = readFileSync(join(root, ".pi", "factory", "project-profile.json"), "utf-8");
  const r = runFactoryInit({ root, mode: "init" });
  expect(r.status).toBe("ok");
  expect(r.reload).toBe(false);
  expect(readFileSync(join(root, "AGENTS.md"), "utf-8")).toBe(agents1);
  expect(readFileSync(join(root, ".pi", "factory", "project-profile.json"), "utf-8")).toBe(profile1);
});

// 5. Explicit refresh after evidence changes.
test("refresh updates factory-managed content after evidence changes", () => {
  const root = makeDir();
  writeSampleRepo(root);
  runFactoryInit({ root, mode: "init" });
  const before = readFileSync(join(root, "AGENTS.md"), "utf-8");

  // Change an evidence source: new pytest marker.
  writeFileSync(
    join(root, "pyproject.toml"),
    '[tool.pytest.ini_options]\nmarkers = ["unit: fast", "sim: slow", "integration: slow2"]\n',
    "utf-8",
  );

  // drift is detected
  const checkAfterChange = runFactoryCheck(root);
  expect(checkAfterChange.profileFresh).toBe(false);
  expect(checkAfterChange.drift.some((d) => d.changed)).toBe(true);

  const r = runFactoryInit({ root, mode: "refresh" });
  expect(r.status).toBe("changed");
  const after = readFileSync(join(root, "AGENTS.md"), "utf-8");
  expect(after).not.toBe(before);
  expect(after).toContain("integration");
});

// 6. Read-only --check.
test("check is read-only and reports stale/missing artifacts", () => {
  const root = makeDir();
  writeSampleRepo(root);
  const c = runFactoryCheck(root);
  expect(c.ok).toBe(false);
  expect(c.profilePresent).toBe(false);
  expect(existsSync(join(root, "AGENTS.md"))).toBe(false); // nothing written

  runFactoryInit({ root, mode: "init" });
  const c2 = runFactoryCheck(root);
  expect(c2.ok).toBe(true);
  expect(c2.profileFresh).toBe(true);
  expect(c2.blockPresent).toBe(true);
});

// 7. Malformed / duplicate marker handling -> fail safely.
test("malformed and duplicate markers fail safely instead of corrupting", () => {
  const root = makeDir();
  writeSampleRepo(root);

  // only an end marker (malformed)
  writeFileSync(join(root, "AGENTS.md"), `hello\n${BLOCK_END}\n`, "utf-8");
  const issues = managedBlockIssues(readFileSync(join(root, "AGENTS.md"), "utf-8"));
  expect(issues.length).toBeGreaterThan(0);
  const before = readFileSync(join(root, "AGENTS.md"), "utf-8");
  expect(() => replaceManagedBlock(before, buildSampleBlock())).toThrow();
  expect(readFileSync(join(root, "AGENTS.md"), "utf-8")).toBe(before); // untouched

  // duplicate start markers
  const dup = `${BLOCK_START}\na\n${BLOCK_START}\nb\n${BLOCK_END}\n`;
  expect(managedBlockIssues(dup).length).toBeGreaterThan(0);
  expect(() => replaceManagedBlock(dup, buildSampleBlock())).toThrow();
});

// 8. Atomic-write failure behaviour.
test("atomicWrite leaves no partial/corrupt file on a failure path", () => {
  const root = makeDir();
  const target = join(root, "out.json");
  atomicWrite(target, '{"ok": true}');
  expect(readFileSync(target, "utf-8")).toBe('{"ok": true}');

  // Failure: target's parent is a file, so the write cannot succeed.
  writeFileSync(join(root, "blocker"), "x", "utf-8");
  expect(() => atomicWrite(join(root, "blocker", "child.json"), "{}")).toThrow();
  // no stray temp files left behind in root
  const leftovers = readdirSync(root).filter((n) => n.includes(".tmp-"));
  expect(leftovers).toEqual([]);
});

// 9. Git-root resolution from a nested directory.
test("resolves the git project root from a nested directory", () => {
  const root = makeDir();
  execFileSync("git", ["init", "-q"], { cwd: root });
  mkdirSync(join(root, "a", "b"), { recursive: true });
  const { root: resolved, method } = resolveProjectRoot(join(root, "a", "b"));
  expect(method).toBe("git");
  expect(resolved).toBe(root);
});

// 10. Non-Git fallback.
test("falls back to cwd when not under git", () => {
  const root = makeDir();
  const { root: resolved, method } = resolveProjectRoot(join(root, "sub"));
  expect(method).toBe("cwd-fallback");
  expect(resolved).toBe(join(root, "sub"));
});

// 11. Exclusion of secrets and generated/dependency directories.
test("excludes secrets, generated output and dependency dirs from the profile", () => {
  const root = makeDir();
  writeSampleRepo(root);
  for (const d of [".venv", "node_modules", ".pytest_cache", "build", ".ruff_cache"]) {
    mkdirSync(join(root, d), { recursive: true });
  }
  writeFileSync(join(root, ".env"), "SECRET=abc\n", "utf-8");
  writeFileSync(join(root, ".env.local"), "SECRET=def\n", "utf-8");

  const r = runFactoryInit({ root, mode: "init" });
  const sourceFiles = (r.profile as { _source_files: string[] })._source_files;
  for (const f of sourceFiles) {
    for (const bad of [".venv", "node_modules", ".pytest_cache", "build", ".ruff_cache", ".env"]) {
      expect(f.includes(bad)).toBe(false);
    }
  }
  // the generated profile itself contains no secret value
  const profileText = readFileSync(join(root, ".pi", "factory", "project-profile.json"), "utf-8");
  expect(profileText).not.toContain("SECRET=abc");
});

// 12. Reload is only flagged after actual changes.
test("reload flag is true only when a run actually changes files", () => {
  const root = makeDir();
  writeSampleRepo(root);
  expect(runFactoryInit({ root, mode: "init" }).reload).toBe(true);
  expect(runFactoryInit({ root, mode: "init" }).reload).toBe(false); // idempotent -> no reload
  writeFileSync(
    join(root, "pyproject.toml"),
    '[tool.pytest.ini_options]\nmarkers = ["unit: fast"]\n',
    "utf-8",
  );
  expect(runFactoryInit({ root, mode: "refresh" }).reload).toBe(true);
});

// 13. Subagent startup in the project root with context-file loading enabled.
test("subagent child starts in the project root with context files enabled", () => {
  const root = makeDir();
  const inv = buildSubagentInvocation({ root, task: "do x", currentDepth: 0 });
  expect(inv).not.toBeNull();
  const i = inv!;
  // No context-file-disabling flag is ever present.
  expect(i.cmd).not.toContain("--no-context-files");
  expect(i.cmd).not.toContain("-nc");
  // Structured mode + concise @file packet + extension inheritance.
  expect(i.cmd).toContain("--mode");
  expect(i.cmd.some((a) => a.startsWith("@"))).toBe(true);
  expect(i.cmd.some((a) => a.includes("index.ts"))).toBe(true);
  // Depth env is propagated.
  expect(i.env.PI_FACTORY_SUBAGENT_DEPTH).toBe("1");
});

// 13b. Recursion prevention for the subagent tool.
test("subagent invocation refuses beyond the recursion bound", () => {
  const inv = buildSubagentInvocation({ root: makeDir(), task: "x", currentDepth: MAX_SUBAGENT_DEPTH });
  expect(inv).toBeNull();
});

// 13c. Spawn planning: on Windows the `pi` npm shim (.cmd/.sh) needs a shell,
// and any argument containing whitespace must be pre-quoted because Node does
// not quote the argv for a shell. On POSIX the shebang script execs directly.
test("subagent spawn plan on win32 goes through a shell and quotes whitespace args", () => {
  const plan = planSubagentSpawn(
    ["pi", "-p", "@C:/path with space/packet.md", "--mode", "json", "--extension", "C:/a b/src/index.ts"],
    "win32",
  );
  expect(plan.shell).toBe(true);
  expect(plan.args).toEqual([]);
  // cmd.exe escape rule: a double quote inside an arg is doubled.
  expect(plan.file).toContain('"@C:/path with space/packet.md"');
  expect(plan.file).toContain('"C:/a b/src/index.ts"');
  // Plain elements are not wrapped.
  expect(plan.file).toContain("-p");
  expect(plan.file).toContain("--mode");
});

test("subagent spawn plan escapes embedded double quotes on win32", () => {
  const plan = planSubagentSpawn(["pi", "-p", '@C:/a"b/packet.md'], "win32");
  expect(plan.shell).toBe(true);
  // cmd.exe doubles an embedded double quote; the @file prefix is preserved.
  expect(plan.file).toContain('"@C:/a""b/packet.md"');
});

test("subagent spawn plan on posix execs the argv directly with no shell", () => {
  const plan = planSubagentSpawn(
    ["pi", "-p", "@C:/path with space/packet.md", "--mode", "json"],
    "linux",
  );
  expect(plan.shell).toBe(false);
  expect(plan.file).toBe("pi");
  expect(plan.args).toEqual(["-p", "@C:/path with space/packet.md", "--mode", "json"]);
});

// 14. Registered subagent tool exposes its prompt snippet and guidelines.
test("subagent tool registration exposes promptSnippet and promptGuidelines", () => {
  expect(typeof subagentTool.promptSnippet).toBe("string");
  expect(Array.isArray(subagentTool.promptGuidelines)).toBe(true);
  const joined = (subagentTool.promptGuidelines ?? []).join("\n");
  expect(joined).toMatch(/delegate|subagent/i);
  // The contract topics section 1 requires the tool itself to teach.
  expect(joined).toMatch(/recurs/i);
  expect(subagentTool.description).toMatch(/AGENTS\.md/);
});

// 15. Bootstrap remains available after context reconstruction (determinism).
test("managed block regeneration is deterministic (survives reconstruction/compaction)", () => {
  const root = makeDir();
  writeSampleRepo(root);
  const a = runFactoryInit({ root, mode: "init" });
  // A fresh discovery with the same evidence yields the byte-identical block,
  // so a re-built prompt after compaction does not need to rediscover facts.
  const b = runFactoryInit({ root, mode: "init" });
  expect(buildManagedBlock(a.profile)).toBe(buildManagedBlock(b.profile));
  // And it equals exactly what is on disk between the markers.
  const agents = readFileSync(join(root, "AGENTS.md"), "utf-8");
  const body = agents.slice(
    agents.indexOf(BLOCK_START) + BLOCK_START.length,
    agents.lastIndexOf(BLOCK_END),
  );
  expect(buildManagedBlock(a.profile)).toBe(`${BLOCK_START}${body}${BLOCK_END}`);
});

function buildSampleBlock(): string {
  return `${BLOCK_START}\n# Project (factory bootstrap)\nsample\n${BLOCK_END}`;
}
