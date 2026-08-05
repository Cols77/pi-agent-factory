import { describe, expect, test } from "vitest";
import {
  formatCheck,
  formatNoGaps,
  formatProposal,
  formatWriteResult,
} from "../src/trace-tool-format.js";
import type { TraceProposal } from "../src/trace-cli.js";

function proposal(candidateCount: number): TraceProposal {
  return {
    gap: {
      node_id: "T-047",
      kind: "task_no_sr",
      detail: "task declares no satisfies",
      disposition: "pending",
    },
    node_title: "Bug Capture",
    node_excerpt: "Create src/sim/bug_capture.py",
    pending_total: 45,
    candidates: Array.from({ length: candidateCount }, (_, i) => ({
      id: `SR-${String(i + 1).padStart(3, "0")}`,
      title: `Requirement ${i + 1}`,
      summary: `the system shall do thing number ${i + 1}`,
      shared_terms: i === 0 ? ["capture"] : [],
      score: i === 0 ? 1 : 0,
    })),
  };
}

describe("formatProposal", () => {
  test("names the gap, the node and how many remain", () => {
    const text = formatProposal(proposal(2));
    expect(text).toContain("T-047");
    expect(text).toContain("task_no_sr");
    expect(text).toContain("Bug Capture");
    expect(text).toContain("45");
  });

  test("includes every candidate's statement, not just its id", () => {
    // Semantic matching is impossible without the statements. Spec section 6.1.
    const text = formatProposal(proposal(3));
    expect(text).toContain("the system shall do thing number 3");
  });

  test("lists all candidates even when there are many", () => {
    const text = formatProposal(proposal(30));
    expect(text).toContain("SR-030");
  });

  test("states that ranking is lexical and not authoritative", () => {
    const text = formatProposal(proposal(2));
    expect(text.toLowerCase()).toContain("shared-term");
  });

  test("handles a gap with no candidates", () => {
    expect(formatProposal(proposal(0))).toContain("no candidates");
  });
});

describe("formatCheck", () => {
  test("reports a pass", () => {
    const text = formatCheck({ ok: true, pending: 0, deferred: 2, exempt: 1, report: "raw" });
    expect(text).toContain("PASSED");
    expect(text).toContain("raw");
  });

  test("reports a failure with the pending count", () => {
    const text = formatCheck({ ok: false, pending: 7, deferred: 0, exempt: 0, report: "raw" });
    expect(text).toContain("FAILED");
    expect(text).toContain("7");
  });
});

describe("formatWriteResult", () => {
  test("reports success with the path written", () => {
    expect(formatWriteResult("link", { ok: true, stdout: "tasks/T-047.md", stderr: "" })).toContain(
      "tasks/T-047.md",
    );
  });

  test("surfaces a refusal verbatim so the model cannot mistake it for success", () => {
    const text = formatWriteResult("link", {
      ok: false,
      stdout: "error: no such requirement: SR-999",
      stderr: "",
    });
    expect(text).toContain("FAILED");
    expect(text).toContain("no such requirement: SR-999");
  });
});

describe("formatNoGaps", () => {
  test("says there is nothing pending", () => {
    expect(formatNoGaps()).toContain("No pending gaps");
  });
});
