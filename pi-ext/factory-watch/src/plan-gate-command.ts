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

export interface PlanHandoffArgs {
  runId: string;
  workflow: string;
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

export function parsePlanHandoffArgs(raw: string): PlanHandoffArgs | null {
  const parts = raw.trim().split(/\s+/);
  if (parts.length !== 2 || parts[0] === undefined || parts[1] === undefined) return null;
  if (!SAFE_RUN_ID.test(parts[0]) || !["standard-development", "health-recovery", "feature-planning"].includes(parts[1])) return null;
  return { runId: parts[0], workflow: parts[1] };
}

export function buildPlanHandoffCommand(root: string, args: PlanHandoffArgs): PlanGateCommand {
  return { bin: "uv", args: ["run", "coherence", "plan", "handoff", "--project-root", resolve(root), "--run-id", args.runId, "--workflow", args.workflow, "--json"] };
}

export function runPlanHandoff(ctx: ExtCommandCtx, rawArgs: string): void {
  const args = parsePlanHandoffArgs(rawArgs);
  if (args === null) { ctx.ui.notify("usage: /plan-handoff <run-id> <workflow>", "error"); return; }
  try {
    const result = spawnSync("uv", buildPlanHandoffCommand(ctx.cwd, args).args, { cwd: resolve(ctx.cwd), encoding: "utf-8", timeout: 120000 });
    ctx.ui.notify(String(result.stdout || result.stderr || "plan-handoff returned no output").trim(), result.status === 0 ? "info" : "error");
  } catch (error) { ctx.ui.notify(`plan-handoff failed: ${String(error)}`, "error"); }
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
