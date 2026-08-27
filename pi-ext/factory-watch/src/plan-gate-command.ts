import { spawnSync } from "node:child_process";
import { isAbsolute, resolve } from "node:path";
import type { ExtCommandCtx } from "./pi-types.js";

export interface PlanGateArgs {
  intent: string;
  spec: string;
  plan: string;
  runId: string;
}

export interface PlanGateCommand {
  bin: string;
  args: string[];
}

const SAFE_RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

export function validatePlanGatePath(value: string): boolean {
  if (value.length === 0 || value !== value.trim() || /[\u0000-\u001f\u007f]/.test(value)) return false;
  if (isAbsolute(value) || /^[A-Za-z]:/.test(value)) return false;
  const parts = value.replaceAll("\\", "/").split("/");
  return parts.every((part) => part !== "" && part !== "." && part !== "..");
}

export function parsePlanGateArgs(args: string): PlanGateArgs | null {
  const parts = args.trim().split(/\s+/);
  if (parts.length !== 4) return null;
  const [intent, spec, plan, runId] = parts;
  if (
    intent === undefined ||
    spec === undefined ||
    plan === undefined ||
    runId === undefined ||
    !validatePlanGatePath(intent) ||
    !validatePlanGatePath(spec) ||
    !validatePlanGatePath(plan) ||
    !SAFE_RUN_ID.test(runId)
  ) {
    return null;
  }
  return { intent, spec, plan, runId };
}

export function buildPlanGateCommand(root: string, args: PlanGateArgs): PlanGateCommand {
  return {
    bin: "uv",
    args: [
      "run",
      "coherence",
      "plan",
      "bootstrap",
      "--project-root",
      resolve(root),
      "--intent",
      args.intent,
      "--spec",
      args.spec,
      "--plan",
      args.plan,
      "--run-id",
      args.runId,
      "--decompose",
      "--json",
    ],
  };
}

export function runPlanGate(ctx: ExtCommandCtx, rawArgs: string): void {
  const args = parsePlanGateArgs(rawArgs);
  if (args === null) {
    ctx.ui.notify("usage: /plan-gate <intent.json> <spec.md> <plan.md> <run-id>", "error");
    return;
  }
  const command = buildPlanGateCommand(ctx.cwd, args);
  try {
    const result = spawnSync(command.bin, command.args, {
      cwd: resolve(ctx.cwd),
      encoding: "utf-8",
      timeout: 120000,
    });
    const output = String(result.stdout || result.stderr || "plan-gate returned no output").trim();
    ctx.ui.notify(output, result.status === 0 ? "info" : "error");
  } catch (error) {
    ctx.ui.notify(`plan-gate failed: ${String(error)}`, "error");
  }
}
