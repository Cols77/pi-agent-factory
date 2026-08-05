import { mkdirSync, mkdtempSync, writeFileSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { listDocs } from "../src/doc-lister.js";

function makeRepo(root: string): void {
  mkdirSync(join(root, "docs", "superpowers", "specs"), { recursive: true });
  mkdirSync(join(root, "docs", "superpowers", "plans"), { recursive: true });
  mkdirSync(join(root, "tasks"), { recursive: true });

  writeFileSync(join(root, "docs", "superpowers", "specs", "2026-01-01-a-design.md"), "# A spec\n");
  writeFileSync(join(root, "docs", "superpowers", "plans", "2026-01-02-a.md"), "# A plan\n");
  writeFileSync(
    join(root, "tasks", "T-001-a.md"),
    "---\nid: T-001\ntitle: A task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
  );
  writeFileSync(join(root, "tasks", "T-002-b.md"), "not even frontmatter\n");

  // Make mtimes deterministic and distinguishable: spec oldest, task-001 middle, plan newest.
  const old = new Date("2026-01-01T00:00:00Z");
  const mid = new Date("2026-01-02T00:00:00Z");
  const newest = new Date("2026-01-03T00:00:00Z");
  utimesSync(join(root, "docs", "superpowers", "specs", "2026-01-01-a-design.md"), old, old);
  utimesSync(join(root, "tasks", "T-001-a.md"), mid, mid);
  utimesSync(join(root, "tasks", "T-002-b.md"), mid, mid);
  utimesSync(join(root, "docs", "superpowers", "plans", "2026-01-02-a.md"), newest, newest);
}

describe("listDocs", () => {
  test("lists specs, plans, and tasks, newest first", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-test-"));
    makeRepo(root);

    const docs = listDocs(root);

    expect(docs.map((d) => d.type)).toEqual(["plan", "task", "task", "spec"]);
    expect(docs[0]!.label).toBe("[plan] 2026-01-02-a.md");
  });

  test("formats a task label with id/title/status when frontmatter parses", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-test-"));
    makeRepo(root);

    const docs = listDocs(root);
    const task001 = docs.find((d) => d.path.endsWith("T-001-a.md"));
    expect(task001!.label).toBe("[task] T-001 -- A task (todo)");
  });

  test("falls back to the filename when a task's frontmatter doesn't parse", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-test-"));
    makeRepo(root);

    const docs = listDocs(root);
    const task002 = docs.find((d) => d.path.endsWith("T-002-b.md"));
    expect(task002!.label).toBe("[task] T-002-b.md");
  });

  test("returns an empty list when none of the three directories exist", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-empty-"));
    expect(listDocs(root)).toEqual([]);
  });
});

describe("listDocs requirements", () => {
  test("lists SR files alongside specs, plans and tasks", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-sr-"));
    makeRepo(root);
    mkdirSync(join(root, "requirements"), { recursive: true });
    writeFileSync(
      join(root, "requirements", "SR-001.md"),
      "---\nid: SR-001\ntitle: Preempt patrol\nstatement: s\ndomain: d\n---\n",
    );
    const labels = listDocs(root).map((d) => d.label);
    expect(labels).toContain("[req] SR-001 -- Preempt patrol");
  });
});
