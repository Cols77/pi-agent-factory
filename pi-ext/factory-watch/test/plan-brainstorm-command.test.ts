import { describe, expect, test, vi } from "vitest";
import {
  buildPlanningSessionCommand,
  buildProvisionalSpecPrompt,
  parsePlanningSessionResponse,
  runPlanBrainstorm,
} from "../src/plan-brainstorm-command.js";
import type { ExtCommandCtx, UiApi } from "../src/pi-types.js";

describe("planning brainstorm command", () => {
  test("builds an argv-only backend session command", () => {
    expect(buildPlanningSessionCommand("C:/repo", "append", [
      "--run-id", "run-1", "--answer-id", "q-1", "--question", "What?", "--text", "exact answer",
    ])).toEqual({
      bin: "uv",
      args: ["run", "coherence", "plan", "append", "--project-root", "C:/repo", "--run-id", "run-1", "--answer-id", "q-1", "--question", "What?", "--text", "exact answer", "--json"],
    });
  });

  test("parses backend responses without losing exact answers", () => {
    const response = parsePlanningSessionResponse(JSON.stringify({
      schema: 1, ok: true, run_id: "run-1", state: "capture", next_sequence: 3,
      events: [{ id: "q-1", question: "What?", text: "  exact answer  ", source: "user" }],
    }));
    expect(response.ok).toBe(true);
    if (response.ok) expect(response.value.events[0]?.text).toBe("  exact answer  ");
  });

  test("captures one answer at a time, then resumes with an honest provisional state", async () => {
    const notify = vi.fn();
    const select = vi.fn(async () => "Finish with provisional spec");
    const editor = vi.fn()
      .mockResolvedValueOnce("answer one")
      .mockResolvedValueOnce(undefined);
    const ui = { notify, select, editor } as unknown as UiApi;
    const ctx = { cwd: "C:/repo", ui, hasUI: true, model: undefined, reload: vi.fn(), newSession: vi.fn() } as unknown as ExtCommandCtx;
    const backend = vi.fn()
      .mockReturnValueOnce({ ok: true, value: { run_id: "run-1", state: "capture", next_sequence: 2, events: [] } })
      .mockReturnValue({ ok: true, value: { run_id: "run-1", state: "intent_provisional", next_sequence: 3, events: [] } });
    const result = await runPlanBrainstorm(ctx, "initial request", { runId: "run-1", runBackend: backend });
    expect(backend).toHaveBeenCalledTimes(3);
    expect(backend.mock.calls[1]?.[0].args).toContain("answer one");
    expect(result.status).toBe("provisional");
    expect(ctx.newSession).toHaveBeenCalled();
  });

  test("blocks when a challenge has no explicit human resolution response", async () => {
    const notify = vi.fn();
    const select = vi.fn(async () => "Resolve");
    const editor = vi.fn()
      .mockResolvedValueOnce("always safe")
      .mockResolvedValueOnce(undefined);
    const ui = { notify, select, editor } as unknown as UiApi;
    const ctx = { cwd: "C:/repo", ui, hasUI: true, model: undefined, reload: vi.fn(), newSession: vi.fn() } as unknown as ExtCommandCtx;
    const backend = vi.fn()
      .mockReturnValueOnce({ ok: true, value: { run_id: "run-1", state: "capture", next_sequence: 2, events: [] } })
      .mockReturnValueOnce({ ok: true, value: { run_id: "run-1", state: "capture", next_sequence: 3, events: [], challenges: [{ id: "c-1", kind: "unsupported_claim", claim: "always safe", rationale: "needs evidence", evidence_needed: "repository inspection", status: "unresolved" }] } });

    const result = await runPlanBrainstorm(ctx, "initial request", { runId: "run-1", runBackend: backend });

    expect(result.status).toBe("blocked");
    expect(backend).toHaveBeenCalledTimes(2);
    expect(notify).toHaveBeenCalledWith(expect.stringContaining("blocked"), "error");
  });
});
