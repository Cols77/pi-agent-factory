# Increment 4 — Engineering Context Agent Surface (pi-ext) (Implementation Plan)

**Status:** Draft for written review. Assumes locked **D1 = pi-ext** (agent tools, not a
standalone MCP server).
**Source phase:** Engineering Context spec §37 **Phase 4 — Engineering Context MCP**,
mapped to the v1 integration route.
**Landing repo:** pi-agent-factory (pi-ext/factory-watch + Python query backends).
**Sub-agents:** dev=`pi -p prompts/increment-04-dev.md`, review=`pi -p prompts/increment-04-review.md`.

## Goal

Expose the engineering-context operations from spec §25 as deterministic Pi-extension
custom tools (D1), backed by the Python query surface built in Inc 1–3. These are the
tools a coding agent uses to reconstruct feature context, trace requirements, read goals
and evidence, and present artifacts — without a separate MCP server.

## Reuse (do not rebuild)

- **Tool plumbing:** `pi-ext/factory-watch` custom tools (`trace_tools`, `system_context_tools`,
  `evidence_client.ts`, `system-cli.ts`) — the exact pattern to copy; no new server process.
- **Query backends:** `factory.system` `query_feature_context`/`query_vcycle` (Inc 1),
  `query_goal`/`query_goals` (Inc 2), `query_simulation_run`/`query_latest_failure`/
  `query_metric_history` (Inc 3), `factory.trace` `trace_requirement`.
- **Presentation:** `present()` is delegated to Inc 5's router; Inc 4 only declares the tool.

## Global constraints (Program §6 + D3)

- Tools are thin adapters; all derivation stays in Python (never re-derive in TS). Confirm with
  the existing v1 pattern `system-context-tools.ts` → python `factory.system ... --json`.
- Additive: new tool ids registered alongside existing ones; existing tools untouched.
- Deterministic, read-only-by-default; `evaluate_goal`/`present` are explicit actions surfaced
  separately (and honor PRESS policy §23 in Inc 5).

## Tool surface (spec §25)

| Tool | Backend query | Read/write |
|---|---|---|
| `eng_get_artifact(id)` | `system brief --scope <kind>:<id>` | read |
| `eng_get_feature_context(feature_id)` | `query_feature_context` | read |
| `eng_get_vcycle(ref)` | `query_vcycle` | read |
| `eng_trace_requirement(requirement_id)` | `factory.trace` trace | read |
| `eng_get_requirement_implementation(requirement_id)` | trace graph | read |
| `eng_get_verification_status(requirement_id)` | `validation_status` (goal-aware) | read |
| `eng_get_diagram(diagram_id)` | `query_diagram` (Inc 1 `diag:` kind) | read |
| `eng_get_recent_feature_changes(feature_id)` | `feature.recent_changes` | read |
| `eng_get_latest_simulation(feature_id)` | `query_latest_simulation` | read |
| `eng_get_latest_failure(feature_id)` | `query_latest_failure` | read |
| `eng_get_goal(goal_id)` | `query_goal` | read |
| `eng_get_goals(scope)` | `query_goals` | read |
| `eng_get_goal_history(goal_id)` | goals history | read |
| `eng_get_goal_evidence(goal_id)` | `evidence_for_goal` | read |
| `eng_evaluate_goal(goal_id)` | Inc 3 auto-eval | action |
| `eng_present(artifact, focus?)` | Inc 5 router | action |

## File structure (additive)

| File | Responsibility |
|---|---|
| `pi-ext/factory-watch/src/eng-context-tools.ts` | Tool definitions (name/description/args/schema) → call `system-cli`. |
| `pi-ext/factory-watch/src/eng-context-tool-format.ts` | Format JSON into compact cockpit text. |
| `pi-ext/factory-watch/test/eng-context-tools.test.ts` | Tool schema + dispatch tests. |
| `src/factory/system/cli.py` (extend, additive) | any missing subcommand flags the tools need (e.g. `--scope` forms already exist). |

## Task 1: Register the read-only tool set

- [x] **Step 1: Failing tests** — copy the v1 tool-registration pattern; assert each tool id is
  registered with a non-empty description and a JSON-schema args block; read-only tools declare
  no side-effect.
- [x] **Step 2: Implement** `eng-context-tools.ts`: map each tool to a `system-cli` invocation,
  e.g.:
```ts
const TOOLS = {
  eng_get_feature_context: { args: { feature_id: "string" },
    run: (a) => buildSystemCli(["brief", "--scope", `feat:${a.feature_id}`, "--json"]) },
  eng_get_goal: { args: { goal_id: "string" },
    run: (a) => buildSystemCli(["goal", "show", "--id", a.goal_id, "--json"]) },
  // ... each maps to a python subcommand (extend cli.py where a subcommand is missing)
};
```
- [x] **Step 3:** TS unit + `uv run python -m pytest -q` green + lint + commit.

## Task 2: Python subcommand backstop

- [x] **Step 1:** add any missing `factory.goals show`/`factory.simulation` CLI subcommands the
  tools reference (additive only; `--json` output shape stable and documented).
  Added `factory.system` subcommands `diagram`, `sim run/latest/failure/metric/goal-evidence`,
  `goal show/list` (+ `query_goal_evidence`) — additive, existing verbs untouched.
- [x] **Step 2:** integration tests drive a tool end-to-end against a seeded repo (a
  `feat:`/`sr:`/`goal:`/run fixture) and assert the returned JSON is well-formed and cites sources.
- [x] **Step 3:** full suite + lint + commit.

## Task 3: Action tools (`eng_evaluate_goal`, `eng_present`) behind policy

- [x] **Step 0 (read): `eng_get_diagram(diagram_id)`** — resolve a `diag:` stub → return the
  canonical HTML path + `focus` + `illustrates` refs (D7). Read-only; `present(diag:..)` routes the
  artifact to the browser via Inc 5. Add the row above to `eng-context-tools.ts` and a `diag:`
  subcommand backstop in Task 2 if missing. Comprehension verification (D8) is **not** an `eng_*`
  tool — it is the installed `grill-understanding`/`visual-explainer` skills invoked from the
  cockpit surfaces (Inc 6/7), keeping the engineering-context surface deterministic and read-only.

- [ ] **Step 1:** `eng_evaluate_goal` calls the Inc 3 auto-eval and returns the resulting
  transition; it is the ONLY tool that writes goal state.
- [ ] **Step 2:** `eng_present` validates args (artifact, optional focus) and forwards to the
  Inc 5 router; in Inc 4 it records the intent and returns the resolution plan (router lands Inc 5).
- [ ] **Step 3:** tests assert action tools are distinct from read tools (a reviewer can forbid
  the former without touching the latter). Full suite + lint + commit.

## Task 4: `/task FEAT-...` workflow start (thin)

- [ ] **Step 1:** implement a minimal `/task <feat:...>` preamble that replays spec §26 steps 1–4
  (reconstruct context → inspect requirements → inspect active goals → determine affected
  design/code) by calling the read tools in order, printing a compact context block.
- [ ] **Step 2:** unit test the ordering; full suite + lint + commit.

## Task 5: Review handoff

- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §25 tool list + D1 (no MCP server, no
  TS re-derivation) + D3 (additive registration). Fix findings as fixes; update checkboxes.

## Acceptance for Increment 4

- All spec §25 read operations callable from the cockpit as tools, returning Python-derived,
  citation-carrying JSON; exact id refs, no fuzzy fallback.
- `eng_get_feature_context` returns the AC-01 bundle in one call.
- Existing v1 tools untouched and green; no standalone MCP process added (D1).
