# FEAT-13 — Government Execution Driver (GOVERNED-EXECUTION-DRIVER)

_Status: **design dossier** (2026-08-27). Owner: mcp-adapter HOST driver (Hermes side) over the
existing Python factory orchestrator. This is the runtime side of the `subagent-increment-workflow`
skill — today run ad-hoc by hand; FEAT-13 makes it enforced + traced. Planning/design only.

_Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (FEAT-13
proposal; locked decisions D-A…D-H). Companion runbook:
`docs/superpowers/plans/2026-08-27-coherence-execution-runbook.md`._

## 1. Purpose

Let a **host (Hermes)** execute the Inc-09 plans (or any coherence-governed plan) as a **deterministic,
traced run**, with **free/Hermes subagents as the worker nodes** (dev per worktree, parallel
spec-compliance + code-quality reviewers, fresh-context fixers-until-silent), where **every gate,
trace edge, human-review interrupt, and evidence write is enforced by the Python backend**, not
improvised by the host.

## 2. The decisive discovery (grounded in source)

**The governed loop ALREADY EXISTS in the Python backend.** Reading:
- `src/factory/orchestrator/nodes.py` — `run_context_gatherer`, `run_dev`, `run_validation`,
  `run_review`, `run_session_review`; node states `running/pass/fail/escalate/reject/already-done`;
  gates run via a `GateRunner` (`gates.run_detail("unit")` etc).
- `src/factory/orchestrator/backends.py` — the **`AgentBackend` protocol**:
  `run(role: AgentRole, prompt, on_snippet=None, on_session_id=None) -> AgentResult`.
  This is THE seam. Any host (Pi today, Hermes tomorrow) implements it.
- `src/factory/orchestrator/runner.py` — `TaskResult`, `HumanReviewGate`, `GrillGate`, KB selection
  (`select_kb`), `finalize_run_evidence`, `write_run_manifest`, `SubprocessGitOps`. The whole loop.
- `src/factory/orchestrator/pi_backend.py` — a deprecated wrapper re-exporting `substrate.agents.backend.PiAgentBackend`
  (role-scoped). Proof a provider-backend pattern already exists.
- `src/factory/orchestrator/types.py` — `AgentRole { CONTEXT_GATHERER, DEV, VALIDATION, REVIEW,
  SESSION_REVIEW, SYNTHESIS, COVERAGE_AUDIT }`; `NodeOutcome`, `NodeEvent`, `TaskResult`.
- `src/coherence/runs/transport.py` + `model.py` — `ObservationEnvelope` run/session canonical records.
- `src/coherence/gate/*`, `coherence/inbox.py`, `coherence/register/*`, `coherence/policy/compiler.py`
  — the canonical reads the driver/gate consume.
- **No MCP server exists yet** (grep confirmed). FEAT-9's `coherence-mcp` is the other half.

**Conclusion:** the *enforcement* is NOT something FEAT-13 builds — it must NOT build enforcement.
FEAT-13 is **two thin additions**: (a) a host-side `AgentBackend` implementation that speaks to
Hermes/free subagents, and (b) an **orchestration driver** (CLI or MCP-server shell) that: picks a
worktree per task, boots the runner with a Hermes backend, runs the reviewers in parallel, runs the
fixers until silent, streams progress, and surfaces human-review gates. Enforcement stays in Python.

## 3. Guiding constraints (locked, carry from capture)

- **D-B: enforcement lives in the Python factory**, never in a host loop. MCP exposes; backend
  enforces; driver orchestrates.
- **Thin-adapter:** the driver and MCP only surface canonical verbs (`resolve_cmd`, transitions, reads)
  + wire free workers → reviewers → fixers into the node states the backend reports.
- **D-D: every artifact carries codemap `satisfies`/`implements` edges** — the driver's job includes
  ensuring each produced file's edge is present before a gate lets the run advance; the backend
  register/obligation gate validates it.
- **Replaceable host/agent (HLR-01 / D1):** the AgentBackend seam is exactly what keeps agents and
  hosts pluggable. Hermes becomes ONE more backend; Pi remains primary. No fork.
- **Human-review is a real gate (dim 0/0):** the driver must surface review requests, not auto-pass.

## 4. Architecture

```
[Hermes host]  --MCP tools (F13)-->  [coherence-mcp server (F9)]
      |                                        |
      |  free subagents (workers)              |  canonical JSON reads: status/route/obligations
      |  dev wrk, reviewer swarm, fixers       |  + transition verbs (resolve_cmd)
      v                                        v
[ HermesAgentBackend ][  WorktreeDriver  ] -> [ Python factory.orchestrator (the authority) ]
       implements AgentBackend.run()           node pipeline, HumanReviewGate, gates, evidence, git
                                                  registers/traces/obligation-checks (D-D)
```

**The two new Python-adjacent pieces (host side, no new authority):**

### 4a. `HermesAgentBackend` (implements `AgentBackend`)
- Same signature as `PiAgentBackend`: `run(role, prompt, on_snippet, on_session_id) -> AgentResult`.
- Spawns a free/Hermes subagent per role via the existing `moa_worker.py`/`hermes chat --query-file`
  machinery; 429-fallback pool order = nemotron → (glm-5.2 fallback); DeepSeek as the cheap review gate.
- Maps `AgentRole.REVIEW` to a **swarm**: the driver dispatches TWO independent review subagents
  (spec-compliance + code-quality/security) in parallel; both must report clean before the node
  advances. `SYNTHESIS`/`SESSION_REVIEW` compose their outputs.
- Streams `on_snippet` (live progress, FEAT-12) and `on_session_id` to the host.

### 4b. `WorktreeDriver` (orchestration entry)
- Entry point: `coherence run-governed --plan <plan-file> [--task <id>] [--worktree <dir>] [--models ...]`.
- Per task: create/enter a worktree off main → provision `.venv` (`uv sync`) → run the nodes with the
  Hermes backend → run reviewers in parallel → fixers until silent → **coherence gate** (`register
  check`, `navigate health`, codemap-edge grep) → scoped commit → next task.
- Streams transitions to a console (FEAT-12/console) + writes `ObservationEnvelope` journal entries.
- Standalone reuse of the existing `runner.py` loop, or thin orchestration around `nodes.py` functions.

### 4c. MCP server shell (`coherence-mcp`, shared with FEAT-9)
- Tools (thin, backend-gated): `run_governed`, `status`, `route`, `obligations`, `resolve`, `decision`,
  `human_review_await`. All call the canonical Python surface; none re-implement.
- This is the Hermes-side adapter that lets the driver be driven from a chat session.

## 5. Scope (one tracer-bullet through every layer)

Vertical: substrate AgentBackend/ActionResult → factory orchestrator nodes/gates → coherence
register/trace/obligation → HermesAgentBackend (new) → WorktreeDriver (new) → MCP tools (shared F9)
→ console/driver CLI. Build **one end-to-end task** so the whole governed loop is exercised.

### Task G-01 — Confirm the backend seam + free-model pool
- Verify `AgentBackend` protocol shape; confirm `mos_worker.py`/`hermes chat` still spawns. Note
  ox-alpha DEAD → pool = nemotron(+glm fallback). **Verify:** a single `AgentResult` round-trip.

### Task G-02 — `HermesAgentBackend.run(role,...)`
- Implement `AgentBackend` for Hermes/forest: per-role prompt → `hermes chat --query-file` →
  parse `AgentResult` (raw, session_id, interruption). Map role→scope via `ROLE_SCOPE`.
- **Verify:** `run(AgentRole.DEV, prompt)` returns a real `AgentResult` with session_id; 429-fallback
  rotates; a context-limit interruption is classified (`InterruptionReason.CONTEXT_LIMIT`).

### Task G-03 — Review swarm + fixer-until-silent in the driver
- Driver dispatches TWO review subagents (spec + code-quality) on a task; both report files on disk
  (never trust exit codes); if either has findings -> fresh-context fixer (only those) -> re-review
  until both silent. Map to `run_review`/`run_session_review` states.
- **Verify:** a task with a seeded defect is caught by ≥1 reviewer, fixed, re-reviewed clean; the
  node states reflect pass only after both silent.

### Task G-04 — Worktree driver boot + coherence gate
- `coherence run-governed` per task in its own worktree (+ venv). After fixers: run `coherence
  register check`, `coherence navigate health --json`, codemap-edge grep on touched files; block on
  any failing gate. `HumanReviewGate` surfaces and waits (doesn't auto-pass).
- **Verify:** a task that violates D-D (no codemap edge) is blocked at the gate, not committed.

### Task G-05 — MCP tools (shared with FEAT-9) + console stream
- MCP tools: run_governed/status/route/obligations/resolve/decision/human_review_await; live progress
  streamed (SSE) to the console (reuse FEAT-12 stream; `runs/transport.py` `ObservationEnvelope`).
- **Verify:** a governed run is drivable from a Hermes session via MCP; progress streams; a
  human-review blocks until a decision is written.
- **Acceptance/exactly:** `coherence run-governed` on one task from the health-resolution plan
  completes end-to-end (worktree → dev → 2 reviewers → fixer → gate → commit) with all gates green,
  all evidence + trace edges on disk, human-review explicit.

## 6. Files likely to change (planned)

- New: `src/coherence/driver/backend_hermes.py` (HermesAgentBackend), `src/coherence/driver/run_governed.py`
  (WorktreeDriver + CLI), `src/coherence/driver/review_swarm.py`, `coherence-mcp` server (F9-shared),
  tests under `tests/` (unit + integration per task).
- Modify/reuse: `src/factory/orchestrator/{runner,nodes,backends,roles}.py` (reuse, mostly read-only;
  only add a registration hook if `ROLE_SCOPE` must know new Hermes roles — unlikely), `substrate/agents/model.py`.
- No new enforcement logic; no new node types unless swarming needs a documented extension.

## 7. Traceability requirement (D-D)

- HermesAgentBackend + WorktreeDriver + MCP tools each carry codemap edges to their FEAT-13 SR
  (created in health-resolution T-2/T-3, like FEAT-10's). The gate validates them; the review node saw
  the artifact-sufficiency. No green-by-declaration.

## 8. Risks & open questions

- **Swarming maps to existing single-role `REVIEW`** — must confirm `run_review` can accept a
  multi-reviewer verdict (or the driver runs two `run_review` passes and ANDs them). Document the
  exact extension.
- **Free-model reliability** — 429 is the dominant failure (ox-alpha already dead). The driver must
  treat free reviewers as "eventually succeeds"; never trust exit codes — require on-disk reports.
- **MCP is one half (F9)** — this driver depends on `coherence-mcp` existing or being scoped with F9;
  sequence F9 (server shell) before/with G-05.
- **Worktree venv** — fresh worktrees have no `.venv`; the driver must provision it (`uv sync`), and
  handle Windows native paths.
- **Does swarming change `AgentRole`?** Likely not (roles stay DEV/REVIEW/SYNTHESIS); the swarm is a
  driver-level fan-out, not a new node type. Confirm with a test before adding any new role.

## 9. Definition of done

`coherence run-governed` (locally or over MCP) executes a coherence-governed plan task end-to-end:
worktree spawned + provisioned, dev on a free worker, **two independent reviewers both clean,
fixer until silent**, all backend gates run (register check, navigate health, codemap edges), a real
`human_review` entry recorded, artifacts committed on the feature branch (never pushed without the
user). Enforcement was entirely the Python factory's; the driver only orchestrated + streamed + gated.
