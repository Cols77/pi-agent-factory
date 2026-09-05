import { beforeEach, describe, expect, test, vi } from "vitest";
import { spawnSync } from "node:child_process";
import {
  buildPlanLegalActionsCommand,
  parsePlanLegalActionsResponse,
  renderPlanLegalActions,
  runPlan,
} from "../src/plan-command.js";
import type { ExtCommandCtx, UiApi } from "../src/pi-types.js";

vi.mock("node:child_process", async () => {
  const actual = await vi.importActual<typeof import("node:child_process")>("node:child_process");
  return { ...actual, spawnSync: vi.fn() };
});

describe("guided /plan adapter", () => {
  beforeEach(() => vi.mocked(spawnSync).mockReset());

  function makeUi(select: UiApi["select"] = vi.fn()): UiApi {
    return {
      notify: vi.fn(),
      setStatus: vi.fn(),
      setWidget: vi.fn(),
      select,
      confirm: vi.fn(),
      editor: vi.fn(),
      custom: vi.fn(),
    };
  }

  function makeContext(ui: UiApi): ExtCommandCtx {
    return {
      cwd: "C:/repo",
      ui,
      hasUI: true,
      model: undefined,
      reload: vi.fn(async () => undefined),
      newSession: vi.fn(async () => ({ cancelled: false })),
    };
  }

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
    const ctx = makeContext(makeUi());
    await runPlan(ctx, "run-1");
    expect(ctx.newSession).not.toHaveBeenCalled();
    expect(ctx.ui.select).not.toHaveBeenCalled();
  });

  test("does not launch a session for a UI selection outside backend actions", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({
        schema: 1, run_id: "run-1", blocked: false, reason: null,
        legal_next_actions: ["author-spec"], starts_automatically: false,
      }),
      stderr: "",
    } as never);
    const select = vi.fn<UiApi["select"]>(async () => "create-downstream-session");
    const ctx = makeContext(makeUi(select));
    await runPlan(ctx, "run-1");
    expect(select).toHaveBeenCalledWith("Planning action", ["author-spec"]);
    expect(ctx.newSession).not.toHaveBeenCalled();
  });

});
