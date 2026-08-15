// Thin `/task <feat:...>` preamble (Inc 4, Task 4).
//
// Replays spec §26 steps 1-4 by calling the read tools IN ORDER and printing a
// compact context block: 1. reconstruct feature context, 2. inspect
// requirements, 3. inspect active goals, 4. determine affected design/code.
// All data comes from the deterministic `factory.system` CLI (Python is the
// single source of truth); this module only renders a compact block and never
// re-derives state (Program Architecture §6).
import { spawnSync } from "node:child_process";

export interface TaskReadSurface {
  featureContext(featureId: string): string;
  requirements(featureId: string): string;
  goals(featureId: string): string;
  affectedDesign(featureId: string): string;
}

interface NodeFact {
  id?: string;
  kind?: string;
  title?: string;
}

interface TaskEntry {
  task?: string;
}

function indent(text: string): string {
  return text
    .split("\n")
    .map((l) => (l.trim() ? `  ${l}` : l))
    .join("\n");
}

// spec §26 steps 1-4 in a FIXED order. The ordering is the contract the unit
// test pins: context -> requirements -> goals -> affected design/code.
export function buildTaskPreamble(featureId: string, reads: TaskReadSurface): string {
  return [
    `task context for ${featureId}`,
    "1. feature context",
    indent(reads.featureContext(featureId)),
    "2. requirements",
    indent(reads.requirements(featureId)),
    "3. active goals",
    indent(reads.goals(featureId)),
    "4. affected design/code",
    indent(reads.affectedDesign(featureId)),
  ].join("\n");
}

function safeParse(json: string): Record<string, unknown> | null {
  try {
    return json ? (JSON.parse(json) as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

// Real surface bound to the `factory.system` CLI. Presentation-only rendering
// of the Python JSON payloads (repeatable, no re-derivation).
export function buildCliTaskReads(cwd: string): TaskReadSurface {
  const sys = (...sub: string[]) => {
    const res = spawnSync(
      "uv",
      ["run", "python", "-m", "factory.system", ...sub, "--json"],
      { cwd, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 },
    );
    return (res.stdout ?? "").toString().trim();
  };

  const nodeIds = (value: unknown): string[] =>
    Array.isArray(value)
      ? (value as NodeFact[]).map((n) => String(n?.id ?? "")).filter(Boolean)
      : [];

  return {
    featureContext(featureId: string): string {
      const p = safeParse(sys("brief", "--scope", `feat:${featureId}`));
      const d = (p?.dossier ?? {}) as Record<string, unknown>;
      if (!p) return `(feature context unavailable: ${featureId})`;
      const title = String(d.title ?? d.id ?? featureId);
      const lines = [title];
      const reqs = nodeIds(d.requirements);
      if (reqs.length) lines.push(`requirements: ${reqs.join(", ")}`);
      if (Array.isArray(d.goal_ids) && (d.goal_ids as unknown[]).length) {
        lines.push(`goals: ${(d.goal_ids as string[]).join(", ")}`);
      }
      if (Array.isArray(d.metric_ids) && (d.metric_ids as unknown[]).length) {
        lines.push(`metrics: ${(d.metric_ids as string[]).join(", ")}`);
      }
      const intent = String(d.intent ?? "").trim();
      if (intent) lines.push(`intent: ${intent.slice(0, 200)}`);
      return lines.join("\n");
    },

    requirements(featureId: string): string {
      const p = safeParse(sys("vcycle", "--scope", `feat:${featureId}`));
      const vp = (p?.vcycle ?? {}) as { definition?: Array<{ nodes?: NodeFact[] }> };
      const reqs = new Set<string>();
      for (const side of vp.definition ?? []) {
        for (const n of side.nodes ?? []) if (n?.id) reqs.add(String(n.id));
      }
      const list = [...reqs];
      return list.length ? list.join(", ") : `(no requirements declared for ${featureId})`;
    },

    goals(featureId: string): string {
      const p = safeParse(sys("goal", "list", "--scope", `feat:${featureId}`));
      const gs = (p?.goals ?? []) as Array<{ id?: string; state?: string; title?: string }>;
      const list = gs
        .map((g) => `${g.id ?? ""} [${g.state ?? ""}] ${g.title ?? ""}`.trim())
        .filter(Boolean);
      return list.length ? list.join("\n") : `(no goals bound to ${featureId})`;
    },

    affectedDesign(featureId: string): string {
      const p = safeParse(sys("brief", "--scope", `feat:${featureId}`));
      const d = (p?.dossier ?? {}) as Record<string, unknown>;
      const lines: string[] = [];
      const design = nodeIds(d.design_records);
      if (design.length) lines.push(`design: ${design.join(", ")}`);
      const tasks = Array.isArray(d.implementation)
        ? (d.implementation as TaskEntry[]).map((t) => String(t?.task ?? "")).filter(Boolean)
        : [];
      if (tasks.length) lines.push(`tasks: ${tasks.join(", ")}`);
      const files = Array.isArray(d.implementation_files)
        ? (d.implementation_files as string[]).filter(Boolean)
        : [];
      if (files.length) lines.push(`files: ${files.join(", ")}`);
      return lines.length ? lines.join("\n") : `(no affected design/code resolved for ${featureId})`;
    },
  };
}
