// Deterministic, bounded context feeds for the session-context injector.
//
// Each feed is a pure-ish function root(+policy) -> markdown | null, plus a
// composer that assembles only the policy-enabled feeds into one bounded,
// as-of-dated block. Feeds are deliberately cheap and fail-fast-to-skip: the
// hook runs on every agent start, so no feed may take the session down or
// stall it — an error means "skip this feed this turn", never an exception.

import { execFileSync } from "node:child_process";
import { buildMemoryRollup, readMemory, type MemoryConfig } from "./session-memory.js";

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
