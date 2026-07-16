# Design: Deterministic Multi-Agent Development Factory

**Date:** 2026-07-16
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

The umbrella project is a **Physical Agentic AI**: a shark-detection drone for the
Australian coast that perceives, reasons, acts (flight/actuators), and warns
swimmers/authorities. The guiding philosophy is **"fix the agent, not the product"** —
the primary showcased capability is the *development system* that builds the drone, not
just the drone itself.

Accordingly, **this spec covers the development system** (the "factory"), which is the
first deliverable. The drone product is designed *by* and *through* this factory and is
scoped separately (see §11 for its roadmap, retained here as downstream context).

### 1.1 Goals

- A **deterministic, multi-agent build-time executor** that consumes plan-time tasks and
  drives them to "done" through: context verification → TDD implementation → functional
  validation → code review → session reporting → knowledge accrual.
- **Determinism where it matters:** the *orchestration graph, routing, context loading,
  skill loading, and gates* are deterministic (code + exit codes + fixed manifests).
  Inference lives strictly *inside* agent nodes.
- **Reproducible session continuity:** any run can be resumed reliably from files.
- **A knowledge base** that prevents repeating known mistakes.
- **Portability:** built on the Pi coding-agent framework with a pluggable model backend
  (Claude now → local model later), so nothing is Claude-Code-exclusive.

### 1.2 Non-Goals (this spec)

- Building the drone's CV, navigation, or hardware layers (separate specs; §11).
- Adopting Hermes Agent's inference-driven memory now (deferred; §12).
- Rebuilding plan-time. Brainstorm/spec/plan is delegated to the existing **superpowers**
  workflow (§3).

---

## 2. Core Principles

1. **Code drives, models think inside nodes.** No LLM decides routing. Transitions are
   functions of validation-script **exit codes**.
2. **Deterministic boundaries around non-deterministic work.** An agent may reason freely,
   but it must emit a **structured artifact** that a script validates (schema + referential
   integrity). A PASS is impossible while any deterministic gate (tests/lint/types) is red —
   no LLM can self-certify past a failing gate.
3. **Resolve-once, load-deterministically.** Judgment about *what context is needed* happens
   once (Context-Gatherer, LLM, iterative). *Loading* that resolved set is deterministic and
   reproducible.
4. **Skills are loaded by role, not chosen by the model.** Each agent has a fixed skill
   manifest injected at spawn.
5. **Interfaces over rewrites.** Model backend, and later the whole agent runtime, sit behind
   stable interfaces (proven pattern reused from the drone's `FlightController`/`Planner`).
6. **Fail safe, not forever.** Every loop has a circuit breaker that escalates to a human.

---

## 3. The Plan-time / Build-time Boundary

```
PLAN-TIME  (superpowers, human-in-the-loop)
   brainstorming → writing-plans (+ reviewer prompts)
   Output (files):  specs/*.md   plan.md   tasks/T-*.md  (each: tests-first intent + DoD)
════════════════════════════════ handoff is files only ════════════════════════════════
BUILD-TIME (Pi-based deterministic executor — THIS spec)
   consumes tasks/, produces code + tests + session logs + KB updates
```

Plan-time is **not** rebuilt inside the executor. The executor's only "planning" interaction
is **rejecting a task back to plan-time** when the Context-Gatherer cannot prove coherence.

---

## 4. Architecture Overview

```
                         ┌─────────────────────────────────────────────┐
                         │  ORCHESTRATOR (deterministic, Pi SDK / RPC)  │
                         │  • task ledger   • context injection         │
                         │  • runs gates    • routes on exit codes      │
                         │  • circuit breakers • model-backend config   │
                         └───────────────┬─────────────────────────────┘
                                         │ spawns fresh sub-agent per node
   ┌──────────────┬──────────────┬───────┴───────┬──────────────┬──────────────┐
   ▼              ▼              ▼               ▼              ▼              ▼
Context-       Dev            Validation      Review        Session-       KB-Manager
Gatherer      (TDD)          (functional)    (structured)  Writer         (built last)
   │              │              │               │              │              │
   └──── each: fixed skill manifest + fixed tool/permission profile + injected manifest ──┘

STORES (plain files, deterministic):
   tasks/            context-manifests/     sessions/            kb/
```

- **Orchestrator:** TypeScript on the **Pi** framework (SDK for embedding; RPC/JSON mode as
  fallback for process integration). Owns the state machine, the task ledger, context
  injection, gate execution, routing, circuit breakers, and model-backend selection.
- **Agents:** each a fresh Pi **sub-agent** invocation with (a) a role system prompt,
  (b) a deterministically-injected context manifest, (c) a fixed skill manifest, (d) a
  restricted permission/path profile (e.g., Review is read-only; Session-Writer may write
  only under `sessions/`).
- **Gates:** standalone scripts (`scripts/gates/*`) returning exit codes. The orchestrator
  never trusts agent prose for routing — only gate results.
- **Model backend:** Pi's multi-provider config. `anthropic` now; `ollama:<model>` later.
  Zero orchestrator changes to switch.

---

## 5. The Pipeline (nodes, contracts, routing)

Routing is a pure function of gate exit codes. `↺` denotes a circuit-breaker-bounded loop.

```
task ← ledger.next()
  │
  ▼
[Context-Gatherer] ── LLM, iterative ↺ until coherence PROVEN
  │   emits: context-manifests/<task>.json  (proof + resolved context set)
  │   gate: manifest schema valid AND all referenced paths exist
  │   └─ cannot prove coherence → REJECT task back to plan-time (human)
  ▼
[Dev] ── loads manifest deterministically; TDD (red→green); consults KB
  │   gate: unit tests green + lint + types  ↺(dev) until green or breaker
  ▼
[Validation] ── functional / headless-sim tests
  │   gate: functional suite green
  │   └─ fail → back to [Dev] ↺
  ▼
[Review] ── LLM emits structured report {principles[], dod_met, findings[]}
  │   gate: report schema valid AND (dod_met ⇒ all deterministic gates green)
  │   └─ changes-requested → back to [Dev] ↺
  ▼
[Session-Writer] ── appends machine session record + regenerates human summary
  ▼
[KB-append] ── Dev-surfaced lessons appended (curation deferred to KB-Manager)
  ▼
ledger.mark(task, done)

CIRCUIT BREAKER (per task): iterations > N  →  mark ESCALATED, log, stop task, surface to human.
```

**Note on the two reviews you described (YAGNI/DRY, then DoD):** collapsed into one Review
node emitting a two-section structured report, gated deterministically. Split into two nodes
only if evidence shows they interfere (YAGNI).

---

## 6. Agents: responsibilities & deterministic skill manifests

`★` = custom skill we author; others already exist in superpowers 6.1.1.

| Agent | Responsibility | Deterministic skill manifest | Permission profile |
|---|---|---|---|
| **Context-Gatherer** | Iterate until it can *prove* spec/plan/prior-session/task are coherent and context is complete; emit manifest or reject | `verification-before-completion`, ★`context-completeness-audit` | read-only + write `context-manifests/` |
| **Dev** | Deterministically load manifest; TDD red→green; consult KB; act on review findings | `test-driven-development` (+`testing-anti-patterns`), `systematic-debugging` (+`root-cause-tracing`,`defense-in-depth`,`condition-based-waiting`), `receiving-code-review`, ★`kb-lookup`, ★ domain skills (`flight-controller-iface`, `sim-harness`) | write `src/`, `tests/`; run bash |
| **Validation** | Run functional/headless-sim suite; assert against DoD's observable criteria | `verification-before-completion`, `condition-based-waiting`, ★`sim-functional-tests` | read + run bash (no source writes) |
| **Review** | Emit structured report: coding principles (YAGNI/DRY) + DoD verdict | `requesting-code-review`/`code-reviewer` persona, `verification-before-completion`, ★`coding-principles` | read-only |
| **Session-Writer** | Append machine record; regenerate human resume summary | ★`session-report` | write `sessions/` only |
| **KB-Manager** *(built last)* | Append new lessons; propose (human-gated) prunes | ★`kb-curation` | write `kb/` only |
| *Plan-time* | Brainstorm → spec → plan | `brainstorming`, `writing-plans` (+ reviewer prompts); reference model `subagent-driven-development` | human-in-loop |

---

## 7. Context Manifest Schema

Produced by the Context-Gatherer (LLM judgment), validated by a script (determinism).

```json
{
  "task_id": "T-012",
  "generated_by": "context-gatherer",
  "generated_at": "2026-07-16T14:32:10Z",
  "coherence": {
    "proven": true,
    "checks": [
      {"name": "task-exists-in-plan",           "pass": true, "evidence": "plan.md#T-012"},
      {"name": "spec-plan-consistent",          "pass": true, "evidence": "spec§4 ↔ plan step 4"},
      {"name": "dod-present-and-clear",         "pass": true, "evidence": "tasks/T-012.md#dod"},
      {"name": "no-contradiction-prior-session","pass": true, "evidence": "sessions/…#T-011"}
    ]
  },
  "context": {
    "spec":          ["docs/superpowers/specs/2026-07-16-…-design.md#build-time"],
    "plan":          ["docs/superpowers/plans/…#T-012"],
    "task":          "tasks/T-012.md",
    "prior_session": "sessions/2026-07-15T…Z.session.json",
    "source_files":  ["src/flight/pybullet_adapter.py"],
    "kb_entries":    ["kb-0001"],
    "skills":        ["test-driven-development", "systematic-debugging", "kb-lookup"]
  },
  "reject": null
}
```

Rejection form (routes back to plan-time):

```json
{ "task_id": "T-012", "coherence": {"proven": false},
  "reject": {"reason": "DoD absent; acceptance criteria unmeasurable",
             "conflicts": ["plan.md#T-012 assumes CV oracle removed in T-009"]} }
```

**Gate:** JSON schema valid · `coherence.proven === true` · every path in `context.*` exists.

---

## 8. Knowledge Base Schema (proposed)

Design intent: **deterministic retrieval** (glob/substring, no semantic guessing in v1),
**append-first**, **human-gated deletion**. One file per entry under `kb/`.

```markdown
---
id: kb-0001
title: "PyBullet drone not armed before goto → silent no-op"
status: active            # active | superseded | archived
severity: high            # high | medium | low
created: 2026-07-16
last_seen: 2026-07-16
occurrences: 3
tags: [pybullet, flight-controller, arming, async]
scope:
  files: ["src/flight/**", "src/sim/**"]           # glob → path-based retrieval
  error_signatures:                                 # substring → error-based retrieval
    - "AssertionError: altitude did not increase"
    - "vehicle not armed"
detection: scripts/kb_checks/kb-0001.sh             # optional deterministic reproduction check
---

## Symptom
`goto()` returns success but the drone never leaves the ground.

## Root cause
Adapter issues position setpoints before the arm/takeoff handshake completes.

## Rule / fix
Await `armed && mode==OFFBOARD` before the first setpoint. See `flight-controller-iface`.
```

**Retrieval (deterministic, done by orchestrator, injected to Dev):** given the task's
touched-file globs and any error signatures observed in the current Dev iteration, select
entries whose `scope.files` glob-match or whose `error_signatures` substring-match. No LLM
in the selection path.

**Index:** `kb/index.json` (generated) maps tags/globs/signatures → ids for O(1) lookup;
regenerated by a script whenever `kb/` changes.

**Curation guardrail:** KB-Manager may **append** and **mark superseded/archived**, but
**hard deletion requires a human-approved prune** (`status` change is reversible; deletion is
not). This prevents silent loss of hard-won lessons.

---

## 9. Session-Log Schema (proposed)

Two artifacts per run: a **machine record** (authoritative, for deterministic resume) and a
**human summary** (regenerated, for readability).

`sessions/<ISO8601>.session.json`:

```json
{
  "session_id": "2026-07-16T14-30-00Z",
  "started_at": "2026-07-16T14:30:00Z",
  "ended_at":   "2026-07-16T15:12:40Z",
  "model_backend": "anthropic:claude-opus-4-8",
  "git": {"branch": "build/T-012", "base": "abc1234", "head": "def5678"},
  "tasks": [
    {
      "task_id": "T-012",
      "title": "PyBullet FlightController.goto() reaches waypoint",
      "outcome": "completed",                 // completed | rejected | escalated
      "iterations": 2,
      "nodes": [
        {"node": "context-gather", "result": "pass", "attempts": 1,
         "artifact": "context-manifests/T-012.json"},
        {"node": "dev",        "result": "pass", "attempts": 2, "tests": "12/12",
         "kb_hits": ["kb-0001"]},
        {"node": "validation", "result": "pass", "attempts": 1},
        {"node": "review",     "result": "changes-requested", "attempts": 1, "findings": 3},
        {"node": "dev",        "result": "pass", "attempts": 1, "tests": "12/12"},
        {"node": "review",     "result": "pass", "attempts": 1}
      ],
      "commits": ["def5678"],
      "dod": {"met": true, "checklist": ["waypoint reached ±0.5m", "battery decremented"]}
    }
  ],
  "kb_changes": {"added": ["kb-0007"], "updated": ["kb-0001"], "pruned": []},
  "escalations": [],
  "resume": {
    "next_task": "T-013",
    "hint": "T-012 done; oracle still emits ground-truth detections; CV not yet integrated"
  }
}
```

`sessions/latest.md`: human-readable digest regenerated each run (what happened, what's next).

**Resume contract:** the next Context-Gatherer reads the newest `*.session.json`
deterministically (not the markdown), reconstructing exact state: last completed task,
open escalations, KB deltas, and the `resume.hint`.

---

## 10. Pi Integration & Model Portability

- **Orchestrator** uses Pi's **SDK** (embed the agent loop in our TS driver). Pi's
  **RPC/JSON mode** is the fallback if we prefer an out-of-process boundary.
- **Per-agent controls we rely on:** Pi **sub-agents** (role isolation), **permission
  gates** + **path protection** (enforce the per-agent write scopes in §6), **plan mode**
  where useful, **sandboxing** for bash gates.
- **Skills** are injected per sub-agent as fixed manifests (the orchestrator supplies them;
  the model never selects them).
- **Model backend** via Pi's multi-provider support: `anthropic` today; switch to
  `ollama:<hermes-or-qwen-tools>` later with a config change — the pipeline is unchanged.
- **Maturity risk:** Pi is young (late 2025). Mitigation: pipeline logic lives in *our*
  orchestrator + scripts + skills; Pi is the replaceable agent-loop substrate. If Pi
  regresses, the same manifests/gates can drive another loop (e.g., Claude Agent SDK).

---

## 11. Downstream: the Drone Product Roadmap (context only)

Built *through* the factory, in vertical slices, each behind stable interfaces
(`FlightController`, `Planner`, `Perception`):

- **Phase 1 — Walking skeleton (no CV).** `gym-pybullet-drones` behind `FlightController`;
  LLM-driven high-level nav (goto/heading/RTB); autonomous return-to-base on low battery;
  geofence/loop-closure; agent reacts to a **perception oracle** (sim ground-truth
  detections) — "get closer to inspect." Fully validatable against deterministic ground truth.
- **Phase 2 — Real perception.** Swap oracle for a pretrained detector on the rendered
  camera feed (shark/dolphin models); ambiguity reasoning; "get closer to confirm."
- **Phase 3 — Real hardware (stretch).** Same `FlightController` API → PX4/MAVSDK or a small
  quad. Ground-station topology (agent on a nearby car GPU / server), so no on-device
  inference constraint.

The **co-bootstrap** first slice (Milestone 0, §13) uses the trivial
**takeoff → hover → land** scenario so the factory has real (tiny) code to gate from commit #1.

---

## 12. Deferred / Out of Scope

- **Hermes Agent runtime.** Its inference-driven self-improving memory conflicts with the
  determinism requirement for KB/session. We *borrow ideas* (persistent memory, learning
  loop) but implement stores as deterministic files. Revisit if a learned-memory layer
  proves worth the nondeterminism.
- **KB-Manager auto-curation** beyond append + supersede. Hard prune stays human-gated.
- **Splitting Review into two agents.** One node until evidence demands two.
- **Local model backend** (Ollama/Hermes-model). Interface is ready; switch is Phase-later.

---

## 13. Phasing of the Factory Itself

- **Milestone 0 — Co-bootstrap (minimal loop + thin product).**
  Orchestrator + these nodes only: Context-Gatherer → Dev → Validation → Review →
  Session-Writer. Gates: ruff, pyright, pytest, headless-sim smoke. Product skeleton:
  the three interfaces + `gym-pybullet-drones` adapter + **takeoff/hover/land** scenario.
  KB present but read-only (seeded manually); no KB-Manager.
- **Milestone 1 — Knowledge base live.** ★`kb-lookup` in Dev; deterministic retrieval;
  append on Dev-surfaced lessons.
- **Milestone 2 — KB-Manager + circuit-breaker tuning + resume hardening.**
- **Milestone 3 — Model-backend swap trial** (Claude → local) to prove portability.

Each factory milestone is itself a plan-time → build-time cycle (dogfooding).

---

## 14. Testing & Validation of the Factory

- **Gate scripts** are unit-tested in isolation (given fixture repo states, assert exit codes).
- **Schema validators** (manifest, KB entry, session record) have positive/negative fixtures.
- **End-to-end dry run:** a canned trivial task must traverse the full graph to a green
  session record, deterministically, twice, with identical routing.
- **Circuit-breaker test:** an intentionally unsatisfiable task must escalate within N
  iterations, not loop forever.

---

## 15. Open Questions

1. **Orchestrator language/boundary:** Pi SDK (in-process TS) vs Pi RPC (out-of-process).
   Leaning SDK; confirm after a Pi spike.
2. **Task ledger format:** flat `tasks/T-*.md` + derived index, or a single `tasks.json`?
   Leaning per-file markdown (human-diffable) + generated index.
3. **Where DoD lives:** embedded in each `tasks/T-*.md` (proposed) vs a separate registry.
4. **KB retrieval v2:** if deterministic glob/substring proves too coarse, add tag-scored
   ranking before considering embeddings.
```

