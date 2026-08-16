// Durable session-continuity memory for pi-agent-factory.
//
// The write/prune half of the volatile bootstrap layer (see docs/project-bootstrap.md
// §6 and the design plan). The stable project facts stay in AGENTS.md; the KEYLESS
// long-lived lessons learned stay in kb/ (written by the session-review role). This
// module is the short-lived, *stateful* middle layer: "where we were / what changed
// this session / next step", with the three retention controls that stop it degrading
// into a pile of stale claims:
//
//   1. TTL  - each "log" entry carries an expiry; expired entries never reach a new
//             session's prompt (the "old enough -> irrelevant" pruning).
//   2. supersede - writing a note with the same `topic` retires the older live entry,
//             so the injectable view can never surface two conflicting "latest" facts
//             about the same subject (age alone would leave the stale one in).
//   3. hard cap - bounded entry count / token budget so the file and the injected
//             rollup cannot grow without bound.
//
// The module is deliberately PURE (no Pi / Node types beyond fs for IO): the
// store/supersede/prune/inject logic is unit-testable against a temp dir the same way
// factory-init.ts is. The command + hook wiring that glues it to /remember,
// session_shutdown and before_agent_start lives in session-memory-command.ts.
//
// Contract rules enforced here rather than in prose:
//   - evidence of *what happened* is logged EXPLICITLY (a /remember command or a
//     persist_note tool), never by dumping transcripts. Raw transcript logging is
//     bloat + a stale-continuity hazard, and is deliberately not supported.
//   - deterministic: the same store + inputs always produce the same store/rollup.
//   - atomic writes (temp file + rename), idempotent (no rewrite when unchanged).

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export const MEMORY_SCHEMA = 1;
export const MEMORY_STEM = "session-memory.json";
export const DEFAULT_CONFIG_DIR = ".pi";

export interface MemoryNote {
  id: string;
  kind: "log"; // only "log" lives in this short-lived store; kb entries route to kb/ instead
  topic: string; // grouping key for supersede, e.g. "task:T-042" or "decision:<slot>"
  created: string; // ISO timestamp
  expires: string; // ISO timestamp; never null here because "log" is always short-lived
  actor: string; // who logged it: a session id, "manual", or ttl-tagged source
  text: string; // concise note (the thing a later session should be aware of)
  supersedes: string | null; // id this entry retires, if any (kept for audit)
}

export interface SessionMemoryFile {
  schema: number;
  entries: MemoryNote[];
}

export interface MemoryConfig {
  ttlHours: number; // default TTL applied when a note doesn't specify one
  maxEntries: number; // hard cap on entry count after prune/supersede
  maxTokens: number; // token budget for the injected rollup
  maxNoteTokens: number; // per-note token cap so one long note can't blow the rollup
}

export const MEMORY_DEFAULTS: MemoryConfig = {
  ttlHours: 24,
  maxEntries: 50,
  maxTokens: 400,
  maxNoteTokens: 160,
};

// ---------------------------------------------------------------------------
// Paths / IO
// ---------------------------------------------------------------------------

export function memoryPath(root: string, configDir = DEFAULT_CONFIG_DIR): string {
  return join(root, configDir, "factory", MEMORY_STEM);
}

export function emptyMemory(): SessionMemoryFile {
  return { schema: MEMORY_SCHEMA, entries: [] };
}

export function readMemory(root: string, configDir = DEFAULT_CONFIG_DIR): SessionMemoryFile {
  const p = memoryPath(root, configDir);
  if (!existsSync(p)) return emptyMemory();
  try {
    const raw = JSON.parse(readFileSync(p, "utf-8")) as SessionMemoryFile;
    if (raw && Array.isArray(raw.entries) && raw.schema === MEMORY_SCHEMA) return raw;
    return emptyMemory();
  } catch {
    return emptyMemory(); // malformed -> treat as absent, don't guess
  }
}

export function writeMemory(root: string, file: SessionMemoryFile, configDir = DEFAULT_CONFIG_DIR): void {
  const p = memoryPath(root, configDir);
  mkdirSync(dirname(p), { recursive: true });
  const data = JSON.stringify(file, null, 2) + "\n";
  const tmp = join(dirname(p), `.${MEMORY_STEM}.tmp-${process.pid}-${Date.now()}`);
  writeFileSync(tmp, data, "utf-8");
  renameSync(tmp, p);
}

// ---------------------------------------------------------------------------
// Pure retention + store logic
// ---------------------------------------------------------------------------

const ISO_RE = /^\d{4}-\d{2}-\d{2}T/;

function ids(file: SessionMemoryFile): Set<string> {
  return new Set(file.entries.map((e) => e.id));
}

/** Deterministic next free "sm-NNNN" id (gap-filling, not just max+1). */
export function nextId(file: SessionMemoryFile): string {
  let n = 1;
  const used: Record<string, boolean> = {};
  for (const e of file.entries) used[e.id] = true;
  while (used[`sm-${String(n).padStart(4, "0")}`]) n++;
  return `sm-${String(n).padStart(4, "0")}`;
}

function parseIso(s: string): number {
  return ISO_RE.test(s) ? Date.parse(s) : NaN;
}

/** Drop entries whose expiry has passed. Pure. */
export function pruneExpired(file: SessionMemoryFile, now: string): SessionMemoryFile {
  const at = Date.parse(now);
  if (Number.isNaN(at)) return file;
  return { schema: file.schema, entries: file.entries.filter((e) => parseIso(e.expires) > at) };
}

/** Retire the live entry sharing `topic` (the new note supersedes it). Pure. */
export function supersedeTopic(file: SessionMemoryFile, topic: string, now: string): SessionMemoryFile {
  const at = Date.parse(now);
  const live = pruneExpired(file, now); // don't supersede an already-dead topic
  const others = live.entries.filter(
    (e) => !(e.topic === topic && parseIso(e.expires) > at),
  );
  return { schema: live.schema, entries: others };
}

/** Bound entry count by dropping the oldest (by created) first. Pure. */
export function enforceCap(file: SessionMemoryFile, maxEntries: number): SessionMemoryFile {
  if (file.entries.length <= maxEntries) return file;
  const sorted = [...file.entries].sort((a, b) => parseIso(a.created) - parseIso(b.created));
  const keep = new Set(sorted.slice(sorted.length - maxEntries).map((e) => e.id));
  return { schema: file.schema, entries: file.entries.filter((e) => keep.has(e.id)) };
}

export interface AddNoteInput {
  topic: string;
  text: string;
  actor: string;
  ttlHours?: number;
  created?: string; // ISO; defaults to now()
  kind?: "log";
}

/** Build a fresh note (no supersede/cap applied yet). Pure. */
export function makeNote(file: SessionMemoryFile, input: AddNoteInput, cfg: MemoryConfig, now: string): MemoryNote {
  const created = input.created ?? now;
  const ttl = input.ttlHours ?? cfg.ttlHours;
  const expires = new Date(Date.parse(created) + ttl * 3600_000).toISOString();
  const retired = file.entries.find(
    (e) => e.topic === input.topic && parseIso(e.expires) > Date.parse(now),
  );
  return {
    id: nextId(file),
    kind: input.kind ?? "log",
    topic: input.topic,
    created,
    expires,
    actor: input.actor,
    text: input.text,
    supersedes: retired?.id ?? null,
  };
}

/** Compose supersede + prune + cap into one deterministic store update. Pure. */
export function addNote(
  file: SessionMemoryFile,
  input: AddNoteInput,
  cfg: MemoryConfig,
  now: string,
): SessionMemoryFile {
  const note = makeNote(file, input, cfg, now);
  let next = supersedeTopic(file, note.topic, now);
  next = { schema: next.schema, entries: [...next.entries, note] };
  return enforceCap(pruneExpired(next, now), cfg.maxEntries);
}

// ---------------------------------------------------------------------------
// Injectable rollup (the forward-injection read side)
// ---------------------------------------------------------------------------

function approxTokens(s: string): number {
  return Math.max(1, Math.ceil(s.length / 4));
}

/**
 * Render the fresh (non-expired) notes as a compact, bounded markdown block for
 * injection into a later session's system prompt. Returns null when there is
 * nothing a new session should be told. Deterministic: oldest first, cap-
 * respecting, per-note token capped. Each line carries its expiry so the reader
 * knows the note is "as of <time>", not a permanent fact.
 */
export function buildMemoryRollup(
  file: SessionMemoryFile,
  now: string,
  cfg: MemoryConfig,
): string | null {
  const fresh = pruneExpired(file, now);
  if (fresh.entries.length === 0) return null;
  const ordered = [...fresh.entries].sort((a, b) => parseIso(a.created) - parseIso(b.created));
  const lines: string[] = [];
  let budget = cfg.maxTokens;
  for (const e of ordered) {
    if (budget <= 0) break;
    let text = e.text;
    if (approxTokens(text) > cfg.maxNoteTokens) {
      text = text.slice(0, cfg.maxNoteTokens * 4) + "…";
    }
    const line = `- [${e.topic}] (${e.actor}, until ${e.expires.slice(0, 16).replace("T", " ")}) ${text}`;
    budget -= approxTokens(line);
    if (budget < 0 && lines.length > 0) break;
    lines.push(line);
  }
  if (lines.length === 0) return null;
  return ["# Session continuity (from session-memory.json — volatile, as-of-dated)",
    "Fresh notes a prior session deliberately left for this one. Verify before acting on them; detailed state is on disk / on-demand.",
    ...lines,
  ].join("\n");
}
