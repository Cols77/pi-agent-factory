import { isPathAllowed } from "./allow.js";
import type { ToolCallEvent, ExtCtx, ToolCallResult } from "./pi-types.js";

export const WRITE_TOOLS: readonly string[] = ["write", "edit"];

export function parseBashPolicy(raw: string | undefined): "allow" | "deny" {
  return raw === "allow" ? "allow" : "deny";
}

export function decide(
  event: ToolCallEvent,
  ctx: ExtCtx,
  allowGlobs: string[],
  bash: "allow" | "deny",
): ToolCallResult {
  if (event.toolName === "bash") {
    if (bash === "deny") {
      return { block: true, reason: "scope-guard: bash is disabled for this agent role" };
    }
    return undefined;
  }

  if (WRITE_TOOLS.includes(event.toolName)) {
    const path = event.input.path;
    if (!path) {
      return { block: true, reason: "scope-guard: write tool called without a path" };
    }
    if (!isPathAllowed(path, ctx.cwd, allowGlobs)) {
      return { block: true, reason: `scope-guard: '${path}' is outside this agent's write scope` };
    }
  }

  return undefined;
}
