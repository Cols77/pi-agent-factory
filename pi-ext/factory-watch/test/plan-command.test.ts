import { beforeEach, describe, expect, test, vi } from "vitest";
import { spawnSync } from "node:child_process";
import {
  buildPlanLegalActionsCommand,
  parsePlanLegalActionsResponse,
  renderPlanLegalActions,
  runPlan,
} from "../src/plan-command.js";
import type { ExtCommandCtx } from "../src/pi-types.js";

vi.mock("node:child_process", async () => {
  const actual = await vi.importActual<typeof import("node:child_process")>("node:child_process");
  return { ...actual, spawnSync: vi.fn() };
});

describe("guided /plan adapter", () => {
  beforeEach(() => vi.mocked(spawnSync).mockReset());

  test("builds an argv-safe legal-actions command", () => {
    expect(buildPlanLegalActionsCommand("C:/repo", "run-001")).toEqual({
      bin: "uv",
      args: ["run", "coherence", "plan", "legal-actions", "--project-root", "C:/repo", "--run-id", "run-001", "--json"],
    });
  });

  test("rejects malformed or automatically starting projections", () => {
    expect(parsePlanLegalActionsResponse("{}" )).toEqual({ ok: false, error: "invalid planning legal-actions response" });
    expect(parsePlanLegalActionsResponse(JSON.stringify({
      schema: 1, run_id: "run-1", blocked: false, reason: null,
      legal_next_actions: [], starts_automatically: true,
    }))).toEqual({ ok: false, error: "invalid planning legal-actions response" });
  });

  test("renders a backend block reason and never invents actions", () => {
    expect(renderPlanLegalActions({
      schema: 1, run_id: "run-1", blocked: true, reason: "SESSION_NOT_READY",
      legal_next_actions: [], selected_downstream_workflow: null, starts_automatically: false,
    })).toBe("Planning blocked: SESSION_NOT_READY\nLegal actions: none\nStarts automatically: no");
  });

  test("dispatches legal-actions and reports the backend projection", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 1,
      stdout: JSON.stringify({ schema: 1, run_id: "run-1", blocked: true, reason: "SESSION_NOT_READY", legal_next_actions: [], starts_automatically: false }),
      stderr: "",
    } as never);
    const notify = vi.fn();
    await runPlan({ cwd: "C:/repo", ui: { notify } } as never, "run-1");
    expect(spawnSync).toHaveBeenCalledWith("uv", expect.arrayContaining(["plan", "legal-actions", "--run-id", "run-1"]), expect.objectContaining({ cwd: expect.any(String) }));
    expect(notify).toHaveBeenCalledWith(expect.stringContaining("SESSION_NOT_READY"), "warning");
  });

  test("fails closed for an unsafe run id without spawning", async () => {
    const notify = vi.fn();
    await runPlan({ cwd: "C:/repo", ui: { notify } } as never, "../escape");
    expect(spawnSync).not.toHaveBeenCalled();
    expect(notify).toHaveBeenCalledWith("usage: /plan <run-id>", "error");
  });

  test("does not launch a session for inspection or downstream actions", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({
        schema: 1, run_id: "run-1", blocked: false, reason: null,
        legal_next_actions: ["inspect-handoff", "create-downstream-session"],
        starts_automatically: false,
      }),
      stderr: "",
    } as never);
    const ctx = {
      cwd: "C:/repo", ui: { notify: vi.fn(), select: vi.fn() },
      hasUI: true, newSession: vi.fn(),
    } as unknown as ExtCommandCtx;
    await runPlan(ctx, "run-1");
    expect(ctx.newSession).not.toHaveBeenCalled();
    expect(ctx.ui.select).not.toHaveBeenCalled();
  });
});
