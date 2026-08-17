// /coverage-review — deterministic feature-scoped coverage audit, factory-run
// style: pick a feature, launch the Python runner, watch per-SR progress, drive
// the human gates, and present the final report.
import { spawn } from "node:child_process";
import { openSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getMarkdownTheme } from "@earendil-works/pi-coding-agent";
import { runJsonCli } from "./cli-runner.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { ScrollableMarkdown } from "./scrollable-markdown.js";

export interface FeatureSummary {
  id: string;
  title: string;
  declared_srs: number;
}

export interface CoverageRunStatus {
  run_id?: string;
  feature?: string;
  phase?: string;
  updated_at?: string;
  srs?: Record<string, { state?: string; session_id?: string | null }>;
  gate?: { outcome?: string; failed?: string[]; warned?: string[]; degraded?: string[] } | null;
  proposed_requirements?: Array<{
    candidate_id?: string;
    rationale?: string;
    evidence_of_gap?: string;
  }>;
  suggested_actions?: string[];
  error?: string | null;
}

export interface CoverageDecision {
  proposed_requirements: Array<{
    candidate_id: string;
    decision: "accept" | "reject" | "defer";
    reason?: string;
  }>;
  noted_actions: string[];
}

const POLL_INTERVAL_MS = 1000;

export function listFeatures(cwd: string): FeatureSummary[] {
  const result = runJsonCli<FeatureSummary[]>(cwd, "uv", [
    "run",
    "python",
    "-m",
    "factory.coverage",
    "list-features",
    "--project-root",
    cwd,
  ]);
  return result.ok ? result.value : [];
}

export function parseFeatureIdFromArgs(args: string): string | null {
  const trimmed = args.trim();
  if (trimmed === "" || trimmed.startsWith("-")) return null;
  const m = /^(?:feat:)?([A-Za-z0-9][A-Za-z0-9_-]*)$/.exec(trimmed);
  return m ? m[1]! : null;
}

export function findLatestStatus(cwd: string, feature: string): string | null {
  const reviewsDir = join(cwd, "coverage-reviews");
  const prefix = `${feature}-`;
  let latest: string | null = null;
  let latestMtime = -1;
  let names: import("node:fs").Dirent[] = [];
  try {
    names = readdirSync(reviewsDir, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const name of names) {
    if (!name.isDirectory() || !name.name.startsWith(prefix)) continue;
    const statusPath = join(reviewsDir, name.name, "status.json");
    try {
      const mtime = statSync(statusPath).mtimeMs;
      if (mtime > latestMtime) {
        latestMtime = mtime;
        latest = statusPath;
      }
    } catch {
      // no status.json yet in this run dir; skip
    }
  }
  return latest;
}

export function readStatus(statusPath: string): CoverageRunStatus | null {
  try {
    return JSON.parse(readFileSync(statusPath, "utf-8")) as CoverageRunStatus;
  } catch {
    return null;
  }
}

export function formatCoverageStatus(status: CoverageRunStatus | null): string[] {
  if (status === null) return ["coverage: waiting for run to start..."];
  const lines = [`coverage: ${status.feature ?? "?"} (${status.run_id ?? "?"})`];
  lines.push(`phase: ${status.phase ?? "?"}`);
  const srs = status.srs ?? {};
  const counts = { pending: 0, running: 0, done: 0, failed: 0, skipped: 0 };
  for (const sr of Object.values(srs)) {
    const s = sr.state ?? "pending";
    if (s in counts) counts[s as keyof typeof counts] += 1;
  }
  lines.push(
    `SRs: ${counts.done} done, ${counts.running} running, ${counts.pending} pending, ` +
      `${counts.failed} failed, ${counts.skipped} skipped`,
  );
  if (status.gate) {
    lines.push(`gate: ${status.gate.outcome ?? "?"}`);
    if (status.gate.failed?.length) lines.push(`  failed: ${status.gate.failed.join(", ")}`);
    if (status.gate.warned?.length) lines.push(`  warned: ${status.gate.warned.join(", ")}`);
    if (status.gate.degraded?.length) lines.push(`  degraded: ${status.gate.degraded.join(", ")}`);
  }
  if (status.phase === "gates") {
    lines.push("⚠ human decision needed — proposed requirements / actions pending");
  }
  if (status.error) lines.push(`error: ${status.error}`);
  return lines;
}

export async function runCoverageReview(args: string, ctx: ExtCommandCtx): Promise<void> {
  const picked = parseFeatureIdFromArgs(args);
  const features = listFeatures(ctx.cwd);
  let feature = picked;

  if (feature === null) {
    if (features.length === 0) {
      ctx.ui.notify("no features found under docs/features/", "error");
      return;
    }
    const option = await ctx.ui.select(
      "Feature to audit",
      features.map((f) => `${f.id}  ${f.title}  (${f.declared_srs} SRs)`),
    );
    if (option === undefined) return;
    const [id] = option.split(/\s+/);
    feature = id ?? null;
    if (feature === null) return;
  }

  if (!features.some((f) => f.id === feature)) {
    ctx.ui.notify(`feature ${feature} not found under docs/features/`, "error");
    return;
  }

  if (ctx.model === undefined) {
    ctx.ui.notify("no model selected in this session — can't launch the audit", "error");
    return;
  }

  const logPath = join(ctx.cwd, "sessions", ".factory-coverage.log");
  const logFd = openSync(logPath, "a");
  const cmd = [
    "run",
    "python",
    "-m",
    "factory.coverage",
    "run",
    feature,
    "--project-root",
    ctx.cwd,
    "--provider",
    ctx.model.provider,
    "--model",
    ctx.model.id,
  ];
  const child = spawn("uv", cmd, { cwd: ctx.cwd, detached: true, stdio: ["ignore", logFd, logFd] });
  child.unref();
  ctx.ui.notify(`coverage review started for ${feature} (log: sessions/.factory-coverage.log)`, "info");

  let pollHandle: ReturnType<typeof setInterval> | undefined;
  const stopPolling = () => {
    if (pollHandle !== undefined) clearInterval(pollHandle);
    pollHandle = undefined;
  };

  const finish = (finalStatus: CoverageRunStatus) => {
    stopPolling();
    ctx.ui.setWidget("coverage", undefined);
    const outcome = finalStatus.gate?.outcome ?? "unknown";
    ctx.ui.notify(`coverage review finished for ${feature}: gate ${outcome}`, "info");
  };

  const promptGates = (status: CoverageRunStatus): void => {
    const runDir = latestRunDir(ctx.cwd, feature);
    if (runDir === null) return;
    const decisions: CoverageDecision = {
      proposed_requirements: [],
      noted_actions: status.suggested_actions ?? [],
    };
    void (async () => {
      for (const proposal of status.proposed_requirements ?? []) {
        const id = proposal.candidate_id ?? "?";
        const choice = await ctx.ui.select(
          `Proposed requirement ${id}: ${proposal.rationale ?? ""}\n${proposal.evidence_of_gap ?? ""}`,
          ["accept (route to doctor)", "reject", "defer"],
        );
        if (choice === undefined) continue;
        let decision: "accept" | "reject" | "defer" = "defer";
        if (choice.startsWith("accept")) decision = "accept";
        else if (choice.startsWith("reject")) decision = "reject";
        let reason: string | undefined;
        if (decision !== "accept") {
          reason = (await ctx.ui.editor("Reason (recorded with the decision)", "")) || undefined;
        }
        decisions.proposed_requirements.push({ candidate_id: id, decision, reason });
      }
      writeFileSync(join(runDir, "decisions.json"), JSON.stringify(decisions, null, 2));
      ctx.ui.notify("decisions recorded — runner will finalize", "info");
    })();
  };

  pollHandle = setInterval(() => {
    try {
      const statusPath = findLatestStatus(ctx.cwd, feature);
      const status = statusPath === null ? null : readStatus(statusPath);
      ctx.ui.setWidget("coverage", formatCoverageStatus(status));
      if (status === null) return;
      if (status.phase === "gates") {
        stopPolling();
        promptGates(status);
        return;
      }
      if (status.phase === "done" || status.phase === "failed" || status.phase === "gates_timeout") {
        finish(status);
        if (status.phase === "done") {
          void showReport(ctx, feature, status.run_id);
        }
      }
    } catch {
      stopPolling();
    }
  }, POLL_INTERVAL_MS);
}

function latestRunDir(cwd: string, feature: string): string | null {
  const statusPath = findLatestStatus(cwd, feature);
  return statusPath === null ? null : statusPath.slice(0, -"status.json".length);
}

async function showReport(ctx: ExtCommandCtx, feature: string, runId?: string): Promise<void> {
  const reportPath = join(ctx.cwd, "coverage-reviews", `${feature}-${runId ?? ""}`, "report.json");
  let text: string;
  try {
    text = readFileSync(reportPath, "utf-8");
  } catch {
    ctx.ui.notify("report not found", "warning");
    return;
  }
  const json = JSON.parse(text) as { feature?: string; run_id?: string; gate?: { outcome?: string } };
  const lines = [
    `Coverage Review report: ${json.feature ?? feature}`,
    `run: ${json.run_id ?? "?"}`,
    `gate: ${json.gate?.outcome ?? "?"}`,
    "",
    text,
  ];
  await ctx.ui.custom<void>(
    (tui, _theme, _keybindings, done) =>
      new ScrollableMarkdown(lines.join("\n"), getMarkdownTheme(), tui, () => done(undefined)),
    { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } },
  );
}

export function registerCoverageRun(pi: PiApi): void {
  pi.registerCommand("coverage-review", {
    description: "Run a feature-scoped requirement coverage audit (pick a feature, watch the run)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      await runCoverageReview(args, ctx);
    },
  });
}
