import { describe, expect, test } from "vitest";
import {
  buildEngContextTools,
  ENG_ACTION_TOOL_IDS,
  registerEngContextTools,
} from "../src/eng-context-tools.js";
import type {
  GoalEvaluate,
  PresentResult,
  SystemDiagram,
  SystemGoal,
  SystemGoalsList,
  SystemVcycle,
} from "../src/system-cli.js";

const CTX = { cwd: "/repo" };

// Minimal dependency stubs so the read-only tools can be unit-tested without a
// real Python side. Each returns a fake `ok` payload for one subcommand.
function deps(overrides: Record<string, unknown> = {}) {
  const vcycle: SystemVcycle = {
    scope: { kind: "feat" as const, ref: "feat:FEAT-NAV-017" },
    vcycle: {
      anchor: "feat:FEAT-NAV-017",
      definition: [{ label: "SYSTEM_REQUIREMENTS", nodes: [{ id: "SR-001", kind: "sr" }] }],
      verification: [{ label: "SIMULATION_VERIFICATION", nodes: [] }],
      goals: [{ id: "GOAL-NAV-003", kind: "goal" }],
      metrics: [{ id: "MET-RATE", kind: "metric" }],
    },
  };
  const diagram: SystemDiagram = {
    id: "DIAG-NAV-001",
    title: "Nav",
    diagram_path: "docs/diagrams/assets/nav.html",
    errors: [],
  };
  const simRun = {
    run: "RUN-003",
    experiment: "SIM-047",
    feature: "FEAT-NAV-017",
    requirements: [],
    goals: ["GOAL-NAV-003"],
    commit: "f92b004",
    result: "passed",
    scope_errors: [],
  };
  const simMetric = [
    { run: "RUN-001", commit: "a", value: 0.71, ts: null },
    { run: "RUN-002", commit: "b", value: 0.8, ts: null },
  ];
  const simGoalEvidence = { goal: "GOAL-NAV-003", runs: [simRun] };
  const goal: SystemGoal = {
    id: "GOAL-NAV-003",
    title: "Reacquire",
    state: "NOT_REACHED",
    version: 1,
    feature: ["FEAT-NAV-017"],
    requirements: ["SR-001"],
    metric: { name: "reacquisition_rate", source_experiment: "SIM-047" },
    target: ">=0.9",
    evidence: [],
    history: [],
    scope_errors: [],
  };
  const goalsList: SystemGoalsList = {
    scope: "feat:FEAT-NAV-017",
    goals: [goal],
  };
  const goalEvaluate: GoalEvaluate = {
    evaluated: true,
    goal_id: "GOAL-NAV-003",
    transition: { from: "EVALUATING", to: "REACHED", legal: true },
    derived: {
      state: "REACHED",
      passed: true,
      value: 0.93,
      target: 0.9,
      operator: ">=",
      run: "RUN-003",
      commit: "f92b004",
      blocked_reason: null,
    },
  };
  const present: PresentResult = {
    artifact: "feat:FEAT-NAV-017",
    focus: "overview",
    level: "INSPECT",
    intent: { artifact: "feat:FEAT-NAV-017", focus: "overview" },
    resolution: "deferred: presentation router lands in Inc 5; no adapter dispatched in Inc 4",
    adapter: null,
    target: null,
    note: "Inc 4 records the intent and declares the plan only; Inc 5 routes it.",
  };
  const traversal = {
    requirement: ["SR-001"],
    tasks: ["T-001"],
    design: [],
    files: ["src/a.py"],
  };
  return {
    vcycle: () => ({ ok: true as const, value: vcycle }),
    diagram: () => ({ ok: true as const, value: diagram }),
    simRun: () => ({ ok: true as const, value: simRun }),
    simLatest: () => ({ ok: true as const, value: simRun }),
    simFailure: () => ({ ok: true as const, value: simRun }),
    simMetric: () => ({ ok: true as const, value: simMetric }),
    simGoalEvidence: () => ({ ok: true as const, value: simGoalEvidence }),
    goal: () => ({ ok: true as const, value: goal }),
    goalsList: () => ({ ok: true as const, value: goalsList }),
    goalEvaluate: () => ({ ok: true as const, value: goalEvaluate }),
    present: () => ({ ok: true as const, value: present }),
    traversal: () => ({ ok: true as const, value: traversal }),
    ...overrides,
  };
}

async function run(tool: { execute: Function }, params: unknown) {
  const r = await tool.execute("call-1", params, undefined, undefined, CTX);
  return r.content.map((c: { text: string }) => c.text).join("\n");
}

function findTool(name: string) {
  const tool = buildEngContextTools(deps()).find((t) => t.name === name);
  if (!tool) throw new Error(`tool not found: ${name}`);
  return tool;
}

describe("eng-context tools (unit, mocked deps)", () => {
  test("each read-only tool is registered with a description and arg schema", () => {
    const tools = buildEngContextTools(deps());
    const ids = tools.map((t) => t.name);
    for (const id of [
      "eng_get_vcycle",
      "eng_get_diagram",
      "eng_trace_requirement",
      "eng_get_latest_simulation",
      "eng_get_latest_failure",
      "eng_get_goal",
      "eng_get_goals",
      "eng_get_goal_evidence",
      "eng_get_metric_history",
      "eng_get_simulation_run",
      "eng_evaluate_goal",
      "eng_present",
    ]) {
      expect(ids).toContain(id);
    }
    for (const tool of tools) {
      expect(tool.description.length).toBeGreaterThan(0);
      expect(tool.parameters).toBeTruthy();
    }
  });

  test("eng_get_vcycle renders definition, goals and metrics", async () => {
    const out = await run(findTool("eng_get_vcycle"), { ref: "feat:FEAT-NAV-017" });
    expect(out).toContain("vcycle: feat:FEAT-NAV-017");
    expect(out).toContain("SYSTEM_REQUIREMENTS: SR-001");
    expect(out).toContain("goals: GOAL-NAV-003");
  });

  test("eng_get_diagram renders the canonical path", async () => {
    const out = await run(findTool("eng_get_diagram"), { diagram_id: "DIAG-NAV-001" });
    expect(out).toContain("diagram: DIAG-NAV-001");
    expect(out).toContain("docs/diagrams/assets/nav.html");
  });

  test("eng_trace_requirement renders the full trace chain", async () => {
    const out = await run(findTool("eng_trace_requirement"), { requirement_id: "SR-001" });
    expect(out).toContain("trace for SR-001:");
    expect(out).toContain("tasks: T-001");
    expect(out).toContain("files: src/a.py");
  });

  test("eng_get_goal renders contract and state", async () => {
    const out = await run(findTool("eng_get_goal"), { goal_id: "GOAL-NAV-003" });
    expect(out).toContain("goal: GOAL-NAV-003");
    expect(out).toContain("state: NOT_REACHED");
  });

  test("eng_get_metric_history renders ascending entries", async () => {
    const out = await run(findTool("eng_get_metric_history"), { metric_id: "reacquisition_rate" });
    expect(out).toContain("metric history: 2 entry(ies)");
    expect(out).toContain("RUN-002: 0.8");
  });

  test("eng_get_goal_evidence renders runs for a goal", async () => {
    const out = await run(findTool("eng_get_goal_evidence"), { goal_id: "GOAL-NAV-003" });
    expect(out).toContain("goal evidence for GOAL-NAV-003:");
    expect(out).toContain("RUN-003");
  });

  test("a failing dep surfaces the CLI error instead of inventing data", async () => {
    const broken = buildEngContextTools(
      deps({ goal: () => ({ ok: false as const, error: "factory.goals exited 1: boom" }) }),
    ).find((t) => t.name === "eng_get_goal");
    if (!broken) throw new Error("eng_get_goal not found");
    const out = await run(broken, { goal_id: "GOAL-NAV-003" });
    expect(out).toContain("eng_get_goal failed");
    expect(out).toContain("boom");
  });

  test("eng_evaluate_goal renders the recorded transition", async () => {
    const out = await run(findTool("eng_evaluate_goal"), { goal_id: "GOAL-NAV-003" });
    expect(out).toContain("transition: EVALUATING -> REACHED (recorded)");
    expect(out).toContain("passed: true");
  });

  test("eng_present records the intent and declares the deferred plan", async () => {
    const out = await run(findTool("eng_present"), { artifact: "feat:FEAT-NAV-017", focus: "overview" });
    expect(out).toContain("intent: present(feat:FEAT-NAV-017, focus=overview)");
    expect(out).toContain("level: INSPECT");
    expect(out).toContain("deferred: presentation router lands in Inc 5");
  });

  test("action tools are distinct from read-only tools (Task 3 Step 3)", () => {
    const tools = buildEngContextTools(deps());
    const ids = new Set(tools.map((t) => t.name));
    const readIds = [...ids].filter((id) => !(ENG_ACTION_TOOL_IDS as readonly string[]).includes(id));
    // Every action tool id is registered and disjoint from the read-only set.
    for (const actionId of ENG_ACTION_TOOL_IDS) expect(ids).toContain(actionId);
    for (const readId of readIds) expect(ENG_ACTION_TOOL_IDS).not.toContain(readId);
    // An action tool advertises that it writes goal state, so a reviewer can
    // forbid these ids without touching the read-only registrations.
    const action = tools.find((t) => t.name === "eng_evaluate_goal");
    expect(action?.description).toMatch(/writes goal state/i);
    const readOnly = tools.filter((t) => !(ENG_ACTION_TOOL_IDS as readonly string[]).includes(t.name));
    for (const tool of readOnly) expect(tool.description).not.toMatch(/writes goal state/i);
  });

  test("registerEngContextTools calls registerTool for each tool", () => {
    const registered: string[] = [];
    registerEngContextTools({ registerTool: (t: { name: string }) => { registered.push(t.name); } });
    expect(registered.length).toBeGreaterThan(0);
  });
});
