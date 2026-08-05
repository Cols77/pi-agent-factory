import { Type } from "typebox";
import { loadNextGap, runTrace, runTraceCheck } from "./trace-cli.js";
import {
  formatCheck,
  formatNoGaps,
  formatProposal,
  formatWriteResult,
} from "./trace-tool-format.js";

// Structural subset of the ExtensionContext fields these tools read, kept local
// so the tools stay unit-testable without constructing a real context.
interface ToolCtx {
  cwd: string;
}

function result(content: string): { content: string } {
  return { content };
}

export const traceNextTool = {
  name: "trace_next",
  label: "Trace: next gap",
  description:
    "Return the next pending traceability gap, with the node's excerpt and EVERY candidate " +
    "target including its full requirement statement. Candidates are ordered by shared-term " +
    "overlap, which is a lexical hint only — judge matches by meaning, not by position.",
  parameters: Type.Object({}),
  async execute(
    _id: string,
    _params: Record<string, never>,
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    const next = loadNextGap(ctx.cwd);
    if (!next.ok) return result(`trace_next failed: ${next.error}`);
    if (next.proposal === null) return result(formatNoGaps());
    return result(formatProposal(next.proposal));
  },
};

export const traceLinkTool = {
  name: "trace_link",
  label: "Trace: link",
  description:
    "Declare a traceability link. Use `satisfies` to record that a task satisfies a requirement " +
    "(node_id must be the TASK id, even when the gap was reported against the requirement), " +
    "`spec` to record that a plan implements a spec file, or `source_plan` to record which plan " +
    "a task came from. The target is validated: a non-existent one is refused, never written.",
  parameters: Type.Object({
    node_id: Type.String({ description: "Task id (satisfies/source_plan) or plan id (spec)" }),
    satisfies: Type.Optional(Type.String({ description: "Requirement id, e.g. SR-001" })),
    spec: Type.Optional(Type.String({ description: "Spec filename, e.g. 2026-07-30-design.md" })),
    source_plan: Type.Optional(Type.String({ description: "Plan filename, e.g. 2026-07-30-sim.md" })),
  }),
  async execute(
    _id: string,
    params: { node_id: string; satisfies?: string; spec?: string; source_plan?: string },
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    const given = (["satisfies", "spec", "source_plan"] as const).filter(
      (k) => typeof params[k] === "string" && params[k]!.trim() !== "",
    );
    if (given.length !== 1) {
      return result(
        "trace_link needs exactly one of `satisfies`, `spec` or `source_plan`; nothing was written.",
      );
    }
    const key = given[0]!;
    const flag = key === "source_plan" ? "--source-plan" : `--${key}`;
    return result(
      formatWriteResult("link", runTrace(ctx.cwd, ["link", params.node_id, flag, params[key]!])),
    );
  },
};

function dispositionTool(name: "exempt" | "defer", label: string, description: string) {
  return {
    name: `trace_${name}`,
    label,
    description,
    parameters: Type.Object({
      node_id: Type.String({ description: "Node id, e.g. T-047 or plan:2026-07-30-sim.md" }),
      reason: Type.String({ description: "Why — recorded on disk and read by humans later" }),
    }),
    async execute(
      _id: string,
      params: { node_id: string; reason: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      // A blank reason would record that we looked without recording what we saw.
      if (params.reason.trim() === "") {
        return result(`trace_${name} needs a non-empty reason; nothing was written.`);
      }
      return result(
        formatWriteResult(
          name,
          runTrace(ctx.cwd, [name, params.node_id, "--reason", params.reason]),
        ),
      );
    },
  };
}

export const traceExemptTool = dispositionTool(
  "exempt",
  "Trace: exempt",
  "Record that no requirement applies to this task or plan. Requirements themselves cannot be " +
    "exempted — defer them instead.",
);

export const traceDeferTool = dispositionTool(
  "defer",
  "Trace: defer",
  "Record that this gap was discussed but needs more time, with what must happen before it can " +
    "be resolved. Deferring passes the gate but does not improve the health score.",
);

export const traceCheckTool = {
  name: "trace_check",
  label: "Trace: check",
  description:
    "Run the completion gate. It re-derives every gap and disposition from disk, so it reflects " +
    "what is actually written, not what was claimed. Fails while any gap is still undiscussed.",
  parameters: Type.Object({}),
  async execute(
    _id: string,
    _params: Record<string, never>,
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    return result(formatCheck(runTraceCheck(ctx.cwd)));
  },
};

export function registerTraceTools(pi: { registerTool(tool: unknown): void }): void {
  for (const tool of [
    traceNextTool,
    traceLinkTool,
    traceExemptTool,
    traceDeferTool,
    traceCheckTool,
  ]) {
    pi.registerTool(tool);
  }
}
