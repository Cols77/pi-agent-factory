import type { TraceCheckResult, TraceProposal } from "./trace-cli.js";

export function formatNoGaps(): string {
  return "No pending gaps. Every gap is linked, exempted, or deferred. Run trace_check to confirm.";
}

// The four kinds with no candidate pool. One shared message steered all of them
// toward deferral -- and for a requirement, deferral is the only legal move, since
// requirements cannot be exempted. That turned an honest disposition into a
// pressure valve on a gate that then went green.
const NO_CANDIDATE_GUIDANCE: Record<string, string> = {
  sr_unvalidated:
    "This gap closes by running validation, not by linking. A requirement can never be " +
    "waived. Defer it only if validation genuinely cannot be run yet, and record what has " +
    "to happen first.",
  sr_stale:
    "The recorded result predates a change to the statement or binding. It closes by " +
    "running validation again, not by linking. Defer it only if that cannot happen yet.",
  dangling_upstream:
    "The upstream target does not exist. Fix the reference or create the missing " +
    "requirement; deferring records the dangle, it does not resolve it.",
  task_plan_missing:
    "source_plan points at a file that is not there. Correct it with trace_link " +
    "--source-plan, or use trace_exempt if this task legitimately has no plan.",
};

const DEFAULT_NO_CANDIDATE_GUIDANCE =
  "Candidates: no candidates exist for this gap kind. Defer it, or exempt it if it is a " +
  "task or plan that legitimately has nothing to link to.";

function formatPending(proposal: TraceProposal): string[] {
  // The extension shells out to the Python CLI, so it can be paired with an
  // older one that does not send `pending`. Degrade to the previous output
  // rather than crashing the renderer.
  if (!proposal.pending?.length) return [];
  return [
    "",
    `All ${proposal.pending.length} pending gap(s) — the focused one above is a default, ` +
      "not a queue. Pass node_id to trace_next to work any of these instead:",
    ...proposal.pending.map((p) => `  ${p.node_id.padEnd(24)} ${p.kind.padEnd(18)} ${p.detail}`),
  ];
}

export function formatProposal(proposal: TraceProposal): string {
  const lines = [
    `Gap: ${proposal.gap.node_id}  [${proposal.gap.kind}]`,
    `Node: ${proposal.node_title}`,
    `Detail: ${proposal.gap.detail}`,
    `Pending gaps remaining: ${proposal.pending_total}`,
    "",
    "Excerpt:",
    proposal.node_excerpt,
    "",
  ];

  if (proposal.candidates.length === 0) {
    lines.push(NO_CANDIDATE_GUIDANCE[proposal.gap.kind] ?? DEFAULT_NO_CANDIDATE_GUIDANCE);
    lines.push(...formatPending(proposal));
    return lines.join("\n");
  }

  lines.push(
    `Candidates (${proposal.candidates.length}, ordered by shared-term overlap — that ordering ` +
      "is a lexical hint, NOT a judgement. Read the statements and decide on meaning; the right " +
      "answer is often not first, and may share no vocabulary at all):",
  );
  lines.push("");
  for (const candidate of proposal.candidates) {
    const terms = candidate.shared_terms.length > 0 ? candidate.shared_terms.join(", ") : "none";
    lines.push(`- ${candidate.id}  ${candidate.title}`);
    lines.push(`    ${candidate.summary}`);
    lines.push(`    (shared terms: ${terms})`);
  }
  lines.push(...formatPending(proposal));
  return lines.join("\n");
}

export function formatCheck(result: TraceCheckResult): string {
  const headline = result.ok
    ? "GATE PASSED — every gap is linked, exempted, or deferred."
    : `GATE FAILED — ${result.pending} gap(s) still undiscussed.`;
  return `${headline}\n\n${result.report}`;
}

export function formatWriteResult(
  label: string,
  result: { ok: boolean; stdout: string; stderr: string },
): string {
  const detail = (result.stdout || result.stderr).trim();
  return result.ok ? `${label} written: ${detail}` : `${label} FAILED: ${detail}`;
}
