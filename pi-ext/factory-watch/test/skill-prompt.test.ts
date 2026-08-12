import { describe, expect, test } from "vitest";
import {
  buildGrillSeedPrompt,
  buildPlanSeedPrompt,
  buildSkillBlock,
  buildTraceFixSeedPrompt,
} from "../src/skill-prompt.js";

describe("buildSkillBlock", () => {
  test("wraps skill content in the same <skill> shape Pi's native /skill:name expansion produces", () => {
    const block = buildSkillBlock({
      name: "brainstorming",
      location: "/repo/.pi/skills/brainstorming/SKILL.md",
      body: "# Brainstorming\n\nSome content.",
    });
    expect(block).toBe(
      '<skill name="brainstorming" location="/repo/.pi/skills/brainstorming/SKILL.md">\n' +
        "# Brainstorming\n\nSome content.\n</skill>",
    );
  });
});

describe("buildPlanSeedPrompt", () => {
  test("includes every skill block, the plan_to_tasks override instructions, and the topic", () => {
    const prompt = buildPlanSeedPrompt("add battery-aware RTB", ["<skill1/>", "<skill2/>"]);
    expect(prompt).toContain("<skill1/>");
    expect(prompt).toContain("<skill2/>");
    expect(prompt).toContain("factory.orchestrator.plan_to_tasks");
    expect(prompt).toContain("Topic: add battery-aware RTB");
  });
});

describe("buildTraceFixSeedPrompt", () => {
  const prompt = buildTraceFixSeedPrompt(['<skill name="trace-fix">body</skill>'], "45 pending");

  test("includes the skill block and the current gap report", () => {
    expect(prompt).toContain('<skill name="trace-fix">');
    expect(prompt).toContain("45 pending");
  });

  test("directs the agent at the tools, not at raw commands", () => {
    expect(prompt).toContain("trace_next");
    expect(prompt).toContain("trace_check");
  });

  test("tells the agent to judge by meaning rather than by rank", () => {
    expect(prompt.toLowerCase()).toContain("ordering is a lexical hint");
  });

  test("forbids editing frontmatter directly", () => {
    expect(prompt.toLowerCase()).toContain("never edit");
  });
});

describe("buildGrillSeedPrompt", () => {
  const skillBlocks = ['<skill name="grill-understanding">body</skill>'];
  const taskText = "Task: add battery-aware RTB\nDoD: ...\nsatisfies: rtb-1\nTouched: src/a.ts";
  const freshExplainers = "battery.fetch: explains rtb-1 fetch path";
  const resultPath = "/repo/grill-result.json";

  test("renders the supplied skill blocks verbatim", () => {
    const prompt = buildGrillSeedPrompt(
      taskText,
      ['<skill name="grill-understanding">body</skill>'],
      freshExplainers,
      resultPath,
    );
    expect(prompt).toContain('<skill name="grill-understanding">body</skill>');
  });

  test("contains the task text and directs the session to write grillResultPath as JSON", () => {
    const prompt = buildGrillSeedPrompt(taskText, skillBlocks, freshExplainers, resultPath);
    expect(prompt).toContain(taskText);
    expect(prompt).toContain("/repo/grill-result.json");
    expect(prompt).toContain("decision");
    expect(prompt).toContain("updated_at");
  });

  test("works with an empty skillBlocks array and still contains the core instructions", () => {
    const prompt = buildGrillSeedPrompt(taskText, [], freshExplainers, resultPath);
    expect(prompt).toContain("ONE question at a time");
    expect(prompt).toContain("state their understanding in their own words");
    expect(prompt).toContain("grill-understanding");
  });

  test("contains a header/label for the explainer summary", () => {
    const prompt = buildGrillSeedPrompt(taskText, skillBlocks, freshExplainers, resultPath);
    expect(prompt).toContain("Visual explainers to consider");
    expect(prompt).toContain(freshExplainers);
  });
});

describe("buildTraceFixSeedPrompt field of view", () => {
  const prompt = buildTraceFixSeedPrompt(['<skill name="trace-fix">body</skill>'], "45 pending");

  test("no longer claims the tools own enumeration", () => {
    expect(prompt).not.toContain("own enumeration");
  });

  test("tells the agent it may choose a gap", () => {
    expect(prompt).toContain("node_id");
  });

  test("still points at the gate and still forbids batching", () => {
    expect(prompt).toContain("trace_check");
    expect(prompt.toLowerCase()).toContain("one gap, one proposal, one confirmation");
  });
});
