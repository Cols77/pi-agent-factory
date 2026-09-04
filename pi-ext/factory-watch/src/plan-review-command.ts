import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import type { ExtCommandCtx } from "./pi-types.js";

export interface PlanReviewCommand { bin: string; args: string[] }
export interface PlanReviewResponse {
  ok: boolean;
  blocked: boolean;
  stage: string;
  iteration: number;
  finding_ids: string[];
  prompts: string[];
  next_loop_input: unknown;
  legal_actions: string[];
  hashes: Record<string, string>;
}

const SAFE_RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

export function buildPlanReviewCommand(root: string, runId: string): PlanReviewCommand {
  if (!SAFE_RUN_ID.test(runId)) throw new Error("unsafe planning run id");
  return { bin: "uv", args: ["run", "coherence", "plan", "review", "--project-root", root, "--run-id", runId, "--json"] };
}

export function parsePlanReviewResponse(raw: string): { ok: true; value: PlanReviewResponse } | { ok: false; error: string } {
  try {
    const value = JSON.parse(raw) as Partial<PlanReviewResponse>;
    if (typeof value.ok !== "boolean" || typeof value.blocked !== "boolean" ||
        typeof value.stage !== "string" || typeof value.iteration !== "number" ||
        !Array.isArray(value.finding_ids) || !Array.isArray(value.prompts) ||
        !Array.isArray(value.legal_actions) || typeof value.hashes !== "object" || value.hashes === null) {
      return { ok: false, error: "invalid planning review response" };
    }
    return { ok: true, value: value as PlanReviewResponse };
  } catch {
    return { ok: false, error: "invalid planning review response" };
  }
}

export function renderPlanReview(value: PlanReviewResponse): string {
  const lines = [
    `Planning review: ${value.stage}, iteration ${value.iteration}`,
    `Status: ${value.blocked ? "BLOCKED" : "ready"}`,
    `Finding IDs: ${value.finding_ids.join(", ") || "none"}`,
    `Prompts: ${value.prompts.join(" | ") || "none"}`,
    `Next-loop input: ${typeof value.next_loop_input === "string" ? value.next_loop_input : JSON.stringify(value.next_loop_input)}`,
    `Hashes: ${JSON.stringify(value.hashes)}`,
    `Legal actions: ${value.legal_actions.join(", ")}`,
  ];
  return lines.join("\n");
}

export function runPlanReview(ctx: ExtCommandCtx, rawArgs: string): void {
  const runId = rawArgs.trim();
  if (!SAFE_RUN_ID.test(runId)) {
    ctx.ui.notify("usage: /plan-review <run-id>", "error");
    return;
  }
  try {
    const command = buildPlanReviewCommand(resolve(ctx.cwd), runId);
    const result = spawnSync(command.bin, command.args, { cwd: resolve(ctx.cwd), encoding: "utf-8", timeout: 120000 });
    const parsed = parsePlanReviewResponse(String(result.stdout || ""));
    if (!parsed.ok) {
      ctx.ui.notify(String(result.stderr || parsed.error), "error");
      return;
    }
    ctx.ui.notify(renderPlanReview(parsed.value), parsed.value.blocked ? "warning" : "info");
  } catch (error) {
    ctx.ui.notify(`plan-review failed: ${String(error)}`, "error");
  }
}
