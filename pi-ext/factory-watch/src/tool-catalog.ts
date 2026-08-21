// Catalog of the factory tools registered into a Pi session.
//
// This is a single derived source for the "available factory tools" that the
// factory bootstrap can surface (currently baked into the AGENTS.md managed
// block by /factory-init). It is NOT hand-maintained: each family is derived
// from the exact builder/definition the extension registers, so adding a tool
// to one of those modules automatically changes this catalog on the next
// build -- no separate name list to forget to update.
//
// The families mirror how the extension registers its tools (see index.ts):
//   - delegation: the subagent tool (child Pi process hand-off)
//   - trace      : determinisic traceability enumerators/writers
//   - system     : the read-only system navigator surface
//   - engineering: the read-only + action engineering-context tools
//   - session-review: post-run session-review suggestions
//
// The /factory-init command passes this into runFactoryInit, which weaves a
// "Factory tools:" line into the AGENTS.md managed block so the agent's system
// prompt reflects the project's current tool surface.

import { buildEngContextTools } from "./eng-context-tools.js";
import { buildSystemContextTools } from "./system-context-tools.js";
import { buildSessionReviewSuggestTools } from "./session-review-suggest.js";
import {
  traceNextTool,
  traceLinkTool,
  traceExemptTool,
  traceDeferTool,
  traceCheckTool,
} from "./trace-tools.js";
import { subagentTool } from "./subagent-tool.js";

export interface FactoryToolEntry {
  name: string;
  family: string;
}

/** Name of the family most tools of this kind are grouped by on disk. */
export const FACTORY_TOOL_FAMILIES = {
  delegation: "delegation",
  trace: "trace",
  system: "system-navigator",
  engineering: "engineering-context",
  review: "session-review",
} as const;

/** Derive the full catalog from what the extension actually registers. */
export function factoryToolsCatalog(): FactoryToolEntry[] {
  const eng = buildEngContextTools().map((t) => ({
    name: t.name,
    family: FACTORY_TOOL_FAMILIES.engineering,
  }));
  const sys = buildSystemContextTools().map((t) => ({
    name: t.name,
    family: FACTORY_TOOL_FAMILIES.system,
  }));
  const trace = [traceNextTool, traceLinkTool, traceExemptTool, traceDeferTool, traceCheckTool].map(
    (t) => ({ name: t.name, family: FACTORY_TOOL_FAMILIES.trace }),
  );
  const review = buildSessionReviewSuggestTools().map((t) => ({
    name: t.name,
    family: FACTORY_TOOL_FAMILIES.review,
  }));
  const delegation = [{ name: subagentTool.name, family: FACTORY_TOOL_FAMILIES.delegation }];
  return [...delegation, ...trace, ...sys, ...eng, ...review];
}

/** Render the catalog as a compact, grouped "family: one, two" line set. */
export function formatToolCatalog(entries: FactoryToolEntry[]): string {
  const byFamily = new Map<string, string[]>();
  for (const e of entries) {
    const list = byFamily.get(e.family) ?? [];
    list.push(e.name);
    byFamily.set(e.family, list);
  }
  const families: string[] = [];
  for (const [family, names] of byFamily) {
    families.push(`${family} (${names.join(", ")})`);
  }
  return families.join("; ");
}