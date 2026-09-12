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

const ACTION_REGISTRY = {
  schema: 1,
  legal_ids: [
    "author-requirements", "record-sr-consent", "author-spec", "author-plan",
    "review-spec", "review-plan", "run-planning-gates", "create-handoff", "inspect-handoff",
  ],
  registry_hash: "26c27865bc893be61f58fd985aa1663e8bce964047f90fa3f0a2226c368dd135",
};

function schemaTwoProjection(overrides: Record<string, unknown> = {}) {
  return {
    schema: 2,
    run_id: "run-1",
    blocked: false,
    reason: null,
    state: "capture",
    legal_next_actions: ["author-requirements"],
    starts_automatically: false,
    run_identity: { run_id: "run-1", next_sequence: 2, journal_sha256: "a".repeat(64) },
    action_registry: ACTION_REGISTRY,
    ...overrides,
  };
}

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

  test("accepts a backend-shaped schema-2 ready projection", () => {
    const payload = schemaTwoProjection();
    expect(parsePlanLegalActionsResponse(JSON.stringify(payload))).toEqual({
      ok: true, value: payload,
    });
  });

  test.each([
    { reason: "STALE_SESSION_STATE", state: "unknown", run_identity: null },
    { reason: "UNRESOLVED_CHALLENGE" },
  ])("accepts a backend-shaped schema-2 blocked projection: $reason", (overrides) => {
    const payload = schemaTwoProjection({
      ...overrides, blocked: true, legal_next_actions: [],
    });
    expect(parsePlanLegalActionsResponse(JSON.stringify(payload))).toEqual({
      ok: true, value: payload,
    });
  });

  test.each([1, 2])("rejects multiple legal actions in schema %s", (schema) => {
    expect(parsePlanLegalActionsResponse(JSON.stringify(schemaTwoProjection({
      schema, legal_next_actions: ["author-spec", "author-plan"],
    })))).toEqual({ ok: false, error: "invalid planning legal-actions response" });
  });

  test.each([
    ["missing identity", { run_identity: undefined }],
    ["null ready identity", { run_identity: null }],
    ["array identity", { run_identity: [] }],
    ["mismatched identity", { run_identity: { ...schemaTwoProjection().run_identity, run_id: "other" } }],
    ["invalid sequence", { run_identity: { ...schemaTwoProjection().run_identity, next_sequence: true } }],
    ["zero sequence", { run_identity: { ...schemaTwoProjection().run_identity, next_sequence: 0 } }],
    ["fractional sequence", { run_identity: { ...schemaTwoProjection().run_identity, next_sequence: 1.5 } }],
    ["invalid journal hash", { run_identity: { ...schemaTwoProjection().run_identity, journal_sha256: "bad" } }],
    ["missing state", { state: undefined }],
    ["missing registry", { action_registry: undefined }],
    ["invalid registry schema", { action_registry: { ...ACTION_REGISTRY, schema: 2 } }],
    ["invalid registry hash", { action_registry: { ...ACTION_REGISTRY, registry_hash: "0".repeat(64) } }],
    ["duplicate registry IDs", { action_registry: { ...ACTION_REGISTRY, legal_ids: ["author-spec", "author-spec"] } }],
    ["unregistered action", { legal_next_actions: ["execute"] }],
    ["ready with no action", { legal_next_actions: [] }],
    ["ready with reason", { reason: "BLOCKED" }],
    ["blocked with action", { blocked: true, reason: "BLOCKED" }],
    ["blocked with no reason", { blocked: true, legal_next_actions: [] }],
    ["automatic start", { starts_automatically: true }],
  ])("rejects invalid schema-2 contract: %s", (_label, overrides) => {
    expect(parsePlanLegalActionsResponse(JSON.stringify(schemaTwoProjection(
      overrides as Record<string, unknown>,
    )))).toEqual({ ok: false, error: "invalid planning legal-actions response" });
  });

  test("reports a schema-2 ready projection without starting work", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify(schemaTwoProjection()), stderr: "",
    } as never);
    const ctx = makeContext(makeUi());
    await runPlan(ctx, "run-1");
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      "Planning ready\nLegal actions: author-requirements\nStarts automatically: no", "info",
    );
    expect(ctx.newSession).not.toHaveBeenCalled();
    expect(ctx.ui.select).not.toHaveBeenCalled();
  });

  test("rejects a schema-2 backend response for another requested run", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify(schemaTwoProjection()), stderr: "",
    } as never);
    const ctx = makeContext(makeUi());
    await runPlan(ctx, "run-2");
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      "planning blocked: planning backend returned a mismatched run id", "error",
    );
    expect(ctx.newSession).not.toHaveBeenCalled();
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

  test.each(["inspect-handoff", "create-downstream-session"])(
    "does not launch a session for %s", async (action) => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({
        schema: 1, run_id: "run-1", blocked: false, reason: null,
        legal_next_actions: [action],
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
