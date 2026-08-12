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

export function buildTraceFixSeedPrompt(skillBlocks: string[], gapReport: string): string {
  const instructions = [
    "You are closing traceability gaps for this repo. Use the loaded `trace-fix` skill.",
    "Work through the gaps with the trace tools: `trace_next` for a gap, its candidates and the full list of pending gaps, `trace_link` / `trace_exempt` / `trace_defer` to record a decision, and `trace_check` for the gate. The default focus is a default, not a queue — pass `node_id` to trace_next to work any pending gap. The tools own validation and every write; you decide which gap to take and what it means.",
    "You own exactly one thing: judging which candidate genuinely matches, and saying why. `trace_next` returns EVERY candidate with its full requirement statement, ordered by shared-term overlap — that ordering is a lexical hint, not a judgement. The right answer is often not first, and may share no vocabulary with the task at all. Read the statements.",
    "Propose one candidate to the human with your reasoning and wait for their answer before calling any write tool. One gap, one proposal, one confirmation — never batch approvals.",
    "Never edit `satisfies:`, `trace_exempt:` or `trace_deferred:` in a file directly. `trace_link` verifies the target exists; a hand-edited link can create a dangling reference it would have refused.",
    "Never claim a gap was handled without having called the tool. `trace_check` re-reads the files and will contradict you.",
    "Finish by calling `trace_check` and reporting its output verbatim.",
  ].join("\n\n");
  return [...skillBlocks, instructions, `Current gap report:\n${gapReport}`].join("\n\n");
}

export function buildGrillSeedPrompt(
  taskText: string,
  skillBlocks: string[],
  freshExplainerSummary: string,
  grillResultPath: string,
): string {
  const instructions = [
    "You are running the grill for this task BEFORE it is implemented. Use the loaded `grill-understanding` skill. Your job is to verify the user genuinely understands the task, its definition of done, and the code they will later review — not to rubber-stamp it. This grill is strongly-advised but never a hard block.",
    "Ask the user ONE question at a time. After every answer, verify it against the actual code and the task before accepting it: read the relevant files, check the DoD, the `satisfies:` trace targets, and the touched code paths, and confirm the claim actually holds before moving on. Never take the user's word over the code.",
    "When the user gets a concept wrong, if the fresh explainer summary below lists a matching fresh visual explainer, have the user READ that explainer's .md and VIEW its .svg. Otherwise generate a NEW visual explainer via the `visual-explainer`/`diagram-design` skills across the scope below.",
    "Require the user to state their understanding in their own words before you consider a concept resolved and move on to the next question. Do not accept a paraphrase of your own wording.",
    `When the grill is done, the session MUST write the result file at ${grillResultPath} as JSON in exactly this shape: {"decision":"agreed"|"not-agreed"|"skipped","summary":<user summary or null>,"explainers":<number reused-or-generated>,"updated_at":<ISO-timestamp>}. Count in "explainers" every fresh explainer reused or generated during this session.`,
  ].join("\n\n");

  const content = [
    `Task to grill about (scope: body, DoD, satisfies: trace targets, touched code paths):\n${taskText}`,
    `Visual explainers to consider (from docs/visual-explain/; verify each one's dependency fingerprint is current before reusing it, else generate a new one):\n${freshExplainerSummary}`,
  ].join("\n\n");

  return [...skillBlocks, instructions, content].join("\n\n");
}
