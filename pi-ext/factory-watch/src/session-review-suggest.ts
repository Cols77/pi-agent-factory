// Pi-side consumer of the factory's structured session-review outcome.
//
// When a factory run finishes, the orchestrator persists
//   sessions/.factory-runs/by-session/<run_id>/session-review.json
// (next to the checkpoint) and prints a one-line pointer on exit. This tool
// reads that artifact for a project and turns its `suggestions` (targeted at
// prompt/skill/role/gate/config) into a concrete, actionable proposal that the
// invoking pi session can use to propose factory-run updates automatically.
//
// It only *proposes*; it never writes to the factory checkout itself.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { Type } from "typebox";
import type { PiApi } from "./pi-types.js";

const MAX_OUTPUT_BYTES = 50 * 1024;

interface Suggestion {
  target?: unknown;
  summary?: unknown;
  proposed?: unknown;
  evidence?: unknown;
}

interface MappedSuggestion {
  target: string;
  summary: string;
  proposed: string;
  evidence: string;
  target_file: string;
}

interface Artifact {
  schema_version?: unknown;
  run_id?: unknown;
  task_id?: unknown;
  final_outcome?: unknown;
  agent_session_id?: unknown;
  ok?: unknown;
  suggestions?: unknown;
  kb_added?: unknown;
  summary_path?: unknown;
}

/** Map a session-review suggestion target to the factory file most likely to
 * hold the change, so pi has a concrete place to propose editing. These are
 * relative to the FACTORY checkout (pi-agent-factory), not the target repo. */
function targetFile(target: string): string {
  switch (target) {
    case "gate":
    case "config":
      return ".factory/factory.yaml";
    case "prompt":
    case "role":
      return "src/factory/orchestrator/roles.py";
    case "skill":
      return ".pi/skills/<name>/SKILL.md";
    default:
      return "(no single file; review the suggestion)";
  }
}

function readJson<T>(path: string): T | null {
  try {
    return JSON.parse(readFileSync(path, "utf-8")) as T;
  } catch {
    return null;
  }
}

/** List run directories that carry a session-review.json, oldest first,
 * skipping runs that were abandoned (an abandoned.json marker closes them and
 * they are ignored by the factory's own "current" check). */
function listReviewRuns(cwd: string): Array<{ runId: string; path: string; mtime: number }> {
  const root = join(cwd, "sessions", ".factory-runs", "by-session");
  let names: string[];
  try {
    names = readdirSync(root, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name);
  } catch {
    return [];
  }
  const runs: Array<{ runId: string; path: string; mtime: number }> = [];
  for (const name of names) {
    const dir = join(root, name);
    if (readFileIfExists(join(dir, "abandoned.json")) !== null) continue;
    const path = join(dir, "session-review.json");
    try {
      statSync(path);
    } catch {
      continue;
    }
    let mtime = 0;
    try {
      mtime = statSync(path).mtimeMs;
    } catch {
      mtime = 0;
    }
    runs.push({ runId: name, path, mtime });
  }
  runs.sort((a, b) => a.mtime - b.mtime);
  return runs;
}

function readFileIfExists(path: string): string | null {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return null;
  }
}

interface SuggestInput {
  run_id?: string;
}

function buildOutput(
  cwd: string,
  requestedRunId: string | undefined,
): Record<string, unknown> {
  if (requestedRunId !== undefined && requestedRunId !== "") {
    const artifact = readJson<Artifact>(
      join(
        cwd,
        "sessions",
        ".factory-runs",
        "by-session",
        requestedRunId,
        "session-review.json",
      ),
    );
    if (artifact === null) {
      return {
        status: "not-found",
        run_id: requestedRunId,
        error: "no session-review.json for this run (abandoned, pre-structured, or not a run)",
        instruction: "Missing outcome is unknown; do not infer suggestions.",
      };
    }
    return summarizeArtifact(requestedRunId, artifact);
  }

  const runs = listReviewRuns(cwd);
  if (runs.length === 0) {
    return {
      status: "none",
      error:
        "no session-review artifacts found; run a factory run with the structured session-review " +
        "outcome first",
    };
  }
  const latest = runs[runs.length - 1];
  if (latest === undefined) {
    return { status: "none", error: "no session-review artifacts found" };
  }
  const artifact = readJson<Artifact>(latest.path);
  if (artifact === null) {
    return { status: "not-found", run_id: latest.runId, error: "artifact unreadable" };
  }
  const out = summarizeArtifact(latest.runId, artifact);
  out["available_runs"] = runs.map((r) => ({
    run_id: r.runId,
    mtime: new Date(r.mtime).toISOString(),
  }));
  return out;
}

function summarizeArtifact(runId: string, artifact: Artifact): Record<string, unknown> {
  const rawSuggestions = Array.isArray(artifact.suggestions) ? artifact.suggestions : [];
  const suggestions: MappedSuggestion[] = rawSuggestions
    .filter((item): item is Record<string, unknown> => item !== null && typeof item === "object")
    .map((item) => {
      const target = typeof item.target === "string" ? item.target : "other";
      return {
        target,
        summary: typeof item.summary === "string" ? item.summary : "",
        proposed: typeof item.proposed === "string" ? item.proposed : "",
        evidence: typeof item.evidence === "string" ? item.evidence : "",
        target_file: targetFile(target),
      };
    });

  const byTarget: Record<string, number> = {};
  for (const s of suggestions) byTarget[s.target] = (byTarget[s.target] ?? 0) + 1;

  return {
    status: "ok",
    run_id: runId,
    task_id: artifact.task_id,
    final_outcome: artifact.final_outcome,
    agent_session_id: artifact.agent_session_id,
    ok: artifact.ok,
    counts_by_target: byTarget,
    kb_added: Array.isArray(artifact.kb_added) ? artifact.kb_added : [],
    summary_path: artifact.summary_path,
    suggestions,
    // A ready-to-print proposal block a pi session can feed straight into an
    // edit/review step against the factory checkout (C:/coding/pi-agent-factory).
    proposal: renderProposal(runId, suggestions),
  };
}

function renderProposal(runId: string, suggestions: MappedSuggestion[]): string {
  if (suggestions.length === 0) {
    return `Run ${runId} produced no factory-run suggestions; the session-reviewer found nothing worth changing.`;
  }
  const lines = [
    `Session-review for run ${runId} proposes ${suggestions.length} factory-run change(s). ` +
      "Review each below, confirm the proposed change is sound, and apply it to the factory " +
      "checkout (pi-agent-factory) under normal change discipline.",
  ];
  for (const s of suggestions) {
    lines.push(`- [${s.target}] ${s.summary}`);
    lines.push(`  proposed: ${s.proposed}`);
    if (s.evidence) lines.push(`  evidence: ${s.evidence}`);
    lines.push(`  where: ${targetFile(s.target)}`);
  }
  return lines.join("\n");
}

export function buildSessionReviewSuggestTools() {
  const factoryRunSuggest = {
    name: "factory_run_suggest",
    label: "Session-review suggestions",
    description:
      "Read the structured session-review outcome of the most recent (or a given) factory run " +
      "and return concrete, targeted suggestions for improving the factory-run pipeline " +
      "(prompt/skill/role/gate/config), mapped to the factory files where each change belongs. " +
      "Use after a factory run to turn its session-review outcome into proposed updates.",
    parameters: Type.Object({
      run_id: Type.Optional(
        Type.String({
          description:
            "Optional specific run id (e.g. 2026-08-09T03-57-47Z). Defaults to the latest run " +
            "with a session-review artifact, skipping abandoned runs.",
        }),
      ),
    }),
    async execute(
      _callId: string,
      params: SuggestInput,
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: { cwd: string },
    ) {
      const data = buildOutput(ctx.cwd, params.run_id);
      const full = JSON.stringify(data, null, 2);
      const bytes = Buffer.from(full, "utf-8");
      const text =
        bytes.length <= MAX_OUTPUT_BYTES
          ? full
          : `${bytes.subarray(0, MAX_OUTPUT_BYTES).toString("utf-8")}\n[truncated]`;
      return { content: [{ type: "text" as const, text }], details: data };
    },
  };

  return [factoryRunSuggest];
}

export function registerSessionReviewSuggestTools(pi: Pick<PiApi, "registerTool">): void {
  for (const tool of buildSessionReviewSuggestTools()) pi.registerTool(tool);
}
