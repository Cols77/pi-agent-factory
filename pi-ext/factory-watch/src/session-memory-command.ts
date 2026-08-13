// Command + hook wiring for session continuity (the volatile bootstrap layer).
// Pure store/policy/feed logic lives in session-memory.ts, session-policy.ts and
// session-feeds.ts; this file only glues them to pi:
//
//   - /remember [--ttl <hours>] <topic>: <text>  -> explicit memory write.
//   - /factory-context                          -> interactive feed on/off +
//       policy report (the human-facing "what should be injected" control).
//   - session_shutdown hook                     -> "after session": persist +
//       prune the store using the policy caps.
//   - before_agent_start hook                   -> "next session": compose the
//       policy-enabled feeds and inject a bounded block into the system prompt.

import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import {
  MEMORY_DEFAULTS,
  addNote,
  enforceCap,
  pruneExpired,
  readMemory,
  writeMemory,
} from "./session-memory.js";
import {
  appendAudit,
  readAudit,
  recentAudit,
  removedNotes,
  writeAudit,
  type AuditReason,
} from "./session-audit.js";
import {
  ALL_FEEDS,
  DEFAULT_CONTEXT,
  readContext,
  setFeed,
  setFeeds,
  writeContext,
  type FeedName,
  type SessionContext,
} from "./session-policy.js";
import {
  composeContext,
  headFeed,
  memoryFeed,
} from "./session-feeds.js";

function parseRemember(args: string): { ttlHours?: number; text: string } {
  const ttl = /(^|\s)--ttl\s+(\d+)(\s|$)/.exec(args);
  const rest = args.replace(/(^|\s)--ttl\s+\d+/, " ").trim();
  return { ttlHours: ttl ? Number(ttl[2]) : undefined, text: rest };
}

/** Deterministic prune pass using the policy caps: drop expired + enforce count. */
function pruneStore(root: string, cfg: SessionContext): void {
  const now = new Date().toISOString();
  const file = readMemory(root);
  const pruned = enforceCap(pruneExpired(file, now), cfg.memory.maxEntries);
  writeMemory(root, pruned);
  // Audit: record what was removed (expired by TTL, else dropped by cap).
  const removed = removedNotes(file.entries, pruned.entries);
  if (removed.length === 0) return;
  const at = Date.parse(now);
  const notes = removed.map((note) => ({
    note,
    reason: (Date.parse(note.expires) <= at ? "expired" : "capped") as AuditReason,
  }));
  writeAudit(root, appendAudit(readAudit(root), notes, now, cfg.audit.maxEntries));
}

function formatContextReport(ctx: SessionContext): string[] {
  const lines = [`factory-context on (feeds: ${ctx.enabledFeeds.join(", ") || "(none)"})`];
  lines.push(`  memory:  ${ctx.enabledFeeds.includes("memory") ? "ON" : "off"} (ttl ${ctx.memory.ttlHours}h, max ${ctx.memory.maxEntries} notes, ${ctx.memory.maxTokens} tok rollup)`);
  lines.push(`  head:    ${ctx.enabledFeeds.includes("head") ? "ON" : "off"} (last ${ctx.head.maxCommits} commits)`);
  lines.push(`  ledger:  ${ctx.enabledFeeds.includes("ledger") ? "ON" : "off"} (task statuses, first 6 active)`);
  lines.push(`  trace_health (opt-in, slowest): ${ctx.enabledFeeds.includes("trace_health") ? "ON" : "off"}`);
  lines.push(`  audit: cap ${ctx.audit.maxEntries} (append-only; see /factory-context --audit)`);
  lines.push(`  available: ${ALL_FEEDS.join(", ")}`);
  lines.push(`  updated: ${ctx.updated_at ?? "(never)"}`);
  return lines;
}

export function registerSessionMemory(pi: PiApi): void {
  pi.registerCommand("remember", {
    description:
      "Log a short-lived note for future sessions: /remember [--ttl <hours>] <topic>: <text>. " +
      "Injected into later sessions (until TTL/superseded/cap) when the memory feed is on.",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const cctx = readContext(ctx.cwd);
      if (!cctx.enabledFeeds.includes("memory")) {
        ctx.ui.notify("memory feed is OFF — enable it with /factory-context before /remember", "warning");
      }
      const { ttlHours, text } = parseRemember(args);
      if (text.trim() === "") {
        ctx.ui.notify("usage: /remember [--ttl <hours>] <topic>: <text>", "error");
        return;
      }
      const colon = text.indexOf(":");
      const topic = (colon > 0 ? text.slice(0, colon) : "note").trim();
      const note = (colon > 0 ? text.slice(colon + 1) : text).trim();
      const now = new Date().toISOString();
      const file = readMemory(ctx.cwd);
      const next = addNote(file, { topic, text: note, actor: "manual", ttlHours }, cctx.memory, now);
      writeMemory(ctx.cwd, next);
      // Audit: the note about to be written may supersede a live one (and the
      // compose step may have capped/expired others) — record what was removed.
      const removed = removedNotes(file.entries, next.entries);
      if (removed.length > 0) {
        const wrote = next.entries[next.entries.length - 1];
        const supId = wrote?.supersedes ?? null;
        const notes = removed.map((n) => ({
          note: n,
          reason: (n.id === supId ? "superseded" : "capped") as AuditReason,
        }));
        writeAudit(ctx.cwd, appendAudit(readAudit(ctx.cwd), notes, now, cctx.audit.maxEntries));
      }
      const written = next.entries[next.entries.length - 1];
      ctx.ui.notify(
        written
          ? `remembered [${written.topic}] until ${written.expires.slice(0, 16).replace("T", " ")}`
          : "remembered (empty store)",
        "info",
      );
    },
  });

  pi.registerCommand("factory-context", {
    description:
      "Show/redefine which session-context feeds (streams) inject into future sessions: " +
      "/factory-context  (report) | <feed> (toggle) | set <f...> | all | none",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const tokens = args.trim().split(/\s+/).filter(Boolean);
      // Read-only audit view: the last pruned entries (newest first).
      if (tokens[0] === "--audit") {
        const entries = recentAudit(readAudit(ctx.cwd), 10);
        if (entries.length === 0) {
          ctx.ui.notify("audit: no pruned entries yet", "info");
          return;
        }
        for (const e of entries) {
          ctx.ui.notify(
            `[${e.pruned_at.slice(0, 16).replace("T", " ")}] ${e.reason}: ${e.topic} (${e.actor}) ${e.text}`,
            "info",
          );
        }
        return;
      }
      const cctx = readContext(ctx.cwd);
      if (tokens.length > 0) {
        const first = tokens[0];
        // Redefine the exact stream set (the "pick what injects" path).
        if (first === "set") {
          const feeds = tokens.slice(1) as FeedName[];
          writeContext(ctx.cwd, setFeeds(cctx, feeds));
          ctx.ui.notify(`factory-context set: streams → ${feeds.join(", ") || "(none)"}`, "info");
          return;
        }
        if (first === "none" || first === "off") {
          writeContext(ctx.cwd, setFeeds(cctx, []));
          ctx.ui.notify("factory-context: all streams off (nothing injected)", "info");
          return;
        }
        if (first === "all" || first === "on") {
          writeContext(ctx.cwd, setFeeds(cctx, ALL_FEEDS));
          ctx.ui.notify(`factory-context: all streams on (${ALL_FEEDS.join(", ")})`, "info");
          return;
        }
        // Backwards-compatible single-feed toggle.
        if (ALL_FEEDS.includes(first as FeedName)) {
          const on = !cctx.enabledFeeds.includes(first as FeedName);
          writeContext(ctx.cwd, setFeed(cctx, first as FeedName, on));
          ctx.ui.notify(`factory-context: ${first} stream ${on ? "ON" : "off"}`, "info");
          return;
        }
        ctx.ui.notify(
          `usage: /factory-context [set <f...> | all | none | <feed> | --audit]  (feeds: ${ALL_FEEDS.join(", ")})`,
          "error",
        );
        return;
      }
      // Interactive: multi-select to redefine the whole stream set.
      if (ctx.hasUI) {
        let feeds = cctx.enabledFeeds;
        for (;;) {
          const selection = await ctx.ui.select(
            "Redefine context streams (flip each, then done)",
            [
              ...ALL_FEEDS.map((f) => `${f} (${feeds.includes(f) ? "ON" : "off"})`),
              ALL_FEEDS.join(","),
              "none",
              "done",
            ],
          );
          if (selection === undefined || selection === "done") break;
          if (selection === "none") {
            feeds = [];
            ctx.ui.notify("factory-context: all streams off (choose again or done)", "info");
            continue;
          }
          if (selection === ALL_FEEDS.join(",")) {
            feeds = [...ALL_FEEDS];
            ctx.ui.notify("factory-context: all streams on (choose again or done)", "info");
            continue;
          }
          const name = selection.split(" ")[0] as FeedName;
          feeds = feeds.includes(name) ? feeds.filter((f) => f !== name) : [...feeds, name];
        }
        writeContext(ctx.cwd, setFeeds(cctx, feeds));
        ctx.ui.notify(`factory-context: streams → ${feeds.join(", ") || "(none)"}`, "info");
        return;
      }
      for (const l of formatContextReport(cctx)) ctx.ui.notify(l, "info");
    },
  });

  // "After session": tend the store (prune expired + enforce cap per policy) so
  // a new session is never told about deprecated/superseded/capped notes.
  pi.on("session_shutdown", (_event, ctx) => {
    try {
      pruneStore(ctx.cwd, readContext(ctx.cwd));
    } catch {
      // A prune failure must never take the host session down at shutdown.
    }
  });

  // "Next session": compose the enabled feeds into a bounded block.
  pi.on("before_agent_start", (event, ctx) => {
    const cctx = readContext(ctx.cwd);
    if (cctx.enabledFeeds.length === 0) return;
    const { markdown } = composeContext(
      ctx.cwd,
      cctx.enabledFeeds,
      cctx.memory,
      cctx.head.maxCommits,
      new Date().toISOString(),
    );
    if (!markdown) return;
    return { systemPrompt: event.systemPrompt + "\n\n" + markdown + "\n" };
  });
}

// Re-exported for tests/consumers.
export { headFeed, memoryFeed, DEFAULT_CONTEXT, MEMORY_DEFAULTS };
