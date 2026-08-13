# Session-Continuity Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give later pi sessions a short-lived, bounded memory of *"where we were / what changed / what's next"* — written when a session ends, injected when a new one starts, and pruned so a new session is never told about deprecated or superseded notes.

**Architecture:** A pure, Pi-free store module (`session-memory.ts`) holds the retention logic (TTL + supersede-by-topic + hard cap) so it is unit-testable against a temp dir, mirroring the existing `factory-init.ts` split. A thin wiring module (`session-memory-command.ts`) registers `/remember`, a `session_shutdown` prune hook, and a `before_agent_start` inject hook. Stable facts stay in the `AGENTS.md` managed block; long-lived lessons stay in `kb/`; this is the volatile middle layer only.

**Tech Stack:** TypeScript + vitest for the pi extension; `node:fs` for atomic writes; the real `@earendil-works/pi-coding-agent` extension hooks `session_shutdown` and `before_agent_start` (verified present in `dist/core/extensions/types.d.ts`).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-14-session-memory-design.md`.
- **Pure core, thin glue.** All store/supersede/prune/inject logic is Pi-free and lives in `session-memory.ts`; `session-memory-command.ts` only calls it and touches pi APIs.
- **No transcripts.** What happened is logged explicitly (`/remember`); never dump raw session/message content into the store.
- **Deterministic.** Same store + inputs ⇒ same store and rollup. Prune is mechanical, no model.
- **Atomic + idempotent.** Writes go to a temp file then rename; a no-op prune rewrites nothing meaningful.
- **Hooks must not take the host down.** `session_shutdown` prune failures are swallowed.
- **Empty store ⇒ no injection.** An unbootstrapped repo is untouched by `before_agent_start`.
- **Commit after every task**, message `feat(watch): <snake_lower>`, ending `Co-Authored-By: ...`.
- **`npm --prefix pi-ext/factory-watch run typecheck` and `npm --prefix pi-ext/factory-watch test` green before commit; no skip.**

## File Structure

**Create**

| path | responsibility |
|---|---|
| `pi-ext/factory-watch/src/session-memory.ts` | pure store: types, `nextId`, `makeNote`, `pruneExpired`, `supersedeTopic`, `enforceCap`, `addNote`, `buildMemoryRollup`, `readMemory`/`writeMemory` |
| `pi-ext/factory-watch/src/session-memory-command.ts` | `/remember`; `session_shutdown` prune; `before_agent_start` inject |
| `pi-ext/factory-watch/test/session-memory.test.ts` | store + rollup unit tests |

**Modify**

| path | change |
|---|---|
| `pi-ext/factory-watch/src/pi-types.ts` | add `SessionShutdownEvent` + `on("session_shutdown", ...)` overload |
| `pi-ext/factory-watch/src/index.ts` | `registerSessionMemory(pi)` in the default export |

## Tasks

### Task 1 — Pure store module
- [x] Create `session-memory.ts` with `MemoryNote`, `SessionMemoryFile`, `MemoryConfig`, `MEMORY_DEFAULTS`, `memoryPath`, `emptyMemory`, `readMemory`/`writeMemory` (atomic), `nextId`, `makeNote`, `pruneExpired`, `supersedeTopic`, `enforceCap`, `addNote`, `buildMemoryRollup`.
- [x] **DoD:** `nextId` is gap-filling; `pruneExpired` drops only entries past `expires`; `supersedeTopic`/`addNote` retire the older live entry for a `topic` and keep `supersedes` for audit; `enforceCap` keeps the newest by `created`; `buildMemoryRollup` returns `null` for empty/fully-expired stores, is oldest-first, per-note-capped and budget-bounded, and as-of-dates every line.

### Task 2 — Command + hook wiring, `PiApi` extension
- [x] Add `SessionShutdownEvent` and the `on("session_shutdown", …)` overload to `pi-types.ts` (mirroring the existing `before_agent_start` overload style).
- [x] Create `session-memory-command.ts`: `/remember [--ttl <hours>] <topic>: <text>` writes via `addNote`; `session_shutdown` runs `pruneExpired`+`enforceCap` (swallow errors); `before_agent_start` appends `buildMemoryRollup` to `systemPrompt` and returns nothing when there is no rollup.
- [x] Wire `registerSessionMemory(pi)` into `index.ts`'s default export.
- [x] **DoD:** `tsc --noEmit` clean (including `type-compat-check.ts` pin against the real `ExtensionFactory`).

### Task 3 — Tests
- [x] Add `test/session-memory.test.ts` covering: id gap-filling; expired pruning; supersede (same topic, audit `supersedes`); cap keeps newest; `addNote` composes supersede+prune+cap over time; rollup null-on-empty, oldest-first, as-of-dated, never injects expired, budget-bounded.
- [x] **DoD:** `npx vitest run test/session-memory.test.ts` green; full `npm test` still green (no regressions in the existing 61 files).

### Task 4 — Policy + feeds (landed)
- [x] `session-policy.ts`: `SessionContext` (schema 1), `readContext`/`writeContext` in `.pi/factory/session-context.json`, `setFeed` (pure), `ALL_FEEDS=["memory","head"]`, defaults.
- [x] `session-feeds.ts`: `headFeed` (git branch/short HEAD/last N one-line commits, skip-on-error), `memoryFeed` (reuses store rollup), `ledgerFeed` (task-status counts + active tasks, direct fs), `traceHealthFeed` (opt-in, guarded so it never spawns the Python CLI on a non-factory repo), `composeContext` (assemble only enabled feeds, bounded, return included/skipped).
- [x] Wire policy into `session-memory-command.ts`: `before_agent_start` composes enabled feeds; `session_shutdown` prunes with policy caps; `/remember` respects memory-on/off; new `/factory-context` command (report + interactive feed toggle + non-interactive `on`/off).
- [x] `test/session-context.test.ts`: policy default/round-trip/toggle, headFeed null-on-non-git and content-on-git, composeContext include/skip gating.
- [x] **DoD:** `tsc --noEmit` clean; full `npm test` green (62 files / 729).

### Task 5 — Append-only audit trail (landed)
- [x] `session-audit.ts`: `AuditFile` (schema 1), `readAudit`/`writeAudit` in `.pi/factory/session-memory-audit.json`, `appendAudit` (stamp `pruned_at`+reason), `capAudit` (keep newest), `removedNotes` (id-diff), `recentAudit` (newest-first view).
- [x] `session-policy.ts`: `audit.maxEntries` (default 200).
- [x] `session-memory-command.ts`: `/remember` audits superseded/capped removals; `session_shutdown` prune audits expired/capped removals; `/factory-context --audit` shows the last 10.
- [x] `test/session-audit.test.ts`: round-trip, reason stamping, newest-keeping cap, id-diff, integration with the store's supersede.
- [x] **DoD:** `tsc --noEmit` clean; full `npm test` green.

## Out of scope (follow-ups, noted in the spec)
- Additional feeds beyond `memory`/`head`/`ledger`/`trace_health` — `composeContext` is feed-agnostic; add each as a deterministic `session-feeds.ts` function plus a policy entry.
- Auto per-session summary at shutdown (needs a summarizer + dedupe by `actor`/topic; risks transcript bloat — deliberate).
