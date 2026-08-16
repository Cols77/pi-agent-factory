// Shared path helpers for the factory's own checkout.
//
// Kept in its own module so factory-init-command.ts (which registers /factory-init
// and needs the subagent tool) and subagent-tool.ts (which needs the extension
// path to spawn children) can both import it without a circular dependency.

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// This file lives at <factory-repo>/pi-ext/factory-watch/src/, so three levels
// up is the factory repo root (same reasoning as factory-skills.ts).
const FACTORY_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

export function factoryRoot(): string {
  return FACTORY_ROOT;
}

/** Absolute path to the factory-watch extension entry that child subagents load. */
export function agentExtensionPath(): string {
  return join(FACTORY_ROOT, "pi-ext", "factory-watch", "src", "index.ts");
}
