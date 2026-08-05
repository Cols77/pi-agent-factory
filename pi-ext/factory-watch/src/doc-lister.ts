import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { parseReqFrontmatter, parseTaskFrontmatter } from "./task-header.js";

export interface DocEntry {
  type: "spec" | "plan" | "task" | "req";
  label: string;
  path: string;
  mtimeMs: number;
}

function listMarkdownFiles(dir: string): string[] {
  try {
    return readdirSync(dir).filter((f) => f.endsWith(".md"));
  } catch {
    return [];
  }
}

function buildTaskLabel(path: string, file: string): string {
  try {
    const parsed = parseTaskFrontmatter(readFileSync(path, "utf-8"));
    if (parsed) {
      return `[task] ${parsed.id} -- ${parsed.title} (${parsed.status})`;
    }
  } catch {
    // fall through to filename fallback
  }
  return `[task] ${file}`;
}

function buildReqLabel(path: string, file: string): string {
  try {
    const parsed = parseReqFrontmatter(readFileSync(path, "utf-8"));
    if (parsed) {
      return `[req] ${parsed.id} -- ${parsed.title}`;
    }
  } catch {
    // fall through to filename fallback
  }
  return `[req] ${file}`;
}

export function listDocs(repoRoot: string): DocEntry[] {
  const entries: DocEntry[] = [];

  const specsDir = join(repoRoot, "docs", "superpowers", "specs");
  for (const file of listMarkdownFiles(specsDir)) {
    const path = join(specsDir, file);
    entries.push({ type: "spec", label: `[spec] ${file}`, path, mtimeMs: statSync(path).mtimeMs });
  }

  const plansDir = join(repoRoot, "docs", "superpowers", "plans");
  for (const file of listMarkdownFiles(plansDir)) {
    const path = join(plansDir, file);
    entries.push({ type: "plan", label: `[plan] ${file}`, path, mtimeMs: statSync(path).mtimeMs });
  }

  const tasksDir = join(repoRoot, "tasks");
  for (const file of listMarkdownFiles(tasksDir).filter((f) => f.startsWith("T-"))) {
    const path = join(tasksDir, file);
    entries.push({
      type: "task",
      label: buildTaskLabel(path, file),
      path,
      mtimeMs: statSync(path).mtimeMs,
    });
  }

  const reqsDir = join(repoRoot, "requirements");
  for (const file of listMarkdownFiles(reqsDir).filter((f) => f.startsWith("SR-"))) {
    const path = join(reqsDir, file);
    entries.push({
      type: "req",
      label: buildReqLabel(path, file),
      path,
      mtimeMs: statSync(path).mtimeMs,
    });
  }

  return entries.sort((a, b) => b.mtimeMs - a.mtimeMs);
}
