// Format helpers for the `eng_*` Engineering Context agent tools (Inc 4, D1).
// Each input mirrors a `factory.system` JSON payload exactly; this file only
// renders it into compact cockpit text, it never re-derives state that Python
// already computed (Program Architecture §6).
import type {
  SimGoalEvidence,
  SimLatest,
  SimMetricEntry,
  SimRun,
  SystemDiagram,
  SystemGoal,
  SystemGoalsList,
  SystemVcycle,
} from "./system-cli.js";

export function formatDiagram(d: SystemDiagram): string {
  const lines = [`diagram: ${d.id}`, `  title: ${d.title}`];
  if (d.diagram_path) lines.push(`  path: ${d.diagram_path}`);
  else lines.push("  path: (none)");
  for (const err of d.errors) lines.push(`  ! ${err}`);
  return lines.join("\n");
}

function formatRun(run: SimRun): string {
  const lines = [
    `  run: ${run.run}  [${run.result ?? "no result"}]`,
    `    experiment: ${run.experiment}`,
    `    feature: ${run.feature}`,
    `    commit: ${run.commit ?? "none"}`,
  ];
  if (run.goals.length) lines.push(`    goals: ${run.goals.join(", ")}`);
  if (run.requirements.length) lines.push(`    requirements: ${run.requirements.join(", ")}`);
  for (const err of run.scope_errors) lines.push(`    ! scope error: ${err}`);
  return lines.join("\n");
}

export function formatSimRun(run: SimLatest): string {
  if (!run.run) return "no simulation run";
  return formatRun(run);
}

export function formatSimLatest(run: SimLatest): string {
  if (!run.run) return "no simulation run for this feature";
  return `latest simulation for ${run.feature}:\n${formatRun(run)}`;
}

export function formatSimFailure(run: SimLatest): string {
  if (!run.run) return "no failed simulation run for this feature";
  return `latest failure for ${run.feature}:\n${formatRun(run)}`;
}

export function formatSimMetric(entries: SimMetricEntry[]): string {
  if (entries.length === 0) return "no metric history";
  const lines = [`metric history: ${entries.length} entry(ies)`];
  for (const e of entries) lines.push(`  ${e.run}: ${e.value}`);
  return lines.join("\n");
}

export function formatSimGoalEvidence(evidence: SimGoalEvidence): string {
  const lines = [`goal evidence for ${evidence.goal}:`];
  if (evidence.runs.length === 0) {
    lines.push("  no runs");
    return lines.join("\n");
  }
  for (const run of evidence.runs) {
    lines.push(`  ${run.run}  [${run.result ?? "no result"}] (${run.experiment})`);
  }
  return lines.join("\n");
}

export function formatVcycle(v: SystemVcycle): string {
  const lines = [`vcycle: ${v.vcycle.anchor}`];
  for (const side of [...v.vcycle.definition, ...v.vcycle.verification]) {
    const ids = side.nodes.map((n) => n.id);
    lines.push(`  ${side.label}: ${ids.length ? ids.join(", ") : "(empty)"}`);
  }
  if (v.vcycle.goals.length) lines.push(`  goals: ${v.vcycle.goals.map((n) => n.id).join(", ")}`);
  if (v.vcycle.metrics.length) lines.push(`  metrics: ${v.vcycle.metrics.map((n) => n.id).join(", ")}`);
  return lines.join("\n");
}

export function formatGoal(goal: SystemGoal): string {
  const lines = [
    `goal: ${goal.id}`,
    `  title: ${goal.title}`,
    `  state: ${goal.state}`,
    `  feature: ${goal.feature.length ? goal.feature.join(", ") : "none"}`,
    `  requirements: ${goal.requirements.length ? goal.requirements.join(", ") : "none"}`,
    `  target: ${goal.target}`,
  ];
  for (const err of goal.scope_errors) lines.push(`  ! scope error: ${err}`);
  return lines.join("\n");
}

export function formatGoalList(list: SystemGoalsList): string {
  const lines = [`goals for ${list.scope}:`];
  if (list.goals.length === 0) {
    lines.push("  none");
    return lines.join("\n");
  }
  for (const g of list.goals) lines.push(`  ${g.id}  [${g.state}]  ${g.title}`);
  return lines.join("\n");
}
