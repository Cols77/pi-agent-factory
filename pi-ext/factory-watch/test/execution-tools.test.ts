import { describe, expect, it } from "vitest";
import {
  EXECUTION_TOOL_NAMES,
  buildExecutionTools,
  registerExecutionTools,
} from "../src/execution-tools.js";
import { factoryToolsCatalog } from "../src/tool-catalog.js";

const CTX = { cwd: "." };

// The builder returns four differently-parameterised tools, so the array's
// element type is a union; tests address one by name and call it through this
// structural shape (the same `{ execute: Function }` convention the
// eng-context tool tests use).
interface CallableTool {
  name: string;
  execute: Function;
}

function toolNamed(
  run: (argv: string[], cwd: string) => string,
  name: string,
): CallableTool {
  const tool = (buildExecutionTools({ run }) as CallableTool[]).find(
    (entry) => entry.name === name,
  );
  if (!tool) throw new Error(`no execution tool named ${name}`);
  return tool;
}

interface ToolResult {
  content: { type: "text"; text: string }[];
  details: null;
}

function call(tool: CallableTool, id: string, params: unknown, ctx = CTX): Promise<ToolResult> {
  return tool.execute(id, params, undefined, undefined, ctx) as Promise<ToolResult>;
}

describe("execution tools forward the Python-owned command surface", () => {
  it("dispatches governed execution through the Python CLI", async () => {
    const calls: string[][] = [];
    const tool = toolNamed((argv) => {
      calls.push(argv);
      return '{"outcome":"escalated"}';
    }, "execution_dispatch_task");

    const result = await call(tool, "call-1", { task_id: "T-013", run_id: "run-013" });

    expect(calls[0]).toEqual(
      expect.arrayContaining(["execution", "dispatch-task", "T-013", "--run-id", "run-013"]),
    );
    expect(result.content[0]).toEqual({ type: "text", text: '{"outcome":"escalated"}' });
  });

  it("forwards the read-only legal-action projection through the Python CLI", async () => {
    const calls: string[][] = [];
    const tool = toolNamed((argv) => {
      calls.push(argv);
      return '{"state":"needs_input","starts_automatically":false}';
    }, "execution_legal_actions");

    const result = await call(tool, "call-2", { task_id: "T-013", run_id: "run-013" });

    expect(calls[0]).toEqual(
      expect.arrayContaining([
        "execution",
        "legal-actions",
        "--run-id",
        "run-013",
        "--task-id",
        "T-013",
      ]),
    );
    expect(result.content[0]).toEqual({
      type: "text",
      text: '{"state":"needs_input","starts_automatically":false}',
    });
  });

  it("streams progress by run id alone", async () => {
    const calls: string[][] = [];
    const tool = toolNamed((argv) => {
      calls.push(argv);
      return '{"events":[]}';
    }, "execution_stream_progress");

    await call(tool, "call-3", { run_id: "run-013" });

    expect(calls[0]).toEqual(["execution", "stream-progress", "run-013", "--json"]);
  });

  it("reports one worker observation without deciding anything", async () => {
    const calls: string[][] = [];
    const tool = toolNamed((argv) => {
      calls.push(argv);
      return '{"action":"report-worker-result"}';
    }, "execution_report_worker_result");

    await call(tool, "call-4", {
      run_id: "run-013",
      task_id: "T-013",
      lane: "review-spec",
      result: "fail",
      detail: "two findings",
      denied_writes: 2,
    });

    expect(calls[0]).toEqual([
      "execution",
      "report-worker-result",
      "--run-id",
      "run-013",
      "--task-id",
      "T-013",
      "--lane",
      "review-spec",
      "--result",
      "fail",
      "--detail",
      "two findings",
      "--denied-writes",
      "2",
      "--json",
    ]);
  });

  it("passes the caller's cwd to the Python command unchanged", async () => {
    const seen: string[] = [];
    const tool = toolNamed((_argv, cwd) => {
      seen.push(cwd);
      return "{}";
    }, "execution_legal_actions");

    await call(tool, "call-5", { run_id: "run-013", task_id: "T-013" }, { cwd: "/repo" });

    expect(seen).toEqual(["/repo"]);
  });
});

describe("execution tools refuse unsafe input before reaching Python", () => {
  it("refuses an unsafe run id without running anything", async () => {
    const calls: string[][] = [];
    const tool = toolNamed((argv) => {
      calls.push(argv);
      return "{}";
    }, "execution_legal_actions");

    const result = await call(tool, "call-6", { run_id: "../escape", task_id: "T-013" });

    expect(calls).toEqual([]);
    expect(result.content[0]?.text).toContain("not a safe identifier");
  });

  it("refuses an unknown worker result vocabulary without running anything", async () => {
    const calls: string[][] = [];
    const tool = toolNamed((argv) => {
      calls.push(argv);
      return "{}";
    }, "execution_report_worker_result");

    const result = await call(tool, "call-7", {
      run_id: "run-013",
      task_id: "T-013",
      lane: "dev",
      result: "completed",
      detail: "nice try",
    });

    expect(calls).toEqual([]);
    expect(result.content[0]?.text).toContain("pass, fail, error");
  });
});

describe("the execution tool family is exactly four registered tools", () => {
  it("registers only the four Python-backed verbs", () => {
    const registered: string[] = [];
    registerExecutionTools({ registerTool: (tool: { name: string }) => registered.push(tool.name) });

    expect(registered).toEqual([
      "execution_legal_actions",
      "execution_dispatch_task",
      "execution_report_worker_result",
      "execution_stream_progress",
    ]);
    expect(EXECUTION_TOOL_NAMES).toEqual(registered);
    // resolve-human is deliberately NOT a tool: a human decision is never an
    // automatic tool transition.
    expect(registered.some((name) => name.includes("resolve"))).toBe(false);
  });

  it("derives the execution family into the factory tool catalog", () => {
    const entries = factoryToolsCatalog().filter(
      (entry) => entry.family === "governed-execution",
    );

    expect(entries.map((entry) => entry.name)).toEqual(EXECUTION_TOOL_NAMES);
  });
});
