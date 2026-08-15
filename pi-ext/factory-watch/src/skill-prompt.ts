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

export function buildVisualExplainSeedPrompt(focus: string, skillBlocks: string[]): string {
  const instructions = [
    "You are producing a visual explanation of parts of this repo's system, using the loaded `diagram-design` skill.",
    "Deliverables — always BOTH: (1) a standalone `.svg` diagram of the system parts, and (2) a markdown `.md` note that explains each part and references the SVG with a relative image link.",
    "Workflow:",
    "  1. Read the loaded skill content. The style guide, per-type references and the export procedure live next to SKILL.md under `references/`; load the ones you need — `style-guide.md` always, the type reference for the diagram type you pick, and `export.md` for the SVG step.",
    "  2. Identify the parts of the system to explain. If a focus was given, explain those parts; otherwise inspect the repo (README, `src/`, `requirements/`, `docs/`) and choose the most instructive parts to explain.",
    "  3. Pick one diagram type from the skill's 27 types that best fits the parts. Respect the skill's density rules: target density 4/10, ≤9 nodes, ≤12 arrows, ≤2 coral accents, orthogonal rounded connectors (r=8), masked arrow labels with a 6–10px gap. Run the §9 pre-output checklist before producing anything.",
    "  4. Build the diagram as a self-contained HTML file per the skill (inline SVG + embedded CSS; Google Fonts is the only external resource). Skip the first-run style-guide gate: proceed with the default skin unless the focus text explicitly provides custom style tokens.",
    "  5. Export the SVG: follow `references/export.md` — extract the first `<svg>` block from the HTML, make it standalone (add `xmlns`, keep the `viewBox`, merge the Google Fonts `@import` into `<defs>`, prepend the `<?xml?>` prolog). SVG only; do NOT produce a PNG.",
    "  6. Write the markdown note: one section per part (what it is, its role, and how it connects to the others), then reference the SVG with a relative image link.",
    "  7. Report the two saved file paths when done.",
    "Output: save both files under `docs/visual-explain/` (create the directory if needed) with a slug derived from the topic, e.g. `docs/visual-explain/<topic-slug>.svg` and `docs/visual-explain/<topic-slug>.md`.",
  ].join("\n\n");
  return [...skillBlocks, instructions, `Focus: ${focus}`].join("\n\n");
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
  packetSlice: string | null = null,
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

  if (packetSlice !== null && packetSlice.trim() !== "") {
    return [...skillBlocks, instructions, content, packetSlice].join("\n\n");
  }

  return [...skillBlocks, instructions, content].join("\n\n");
}
