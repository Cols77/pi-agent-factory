// Command + hook wiring for the session-continuity memory (the volatile
// bootstrap layer). All retention/store logic is pure and lives in
// session-memory.ts; this file only glues it to pi:
//
//   - /remember [--ttl <hours>] <text>  -> explicit write path (logs a note a
//     later session should be aware of).
//   - session_shutdown hook             -> the "after session" half: persist
//     + prune. Pruning (drop expired, supersede-free is handled at write, cap)
//     runs here so the file that stores old-of-age claims is cleaned so a new
//     session is not told about deprecated/unrelevant notes. Content is only
//     ever logged EXPLICITLY (/remember), never dumped from transcripts.
//   - before_agent_start hook           -> the "next session" half: read the
//     pruned store and inject a bounded rollup into the next system prompt.

import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import {
  MEMORY_DEFAULTS,
  addNote,
  buildMemoryRollup,
  pruneExpired,
  enforceCap,
  readMemory,
  writeMemory,
  type MemoryConfig,
} from "./session-memory.js";

function resolveCfg(): MemoryConfig {
  // Overridable later from a project-profile "session_context" policy block.
  // Deterministic defaults for the prototype.
  return { ...MEMORY_DEFAULTS };
}

function parseRemember(args: string): { ttlHours?: number; text: string } {
  const ttl = /(^|\s)--ttl\s+(\d+)(\s|$)/.exec(args);
  const rest = args.replace(/(^|\s)--ttl\s+\d+/, " ").trim();
  return { ttlHours: ttl ? Number(ttl[2]) : undefined, text: rest };
}

/** Deterministic prune pass: drop expired entries and enforce the count cap. */
function pruneStore(root: string, cfg: MemoryConfig): void {
  const now = new Date().toISOString();
  const file = readMemory(root);
  writeMemory(root, enforceCap(pruneExpired(file, now), cfg.maxEntries));
}

export function registerSessionMemory(pi: PiApi): void {
  const cfg = resolveCfg();

  pi.registerCommand("remember", {
    description:
      "Log a short-lived note for future sessions: /remember [--ttl <hours>] <topic>: <text>. " +
      "Next sessions get it injected (until TTL/superseded/cap).",
    handler: async (args: string, ctx: ExtCommandCtx) => {
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
      const next = addNote(file, { topic, text: note, actor: "manual", ttlHours }, cfg, now);
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

  // "After session": persist any writes and prune deprecated/unrelevant entries so
  // a new session is never told about notes that have expired or been superseded
  // past the cap. Runs on every shutdown reason (quit/reload/new/resume/fork).
  // Writing notes is explicit (/remember); this hook only tends the store.
  pi.on("session_shutdown", (_event, ctx) => {
    try {
      pruneStore(ctx.cwd, cfg);
    } catch {
      // A prune failure must never take the host session down at shutdown.
    }
  });

  // "Next session": inject the fresh, bounded rollup into the system prompt.
  // Returns nothing (no injection) when the store is empty/absent, so an
  // unbootstrapped repo is untouched.
  pi.on("before_agent_start", (event, ctx) => {
    const rollup = buildMemoryRollup(readMemory(ctx.cwd), new Date().toISOString(), cfg);
    if (!rollup) return;
    return { systemPrompt: event.systemPrompt + "\n\n" + rollup + "\n" };
  });
}
