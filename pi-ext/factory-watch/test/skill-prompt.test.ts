import { describe, expect, test } from "vitest";
import { buildPlanSeedPrompt, buildSkillBlock } from "../src/skill-prompt.js";

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
