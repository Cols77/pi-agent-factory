export interface SkillContent {
  name: string;
  location: string;
  body: string;
}

export function buildSkillBlock(skill: SkillContent): string {
  return `<skill name="${skill.name}" location="${skill.location}">\n${skill.body}\n</skill>`;
}

export function buildPlanSeedPrompt(topic: string, skillBlocks: string[]): string {
  const instructions = [
    "You're in plan-time for this repo's dev factory. Use the loaded `brainstorming` skill on the topic below.",
    "When brainstorming reaches its handoff to `writing-plans`, proceed into `writing-plans` as usual; save the plan under `docs/superpowers/plans/`.",
    'Override writing-plans\' own "Execution Handoff" step: once the plan is saved, do not offer subagent-driven or inline execution. Instead run `uv run python -m factory.orchestrator.plan_to_tasks <plan-file>` and report the task ids it created. Actual execution happens later via /factory-run.',
  ].join("\n\n");
  return [...skillBlocks, instructions, `Topic: ${topic}`].join("\n\n");
}
