import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import type { ExtCommandCtx } from "./pi-types.js";

export interface PlanLegalActionsResponse {
  schema: number;
  run_id: string;
  blocked: boolean;
  reason: string | null;
  legal_next_actions: string[];
  selected_downstream_workflow?: string | null;
  starts_automatically: false;
  state?: string;
  run_identity?: Record<string, unknown> | null;
  action_registry?: {
    schema: number;
    legal_ids: string[];
    registry_hash: string;
  };
}

export interface PlanCommand {
  bin: string;
  args: string[];
}

const SAFE_RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const AUTHORING_OR_REVIEW_ACTIONS = new Set([
  "author-spec",
  "author-plan",
  "review-spec",
  "review-plan",
]);

export function buildPlanLegalActionsCommand(root: string, runId: string): PlanCommand {
  if (!SAFE_RUN_ID.test(runId)) throw new Error("unsafe planning run id");
  return {
    bin: "uv",
    args: ["run", "coherence", "plan", "legal-actions", "--project-root", root, "--run-id", runId, "--json"],
  };
}

export function parsePlanLegalActionsResponse(raw: string):
  | { ok: true; value: PlanLegalActionsResponse }
  | { ok: false; error: string } {
  try {
    const value: unknown = JSON.parse(raw);
    if (
      !isRecord(value) ||
      (value.schema !== 1 && value.schema !== 2) || typeof value.run_id !== "string" ||
      typeof value.blocked !== "boolean" ||
      !(value.reason === null || typeof value.reason === "string") ||
      !Array.isArray(value.legal_next_actions) ||
      value.legal_next_actions.length > 1 ||
      !value.legal_next_actions.every((item) => typeof item === "string") ||
      value.starts_automatically !== false
    ) {
      return { ok: false, error: "invalid planning legal-actions response" };
    }
    if (value.schema === 2) {
      // Validate the Python adapter's wire contract without deriving a stage.
      const actions = value.legal_next_actions;
      const registry = value.action_registry;
      const identity = value.run_identity;
      if (
        typeof value.state !== "string" ||
        !isRecord(registry) || registry.schema !== 1 ||
        !Array.isArray(registry.legal_ids) ||
        !registry.legal_ids.every((action) => typeof action === "string") ||
        new Set(registry.legal_ids).size !== registry.legal_ids.length ||
        typeof registry.registry_hash !== "string" ||
        registry.registry_hash !== createHash("sha256")
          .update(registry.legal_ids.join("\n"), "utf8").digest("hex") ||
        !("run_identity" in value) ||
        (identity !== null && !isRecord(identity)) ||
        (!value.blocked && (!isRecord(identity) || value.reason !== null || actions.length !== 1)) ||
        (value.blocked && (typeof value.reason !== "string" || actions.length !== 0)) ||
        (actions[0] !== undefined && !registry.legal_ids.includes(actions[0]))
      ) {
        return { ok: false, error: "invalid planning legal-actions response" };
      }
      if (isRecord(identity) && (
        identity.run_id !== value.run_id ||
        typeof identity.next_sequence !== "number" ||
        !Number.isInteger(identity.next_sequence) || identity.next_sequence < 1 ||
        typeof identity.journal_sha256 !== "string" ||
        identity.journal_sha256.length !== 64 || !/^[0-9a-f]{64}$/.test(identity.journal_sha256)
      )) {
        return { ok: false, error: "invalid planning legal-actions response" };
      }
    }
    return { ok: true, value: value as unknown as PlanLegalActionsResponse };
  } catch {
    return { ok: false, error: "invalid planning legal-actions response" };
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function renderPlanLegalActions(value: PlanLegalActionsResponse): string {
  const status = value.blocked ? `Planning blocked: ${value.reason ?? "UNKNOWN"}` : "Planning ready";
  const actions = value.legal_next_actions.length > 0 ? value.legal_next_actions.join(", ") : "none";
  return [
    status,
    `Legal actions: ${actions}`,
    `Starts automatically: ${value.starts_automatically ? "yes" : "no"}`,
  ].join("\n");
}

function defaultBackend(ctx: ExtCommandCtx, runId: string):
  | { ok: true; value: PlanLegalActionsResponse }
  | { ok: false; error: string } {
  try {
    const command = buildPlanLegalActionsCommand(resolve(ctx.cwd), runId);
    const result = spawnSync(command.bin, command.args, {
      cwd: resolve(ctx.cwd), encoding: "utf-8", timeout: 120000,
    });
    const parsed = parsePlanLegalActionsResponse(String(result.stdout || ""));
    if (!parsed.ok) return { ok: false, error: String(result.stderr || parsed.error).trim() };
    if (parsed.value.run_id !== runId) return { ok: false, error: "planning backend returned a mismatched run id" };
    return parsed;
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

export async function runPlan(ctx: ExtCommandCtx, rawArgs: string): Promise<void> {
  const runId = rawArgs.trim();
  if (!SAFE_RUN_ID.test(runId)) {
    ctx.ui.notify("usage: /plan <run-id>", "error");
    return;
  }

  const response = defaultBackend(ctx, runId);
  if (!response.ok) {
    ctx.ui.notify(`planning blocked: ${response.error}`, "error");
    return;
  }
  const projection = response.value;
  ctx.ui.notify(renderPlanLegalActions(projection), projection.blocked ? "warning" : "info");
  if (projection.blocked || projection.starts_automatically) return;

  const actions = projection.legal_next_actions.filter((action) => AUTHORING_OR_REVIEW_ACTIONS.has(action));
  if (actions.length === 0 || !ctx.hasUI) return;
  const selected = await ctx.ui.select("Planning action", actions);
  if (selected === undefined || !actions.includes(selected)) return;
  await ctx.newSession({
    withSession: async (session) => {
      await session.sendUserMessage(
        `Continue only the backend-authorized planning action: ${selected}. Do not request or record consent, adoption, downstream execution, or configuration changes.`,
        { deliverAs: "followUp" },
      );
    },
  });
}

