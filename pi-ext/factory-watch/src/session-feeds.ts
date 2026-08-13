// Deterministic, bounded context feeds for the session-context injector.
//
// Each feed is a pure-ish function root(+policy) -> markdown | null, plus a
// composer that assembles only the policy-enabled feeds into one bounded,
// as-of-dated block. Feeds are deliberately cheap and fail-fast-to-skip: the
// hook runs on every agent start, so no feed may take the session down or
// stall it — an error means "skip this feed this turn", never an exception.

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { buildMemoryRollup, readMemory, type MemoryConfig } from "./session-memory.js";
import { runTraceCheck } from "./trace-cli.js";
import { parseTaskFrontmatter } from "./task-header.js";

/** git branch + HEAD + last N one-line commits. Deterministic and quick. */
export function headFeed(root: string, maxCommits: number, now: string): string | null {
  try {
    const head = execFileSync("git", ["rev-parse", "--short", "HEAD"], {
      cwd: root, encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const branch = execFileSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
      cwd: root, encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"],
    }).trim() || "(detached)";
    const log = execFileSync(
      "git", ["log", `-n${maxCommits}`, "--pretty=format:%h %s"],
      { cwd: root, encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"] },
    ).trim();
    if (!head) return null;
    const commits = (log ? log.split("\n") : []).map((l) => `  - ${l}`).join("\n");
    return [
      `# Git head (as of ${now.slice(0, 16).replace("T", " ")})`,
      `branch: ${branch}  HEAD: ${head}`,
      commits ? `recent commits (last ${maxCommits}):\n${commits}` : "(no commits yet)",
    ].join("\n");
  } catch {
    return null; // not a git repo, or git unavailable -> skip the feed
  }
}

/** memory feed: the /remember continuity rollup (reuses the store's logic). */
export function memoryFeed(root: string, cfg: MemoryConfig, now: string): string | null {
  return buildMemoryRollup(readMemory(root), now, cfg);
}

const FACTORY_MARKERS = [".factory/factory.yaml", "requirements"];

/**
 * ledger feed: current task statuses, read directly from tasks/T-*.md (cheap,
 * no subprocess). Lists the active (non-done) tasks with counts across statuses.
 */
export function ledgerFeed(root: string, now: string, maxTasks: number): string | null {
  const tasksDir = join(root, "tasks");
  if (!existsSync(tasksDir)) return null;
  let names: string[];
  try {
    names = readdirSync(tasksDir);
  } catch {
    return null;
  }
  const rows: { id: string; title: string; status: string }[] = [];
  const counts: Record<string, number> = {};
  for (const name of names) {
    if (!name.endsWith(".md") || !name.startsWith("T-")) continue;
    let content: string;
    try {
      content = readFileSync(join(tasksDir, name), "utf-8");
    } catch {
      continue;
    }
    const parsed = parseTaskFrontmatter(content);
    if (!parsed) continue;
    counts[parsed.status] = (counts[parsed.status] ?? 0) + 1;
    if (parsed.status !== "done") {
      rows.push({ id: parsed.id, title: parsed.title, status: parsed.status });
    }
  }
  if (rows.length === 0 && Object.keys(counts).length === 0) return null;
  const summary = Object.keys(counts)
    .sort()
    .map((s) => `${s}: ${counts[s]}`)
    .join(" · ");
  const active = rows
    .slice(0, maxTasks)
    .map((r) => `  - ${r.id} (${r.status}) ${r.title}`)
    .join("\n");
  return [
    `# Task ledger (as of ${now.slice(0, 16).replace("T", " ")})`,
    summary || "(no tasks)",
    active ? `${rows.length > maxTasks ? `active (${rows.length}, first ${maxTasks}):` : `active:`}\n${active}` : "no active tasks",
    "(detail via /factory-tasks or /factory-run)",
  ].join("\n");
}

/**
 * trace_health feed: open traceability gap counts (opt-in; the slowest feed).
 * Guards on the repo looking like a factory target FIRST so a non-factory repo
 * (and a unit-test temp dir) skips without ever spawning the Python CLI.
 */
export function traceHealthFeed(root: string, now: string): string | null {
  const looksLike = FACTORY_MARKERS.some((m) => existsSync(join(root, m)));
  if (!looksLike) return null;
  try {
    const check = runTraceCheck(root);
    return [
      `# Trace health (as of ${now.slice(0, 16).replace("T", " ")})`,
      `open gaps: ${check.pending} · deferred: ${check.deferred} · exempt: ${check.exempt} · gate: ${check.ok ? "passes" : "FAILS"}`,
      "(drill down via /trace-fix or /system)",
    ].join("\n");
  } catch {
    return null; // Python CLI unavailable -> skip the feed this turn
  }
}

export interface ComposedContext {
  markdown: string | null;
  included: string[]; // which feeds actually produced content
  skipped: string[]; // enabled feeds that produced nothing / failed
}

/**
 * Assemble the enabled feeds into one bounded block for injection. Returns
 * null when nothing of the enabled feeds produced content (an unbootstrapped or
 * quiet repo is untouched). The per-feed caps keep the whole block bounded.
 */
export function composeContext(
  root: string,
  enabledFeeds: string[],
  memoryCfg: MemoryConfig,
  maxCommits: number,
  now: string,
): ComposedContext {
  const parts: string[] = [];
  const included: string[] = [];
  const skipped: string[] = [];

  for (const feed of enabledFeeds) {
    let block: string | null = null;
    if (feed === "head") block = headFeed(root, maxCommits, now);
    else if (feed === "memory") block = memoryFeed(root, memoryCfg, now);
    else if (feed === "trace_health") block = traceHealthFeed(root, now);
    else if (feed === "ledger") block = ledgerFeed(root, now, 6);
    if (block) {
      parts.push(block);
      included.push(feed);
    } else {
      skipped.push(feed);
    }
  }

  if (parts.length === 0) return { markdown: null, included, skipped };
  const markdown =
    "# Session context (volatile — from session-context.json feeds; verify before acting)\n\n" +
    parts.join("\n\n");
  return { markdown, included, skipped };
}
