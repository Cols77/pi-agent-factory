# PIF and Browser Evidence Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the PIF coding agent and browser one shared, live view of run evidence, freshness, publication, and interrupted-run recovery through deterministic Python commands.

**Architecture:** Add thin TypeScript clients over the evidence/preflight/run-state CLIs, then extend the existing docs server and browser with task evidence and recovery endpoints. The extension owns presentation and explicit command routing only; Python remains the sole parser and policy engine. Initial live updates use bounded polling.

**Tech Stack:** TypeScript, Node built-in HTTP/fs/child_process, existing inline browser UI, Vitest, Python JSON CLIs.

## Global Constraints

- TypeScript must not duplicate freshness, reconciliation, or resume policy.
- Browser data is read-only except narrow Python-validated commands.
- All servers remain loopback-only and path-confined.
- Missing optional blobs render an honest degraded state.
- Polling stops when the page/extension closes; no orphan intervals.
- Existing `/review-plans`, `/factory-watch`, terminal review, and browser review remain compatible.

---

## File Structure

**Create:**
- `pi-ext/factory-watch/src/evidence-client.ts` — Python CLI wrappers and shared types.
- `pi-ext/factory-watch/src/system-context-tools.ts` — PIF tools over evidence/preflight.
- `pi-ext/factory-watch/test/evidence-client.test.ts`
- `pi-ext/factory-watch/test/system-context-tools.test.ts`

**Modify:**
- `pi-ext/factory-watch/src/docs-server.ts` — evidence, preflight, reconcile, and run-state routes.
- `pi-ext/factory-watch/src/docs-html.ts` — task implementation/evidence and recovery panes.
- `pi-ext/factory-watch/src/index.ts` — register tools/commands and focus browser on active run.
- `pi-ext/factory-watch/src/process-control.ts` — evidence/preflight command builders if not contained in client.
- existing tests for docs server/page, handlers, and smoke loading.

### Task 1: Typed evidence/preflight/run-state client

**Interfaces:**

```typescript
export type CliResult<T> = { ok: true; value: T } | { ok: false; error: string; status: number };
export interface EvidenceRun { /* exact evidence schema fields */ }
export interface FreshnessIssue { code: string; severity: "integrity"|"blocking"|"warning"; subject: string; dependency: string; detail: string; repair: string|null }
export interface ReconcileItem { kind: string; subject: string; detail: string; repairable: boolean; source: string }
export interface RecoveryAssessment { state: "resumable"|"inspect-only"|"conflict"|"complete"; reasons: string[]; actions: string[] }

export function loadTaskEvidence(cwd: string, taskId: string): CliResult<{runs: EvidenceRun[]}>;
export function runPreflight(cwd: string, taskId: string): CliResult<{issues: FreshnessIssue[]}>;
export function runReconcile(cwd: string, taskId?: string): CliResult<{items: ReconcileItem[]}>;
export function loadCurrentRun(cwd: string): CliResult<unknown>;
export function requestRunAction(cwd: string, runId: string, action: "resume"|"abandon", reason?: string): CliResult<unknown>;
```

- [ ] Mock `spawnSync` and test exact commands, 64 MiB buffer, JSON parsing, non-zero structured output, malformed JSON, and executable-not-found.
- [ ] Implement one private `runJson(cwd, module, args)`; wrappers contain no domain policy.
- [ ] Run typecheck/tests and commit `feat(factory-watch): add evidence lifecycle client`.

### Task 2: Browser server APIs

Routes:

```text
GET  /api/evidence/task?task=T-042
GET  /api/preflight?task=T-042
GET  /api/reconcile?task=T-042
GET  /api/run-state
POST /api/run-state/<run-id>/resume
POST /api/run-state/<run-id>/abandon   {"reason":"..."}
GET  /api/artifact/<sha256>
```

- `/api/artifact` serves only a hash referenced by a manifest returned for the current repository; it verifies the object hash before response.
- action POSTs require exact JSON, call Python, and return its structured status.
- action endpoints reject missing/blank abandonment reason.
- routes remain loopback-only and never accept repository paths.

- [ ] Add server tests for every route, method rejection, unknown hash, hash mismatch, and command failure.
- [ ] Refactor route helpers out of `docs-server.ts` into focused functions if the file exceeds one clear responsibility; do not alter existing graph/doc behavior.
- [ ] Implement routes and commit `feat(factory-watch): serve project evidence and recovery state`.

### Task 3: Task implementation and validation view

On task navigation, render these sections beneath the document:

1. implementation runs newest-first;
2. code commit/start commit and changed files;
3. review rounds with decisions/comments and patch link;
4. validation entries with status and stale reasons;
5. publication status and missing blobs;
6. reconciliation gaps.

The current `/api/reviews` runtime-history panel becomes a fallback only when no
durable evidence manifest exists. Label it `local legacy review history`.

- [ ] Extend `docs-html.test.ts` assertions for every section and provenance label (`recorded`, `derived`, `missing`).
- [ ] Add browser DOM construction using `createTextNode` for all evidence data; only existing escaped Markdown renderer output may use `innerHTML`.
- [ ] Color states consistently with trace validation and provide text labels independent of color.
- [ ] Poll active task evidence every two seconds only while an active run exists; ignore stale responses after navigation.
- [ ] Commit `feat(browser): show durable task implementation evidence`.

### Task 4: Interrupted-run recovery panel

When `/api/run-state` reports a non-complete run, show:

```text
Interrupted run · T-042 · validation
State: resumable
Reasons: process ended after dev checkpoint
[Inspect evidence] [Resume] [Abandon]
```

- Resume requires confirmation and displays Python conflict/inspect-only reasons without mutating UI state optimistically.
- Abandon requires a non-empty rationale textarea and confirmation.
- Inspect opens the task/evidence view at the checkpoint run.
- No automatic browser action occurs after reboot.

- [ ] Add static-page tests for controls and client-side decision guards.
- [ ] Add server integration tests proving resume/abandon call only Python wrappers.
- [ ] Implement and commit `feat(browser): recover interrupted factory runs`.

### Task 5: PIF system-context tools

Register read-only tools:

```text
system_context      {id: string}
implementation_history {task_id: string}
validation_status  {id: string}
evidence_health    {task_id?: string}
```

For this foundation:

- `system_context` returns the exact graph node, declared one-hop neighbors, freshness issues, and task evidence references;
- `implementation_history` wraps task evidence;
- `validation_status` filters declared requirement validation entries;
- `evidence_health` wraps reconciliation.

Tool descriptions explicitly tell the model that missing data is unknown, not an
invitation to infer. No write/resume tool is exposed to the model in this plan.

- [ ] Add fake `PiApi` registration tests and response-format tests.
- [ ] Implement tools using `evidence-client.ts` and existing trace CLI only.
- [ ] Register in `index.ts`; verify extension smoke loading.
- [ ] Commit `feat(factory-watch): give PIF grounded system evidence tools`.

### Task 6: Command integration and complete verification

- Add `/system` as a general browser entry point while retaining `/review-plans`.
- `/factory-watch` opens the same server focused by query string on the active run/task when browser preference is selected; terminal mission control remains available.
- Browser server singleton reuse must reject a different repository root rather than accidentally serving the first repo's data.
- `/system --stop` uses the same server lifecycle.

- [ ] Add handler tests for focus URLs, aliases, stop, server-root mismatch, and browser-open failure.
- [ ] Update extension README command table.
- [ ] Run `npm test`, `npm run typecheck`, Python tests for CLI contracts, and real browser smoke verification.
- [ ] Commit `feat(factory-watch): integrate the system evidence navigator`.

## Plan Self-review

- Every UI/API path consumes deterministic Python output.
- Existing review and document surfaces remain compatible.
- Natural-language synthesis and final feature briefing are intentionally deferred.
- Recovery writes require explicit human actions; coding-agent tools remain read-only.
