import { describe, expect, test } from "vitest";
import { buildPlanReviewCommand, parsePlanReviewResponse, renderPlanReview } from "../src/plan-review-command.js";

describe("plan-review command", () => {
  test("builds an argv-only review command", () => {
    expect(buildPlanReviewCommand("C:/repo", "run-7")).toEqual({
      bin: "uv",
      args: ["run", "coherence", "plan", "review", "--project-root", "C:/repo", "--run-id", "run-7", "--json"],
    });
  });
  test("rejects malformed backend output and renders escalation details", () => {
    expect(parsePlanReviewResponse("{}" )).toEqual({ ok: false, error: "invalid planning review response" });
    expect(renderPlanReview({ ok: false, blocked: true, stage: "spec_alignment", iteration: 1,
      finding_ids: ["F-1"], prompts: ["Choose a scope"], next_loop_input: "answer required",
      legal_actions: ["answer", "cancel"], hashes: { spec: "abc" } })).toContain("F-1");
  });
});
