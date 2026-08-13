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
  ALL_FEEDS,
  DEFAULT_CONTEXT,
  readContext,
  setFeed,
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
  writeMemory(root, enforceCap(pruneExpired(file, now), cfg.memory.maxEntries));
}

function formatContextReport(ctx: SessionContext): string[] {
  const lines = [`factory-context on (feeds: ${ctx.enabledFeeds.join(", ") || "(none)"})`];
  lines.push(`  memory:  ${ctx.enabledFeeds.includes("memory") ? "ON" : "off"} (ttl ${ctx.memory.ttlHours}h, max ${ctx.memory.maxEntries} notes, ${ctx.memory.maxTokens} tok rollup)`);
  lines.push(`  head:    ${ctx.enabledFeeds.includes("head") ? "ON" : "off"} (last ${ctx.head.maxCommits} commits)`);
  lines.push(`  ledger:  ${ctx.enabledFeeds.includes("ledger") ? "ON" : "off"} (task statuses, first 6 active)`);
  lines.push(`  trace_health (opt-in, slowest): ${ctx.enabledFeeds.includes("trace_health") ? "ON" : "off"}`);
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
      "Show and toggle which session-context feeds inject into future sessions: /factory-context [memory|head]",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const arg = args.trim();
      if (arg !== "" && (ALL_FEEDS.includes(arg as FeedName) || arg === "all")) {
        // Non-interactive toggle: turn the named feed(s) on for all, or off via
        // "off", determined by the current state for a single named feed.
        const cctx = readContext(ctx.cwd);
        if (arg === "all") {
          const next: SessionContext = { ...cctx, enabledFeeds: [...ALL_FEEDS] };
          writeContext(ctx.cwd, next);
          ctx.ui.notify(`factory-context: all feeds enabled (${ALL_FEEDS.join(", ")})`, "info");
        } else {
          const feedName = arg as FeedName;
          const on = !cctx.enabledFeeds.includes(feedName);
          writeContext(ctx.cwd, setFeed(cctx, feedName, on));
          ctx.ui.notify(`factory-context: ${feedName} feed ${on ? "ON" : "off"}`, "info");
        }
        return;
      }
      // Interactive: toggle any subset of feeds via a multi-select.
      const cctx = readContext(ctx.cwd);
      if (ctx.hasUI) {
        const selection = await ctx.ui.select("Toggle context feeds (choose one to flip)", [
          ...ALL_FEEDS.map((f) => `${f} (${cctx.enabledFeeds.includes(f) ? "ON" : "off"})`),
          ALL_FEEDS.join(","),
          "done",
        ]);
        if (selection === undefined || selection === "done") {
          for (const l of formatContextReport(readContext(ctx.cwd))) ctx.ui.notify(l, "info");
          return;
        }
        const name = selection.split(" ")[0] as FeedName;
        const on = !cctx.enabledFeeds.includes(name);
        writeContext(ctx.cwd, setFeed(cctx, name, on));
        ctx.ui.notify(`factory-context: ${name} feed ${on ? "ON" : "off"}`, "info");
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
