// Capped, append-only audit of entries pruned from the session-memory store.
//
// The /remember store is short-lived and *deletes* on prune (TTL expiry,
// supersede-by-topic, cap). That is correct for the INJECT path — a new session
// must never see deprecated/superseded notes — but it loses replayability:
// "why did the store stop telling me about X?" This module keeps the *pruned*
// entries as an append-only, bounded trail so the removal is reconstructable.
//
// Deliberately:
//   - SEPARATE file (`.pi/factory/session-memory-audit.json`) so it never
//     collides with the store or --refresh regeneration.
//   - NEVER injected. The audit is a human/analyst record, not session context.
//   - APPEND-ONLY: pruned entries are added, never edited in place.
//   - CAPPED: bounded to a max entry count, dropping the OLDEST prunes first so
//     it cannot grow without bound while keeping the most recent reasoning.
//   - PURE, no Pi/Node beyond fs for IO, mirroring session-memory.ts.

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { MemoryNote } from "./session-memory.js";

export const AUDIT_SCHEMA = 1;
export const AUDIT_STEM = "session-memory-audit.json";
export const AUDIT_CAP_DEFAULT = 200;
export const DEFAULT_CONFIG_DIR = ".pi";

export type AuditReason = "expired" | "superseded" | "capped";

export interface AuditEntry {
  id: string; // original memory-note id
  topic: string;
  text: string;
  actor: string;
  created: string;
  expires: string | null;
  pruned_at: string; // when it was pruned (audit entry timestamp)
  reason: AuditReason;
}

export interface AuditFile {
  schema: number;
  entries: AuditEntry[];
}

export function auditPath(root: string, configDir = DEFAULT_CONFIG_DIR): string {
  return join(root, configDir, "factory", AUDIT_STEM);
}

export function emptyAudit(): AuditFile {
  return { schema: AUDIT_SCHEMA, entries: [] };
}

export function readAudit(root: string, configDir = DEFAULT_CONFIG_DIR): AuditFile {
  const p = auditPath(root, configDir);
  if (!existsSync(p)) return emptyAudit();
  try {
    const raw = JSON.parse(readFileSync(p, "utf-8")) as AuditFile;
    if (raw && Array.isArray(raw.entries) && raw.schema === AUDIT_SCHEMA) return raw;
    return emptyAudit();
  } catch {
    return emptyAudit(); // malformed -> treat as absent, don't guess
  }
}

export function writeAudit(root: string, file: AuditFile, configDir = DEFAULT_CONFIG_DIR): void {
  const p = auditPath(root, configDir);
  mkdirSync(dirname(p), { recursive: true });
  const data = JSON.stringify(file, null, 2) + "\n";
  const tmp = join(dirname(p), `.${AUDIT_STEM}.tmp-${process.pid}-${Date.now()}`);
  writeFileSync(tmp, data, "utf-8");
  renameSync(tmp, p);
}

/** Keep the NEWEST `max` entries by pruned_at (most recent prunes are most useful). Pure. */
export function capAudit(file: AuditFile, max: number): AuditFile {
  if (file.entries.length <= max) return file;
  const sorted = [...file.entries].sort(
    (a, b) => Date.parse(a.pruned_at) - Date.parse(b.pruned_at),
  );
  const keep = new Set(sorted.slice(sorted.length - max).map((e) => `${e.id}@${e.pruned_at}`));
  return {
    schema: file.schema,
    entries: file.entries.filter((e) => keep.has(`${e.id}@${e.pruned_at}`)),
  };
}

/**
 * Entries present in `before` but absent from `after` (matched by id). Pure.
 * This is the deterministic "what got pruned" diff used by the command layer.
 */
export function removedNotes(before: MemoryNote[], after: MemoryNote[]): MemoryNote[] {
  const afterIds = new Set(after.map((e) => e.id));
  return before.filter((e) => !afterIds.has(e.id));
}

/**
 * Append pruned notes to the audit (stamping pruned_at and reason), then cap.
 * Pure. `max` is the audit cap from the session-context policy.
 */
export function appendAudit(
  file: AuditFile,
  notes: { note: MemoryNote; reason: AuditReason }[],
  now: string,
  max: number,
): AuditFile {
  const stamped: AuditEntry[] = notes.map(({ note, reason }) => ({
    id: note.id,
    topic: note.topic,
    text: note.text,
    actor: note.actor,
    created: note.created,
    expires: note.expires,
    pruned_at: now,
    reason,
  }));
  return capAudit({ schema: file.schema, entries: [...file.entries, ...stamped] }, max);
}

/** Last `n` audit entries, newest first — for a read-only view. Pure. */
export function recentAudit(file: AuditFile, n: number): AuditEntry[] {
  return [...file.entries]
    .sort((a, b) => Date.parse(b.pruned_at) - Date.parse(a.pruned_at))
    .slice(0, n);
}
