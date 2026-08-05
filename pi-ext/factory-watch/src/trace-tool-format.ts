import type { TraceCheckResult, TraceProposal } from "./trace-cli.js";

export function formatNoGaps(): string {
  return "No pending gaps. Every gap is linked, exempted, or deferred. Run trace_check to confirm.";
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
    lines.push(
      "Candidates: no candidates exist for this gap kind. Defer it, or exempt it if it is a " +
        "task or plan that legitimately has nothing to link to.",
    );
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
