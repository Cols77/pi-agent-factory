import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// This file lives at <factory-repo>/pi-ext/factory-watch/src/, so three levels
// up is the factory repo root -- the same reasoning handler.test.ts uses to
// find REPO_ROOT.
export function factorySkillsDir(): string {
  return join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", ".pi", "skills");
}

/**
 * Resolve a skill by name, preferring the target project's own vendored copy
 * and falling back to the one shipped with the factory.
 *
 * The fallback matters because commands run with ctx.cwd set to whatever repo
 * the human is working in, and a target project may vendor no skills at all
 * (cool_physical_ai_project's .pi/ is empty). Without it, a factory command
 * would only work inside the factory's own checkout.
 */
export function findSkillFile(cwd: string, name: string): string | null {
  const candidates = [
    join(cwd, ".pi", "skills", name, "SKILL.md"),
    join(factorySkillsDir(), name, "SKILL.md"),
  ];
  return candidates.find((p) => existsSync(p)) ?? null;
}
