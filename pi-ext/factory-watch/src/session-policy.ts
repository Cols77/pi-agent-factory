// Per-project, user-tunable policy for the session-context injection layer.
//
// This is the "interactivity lives once, determinism lives every turn" split:
// the human edits this policy (via /factory-context, writing this file), and the
// before_agent_start hook reads it without prompting. Deliberately a SEPARATE
// file from project-profile.json: /factory-init --refresh regenerates
// project-profile.json from evidence, so a hand-added key there would be wiped
// on the next refresh. This file is owned only by the session-context layer.
//
// Shape (schema 1):
//   enabledFeeds: which feeds inject into the next session's system prompt.
//   memory.*: retention + budget for the /remember continuity store.
//   head.*: git snapshot feed, "recent commits" line count.

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { MEMORY_DEFAULTS, type MemoryConfig } from "./session-memory.js";

export const CONTEXT_SCHEMA = 1;
export const CONTEXT_STEM = "session-context.json";
export const DEFAULT_CONFIG_DIR = ".pi";

export type FeedName = "memory" | "head" | "trace_health" | "ledger";

export interface SessionContext {
  schema: number;
  enabledFeeds: FeedName[];
  memory: MemoryConfig;
  head: { maxCommits: number };
  audit: { maxEntries: number };
  updated_at: string;
}

export const DEFAULT_CONTEXT: SessionContext = {
  schema: CONTEXT_SCHEMA,
  enabledFeeds: ["memory", "head", "ledger"],
  memory: { ...MEMORY_DEFAULTS },
  head: { maxCommits: 5 },
  audit: { maxEntries: 200 },
  updated_at: "",
};

export const ALL_FEEDS: FeedName[] = ["memory", "head", "ledger", "trace_health"];

export function contextPath(root: string, configDir = DEFAULT_CONFIG_DIR): string {
  return join(root, configDir, "factory", CONTEXT_STEM);
}

/** Whether a session-context policy file has been seeded yet. */
export function hasContext(root: string, configDir = DEFAULT_CONFIG_DIR): boolean {
  return existsSync(contextPath(root, configDir));
}

/**
 * A seed policy with exactly *feeds* enabled, everything else at defaults.
 * Used by /factory-init to write the very first session-context.json during
 * bootstrap (the human picks which streams inject into future sessions).
 */
export function seedContext(feeds: FeedName[]): SessionContext {
  const valid = feeds.filter((f): f is FeedName => ALL_FEEDS.includes(f as FeedName));
  return {
    ...DEFAULT_CONTEXT,
    memory: { ...DEFAULT_CONTEXT.memory },
    enabledFeeds: valid,
  };
}

/** Read the policy; return the deterministic default when absent/malformed. */
export function readContext(root: string, configDir = DEFAULT_CONFIG_DIR): SessionContext {
  const p = contextPath(root, configDir);
  if (!existsSync(p)) return { ...DEFAULT_CONTEXT, memory: { ...DEFAULT_CONTEXT.memory } };
  try {
    const raw = JSON.parse(readFileSync(p, "utf-8")) as Partial<SessionContext>;
    if (!raw || raw.schema !== CONTEXT_SCHEMA || !Array.isArray(raw.enabledFeeds)) {
      return { ...DEFAULT_CONTEXT, memory: { ...DEFAULT_CONTEXT.memory } };
    }
    const feeds = raw.enabledFeeds.filter((f): f is FeedName =>
      ALL_FEEDS.includes(f as FeedName),
    );
    return {
      schema: CONTEXT_SCHEMA,
      enabledFeeds: feeds,
      memory: { ...DEFAULT_CONTEXT.memory, ...(raw.memory ?? {}) },
      head: { maxCommits: raw.head?.maxCommits ?? DEFAULT_CONTEXT.head.maxCommits },
      audit: { maxEntries: raw.audit?.maxEntries ?? DEFAULT_CONTEXT.audit.maxEntries },
      updated_at: raw.updated_at ?? new Date().toISOString(),
    };
  } catch {
    return { ...DEFAULT_CONTEXT, memory: { ...DEFAULT_CONTEXT.memory } };
  }
}

export function writeContext(root: string, ctx: SessionContext, configDir = DEFAULT_CONFIG_DIR): void {
  const p = contextPath(root, configDir);
  mkdirSync(dirname(p), { recursive: true });
  const data = JSON.stringify({ ...ctx, updated_at: new Date().toISOString() }, null, 2) + "\n";
  const tmp = join(dirname(p), `.${CONTEXT_STEM}.tmp-${process.pid}-${Date.now()}`);
  writeFileSync(tmp, data, "utf-8");
  renameSync(tmp, p);
}

/** Toggle a feed on/off, returning the updated policy (pure). */
export function setFeed(ctx: SessionContext, feed: FeedName, enabled: boolean): SessionContext {
  const has = ctx.enabledFeeds.includes(feed);
  if (enabled === has) return ctx;
  const enabledFeeds = enabled
    ? [...ctx.enabledFeeds, feed]
    : ctx.enabledFeeds.filter((f) => f !== feed);
  return { ...ctx, enabledFeeds };
}

/**
 * Replace the enabled feed set with exactly *feeds* (preserving every other
 * setting). Unknown names are filtered. This is the "redefine the streams"
 * primitive behind /factory-context set|all|none -- a single-pass set, not a
 * one-at-a-time toggle.
 */
export function setFeeds(ctx: SessionContext, feeds: FeedName[]): SessionContext {
  const valid = feeds.filter((f): f is FeedName => ALL_FEEDS.includes(f as FeedName));
  return { ...ctx, enabledFeeds: valid };
}
