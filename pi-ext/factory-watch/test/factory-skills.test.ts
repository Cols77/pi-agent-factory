import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { factorySkillsDir, findSkillFile } from "../src/factory-skills.js";

function repoWithSkill(name: string): string {
  const root = mkdtempSync(join(tmpdir(), "skills-"));
  mkdirSync(join(root, ".pi", "skills", name), { recursive: true });
  writeFileSync(join(root, ".pi", "skills", name, "SKILL.md"), "---\nname: x\n---\nbody\n");
  return root;
}

describe("factorySkillsDir", () => {
  test("points at the factory's own vendored skills", () => {
    // The extension ships with the factory repo, so its skills are always
    // reachable even when the target project vendors none.
    expect(factorySkillsDir()).toContain(join(".pi", "skills"));
    expect(findSkillFile(mkdtempSync(join(tmpdir(), "empty-")), "trace-fix")).not.toBeNull();
  });
});

describe("findSkillFile", () => {
  test("prefers the target project's own copy when it has one", () => {
    const root = repoWithSkill("trace-fix");
    expect(findSkillFile(root, "trace-fix")).toBe(
      join(root, ".pi", "skills", "trace-fix", "SKILL.md"),
    );
  });

  test("falls back to the factory's copy when the project vendors none", () => {
    // cool_physical_ai_project has an empty .pi/, so without this fallback
    // /trace-fix could never run in the project that actually has requirements.
    const empty = mkdtempSync(join(tmpdir(), "empty-"));
    const found = findSkillFile(empty, "trace-fix");
    expect(found).toBe(join(factorySkillsDir(), "trace-fix", "SKILL.md"));
  });

  test("falls back per-skill, not per-directory", () => {
    // The real failure: main has 12 vendored skills but not trace-fix, so a
    // directory-level "does the project vendor skills?" check would wrongly
    // conclude the project's copy should win and then fail to find the file.
    const root = repoWithSkill("brainstorming");
    expect(findSkillFile(root, "brainstorming")).toBe(
      join(root, ".pi", "skills", "brainstorming", "SKILL.md"),
    );
    expect(findSkillFile(root, "trace-fix")).toBe(
      join(factorySkillsDir(), "trace-fix", "SKILL.md"),
    );
  });

  test("returns null for a skill that exists in neither place", () => {
    const empty = mkdtempSync(join(tmpdir(), "empty-"));
    expect(findSkillFile(empty, "no-such-skill")).toBeNull();
  });
});
