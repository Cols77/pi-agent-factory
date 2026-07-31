---
name: session-report
description: Analyze a completed factory task's pipeline run, record genuinely reusable issues in the knowledge base, and suggest skill/prompt improvements
---

# Session Report

Analyze what happened during this task's pipeline run using the event
history provided in your prompt: which stages ran, how many attempts each
took, and the final outcome.

## Knowledge base entries

Not every run produces something worth recording. Only write a new
`kb/kb-NNNN-<slug>.md` entry when you've identified a genuinely reusable
issue -- a bug class, a gotcha, a non-obvious fix -- that would help a
future task avoid the same problem. Check the existing entry list in your
prompt (and `kb/` itself if you want more detail on a specific one) before
writing; do not create a near-duplicate of an issue already recorded.

Follow the existing KB entry format: YAML frontmatter with `id`, `title`,
`status`, `severity`, `tags`, and `scope.files`/`scope.error_signatures`,
followed by Symptom / Root cause / Rule-or-fix sections in the body.

## Skill and prompt suggestions

Append a short "Suggestions" section to this session's summary noting any
skill or prompt improvements that would have made this specific run more
efficient -- for example, a skill that was missing context it needed, or a
role prompt that led to a wasted retry. These are suggestions for a human
to read and decide on later; do not edit `.pi/skills/**` or any role prompt
yourself.
