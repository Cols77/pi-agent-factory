import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { buildSessionReviewSuggestTools } from "../src/session-review-suggest.js";

function makeRepo(tmp: string) {
  const cwd = join(tmp, "proj");
  const runs = join(cwd, "sessions", ".factory-runs", "by-session");
  mkdirSync(runs, { recursive: true });
  return { cwd, runs };
}

describe("factory_run_suggest", () => {
  test("returns a proposal from the latest non-abandoned artifact", async () => {
    const { cwd, runs } = makeRepo("/tmp/review-suggest-test-1");
    const dirOld = join(runs, "R-OLD");
    const dirNew = join(runs, "R-NEW");
    mkdirSync(dirOld, { recursive: true });
    mkdirSync(dirNew, { recursive: true });
    writeFileSync(
      join(dirOld, "session-review.json"),
      JSON.stringify({
        run_id: "R-OLD", task_id: "T-1", final_outcome: "completed",
        suggestions: [{ target: "prompt", summary: "old", proposed: "old change", evidence: "e" }],
      }),
      "utf-8",
    );
    writeFileSync(
      join(dirNew, "session-review.json"),
      JSON.stringify({
        run_id: "R-NEW", task_id: "T-2", final_outcome: "completed",
        suggestions: [
          { target: "gate", summary: "gate interpreter", proposed: "use uv run python", evidence: "collection fail" },
          { target: "skill", summary: "add context", proposed: "extend session-report skill", evidence: "retry" },
        ],
      }),
      "utf-8",
    );
    // Abandoned run is skipped even if its artifact is newer on disk later.
    const dirAbandoned = join(runs, "R-ABANDONED");
    mkdirSync(dirAbandoned, { recursive: true });
    writeFileSync(join(dirAbandoned, "abandoned.json"), JSON.stringify({ reason: "stale" }), "utf-8");
    writeFileSync(
      join(dirAbandoned, "session-review.json"),
      JSON.stringify({ run_id: "R-ABANDONED", suggestions: [{ target: "config", summary: "x", proposed: "y" }] }),
      "utf-8",
    );

    const tool = buildSessionReviewSuggestTools()[0]!;
    const out: any = await tool.execute("c", { run_id: "R-NEW" }, undefined, undefined, { cwd });
    const details = out.details;
    expect(details.status).toBe("ok");
    expect(details.run_id).toBe("R-NEW");
    expect(details.counts_by_target).toEqual({ gate: 1, skill: 1 });
    expect(details.suggestions[0].target_file).toBe(".factory/factory.yaml");
    expect(details.suggestions[1].target_file).toBe(".pi/skills/<name>/SKILL.md");
    expect(details.proposal).toContain("use uv run python");
  });

  test("defaults to the latest run and lists available runs", async () => {
    const { cwd, runs } = makeRepo("/tmp/review-suggest-test-2");
    const dirA = join(runs, "R-A");
    const dirB = join(runs, "R-B");
    mkdirSync(dirA, { recursive: true });
    mkdirSync(dirB, { recursive: true });
    writeFileSync(join(dirA, "session-review.json"), JSON.stringify({ run_id: "R-A", suggestions: [] }), "utf-8");
    writeFileSync(join(dirB, "session-review.json"), JSON.stringify({ run_id: "R-B", suggestions: [] }), "utf-8");

    const tool = buildSessionReviewSuggestTools()[0]!;
    const out: any = await tool.execute("c", {}, undefined, undefined, { cwd });
    expect(out.details.status).toBe("ok");
    // R-B is newest by mtime (written after R-A).
    expect(out.details.run_id).toBe("R-B");
    expect(out.details.available_runs.map((r: any) => r.run_id)).toEqual(["R-A", "R-B"]);
  });

  test("returns none when no artifacts exist", async () => {
    const { cwd } = makeRepo("/tmp/review-suggest-test-3");
    const tool = buildSessionReviewSuggestTools()[0]!;
    const out: any = await tool.execute("c", {}, undefined, undefined, { cwd });
    expect(out.details.status).toBe("none");
  });

  test("returns not-found for a missing explicit run", async () => {
    const { cwd } = makeRepo("/tmp/review-suggest-test-4");
    const tool = buildSessionReviewSuggestTools()[0]!;
    const out: any = await tool.execute("c", { run_id: "NOPE" }, undefined, undefined, { cwd });
    expect(out.details.status).toBe("not-found");
  });
});
