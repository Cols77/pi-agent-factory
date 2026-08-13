Implement a deterministic project-bootstrap system in the current `pi-agent-factory` repository.

This is an implementation task, not only a design or planning task. First inspect the existing specifications, plans, extension architecture, subagent implementation, tests, and package conventions. Reuse the current abstractions and installed Pi API version; do not perform an unrelated framework migration.

## Problem

At present, new Pi sessions repeatedly rediscover:

- what project they are in;
    
- how the repository is structured;
    
- the canonical build, test, lint, simulation, and validation commands;
    
- where specifications and implementation plans live;
    
- which Pi Agent Factory capabilities are available;
    
- how and when to run a subagent.
    

Implement an idempotent `/factory-init` command that performs bounded discovery once, persists a compact project bootstrap, and ensures that the same approved knowledge is deterministically available in every later parent-agent and subagent session.

Do not rescan or ask an LLM to reinterpret the repository on every session.

## Required architecture

### 1. Factory-wide tool awareness

Inspect all custom tools registered by the factory, particularly the subagent tool.

Give each important tool:

- a concise `promptSnippet`;
    
- explicit `promptGuidelines` that name the tool;
    
- a clear tool description and parameter descriptions.
    

For the subagent tool, the prompt metadata must explain:

- what it does;
    
- when delegation is appropriate;
    
- that independent work may run in parallel when supported;
    
- how results return to the parent;
    
- when delegation is unnecessary;
    
- how recursive spawning is prevented.
    

Do not rely on `AGENTS.md` alone to teach the parent agent that a registered tool exists. Tool-specific knowledge belongs with the tool registration.

### 2. Stable project bootstrap

`/factory-init` must create and maintain:

- `<project-root>/AGENTS.md`
    
- `<project-root>/.pi/factory/project-profile.json`
    

Use `CONFIG_DIR_NAME` from the installed Pi API instead of hardcoding `.pi` inside extension code where applicable.

`project-profile.json` must be schema-versioned and machine-readable. It should contain, at minimum:

- detected project root;
    
- project name and concise purpose;
    
- important packages/components;
    
- important source directories;
    
- canonical specifications, plans, requirements, ADRs, and validation artefacts;
    
- exact setup, build, test, lint, typecheck, simulation, and validation commands that can be supported by repository evidence;
    
- important architectural invariants;
    
- evidence paths supporting each detected fact;
    
- generation timestamp;
    
- hashes or other drift indicators for relevant source files.
    

Do not store secrets, environment-variable values, generated build output, dependency contents, or arbitrary repository dumps.

### 3. Managed `AGENTS.md` section

Maintain a compact generated block inside the root `AGENTS.md`, using stable markers such as:

`<!-- pi-agent-factory:bootstrap:start schema=1 -->`

and

`<!-- pi-agent-factory:bootstrap:end -->`

The block should contain only the minimum context worth injecting into every request:

- one-paragraph project purpose;
    
- key components and boundaries;
    
- canonical specification/plan locations;
    
- exact common commands;
    
- non-negotiable engineering and validation rules;
    
- pointers to deeper project knowledge and factory commands.
    

Target approximately 500–900 tokens. Do not place volatile implementation progress, current tasks, recent conversation history, experiment results, or a repository inventory in this block.

If `AGENTS.md` already exists:

- preserve all content outside the managed markers byte-for-byte;
    
- never overwrite the whole file;
    
- never create duplicate managed blocks;
    
- fail safely if markers are malformed or ambiguous.
    

If no `AGENTS.md` exists, create it with an appropriate heading and the managed block.

### 4. Command behaviour

Register a Pi extension command named `/factory-init`.

Support:

- `/factory-init` — initialise if missing; otherwise validate and report status;
    
- `/factory-init --refresh` — rediscover and update only factory-managed content;
    
- `/factory-init --check` — perform a read-only validation and drift check.
    

The command must:

1. Resolve the project root using Git when available, with a safe fallback to `ctx.cwd`.
    
2. Verify project trust before honoring executable project-local configuration.
    
3. Collect repository evidence using deterministic inspection first.
    
4. If semantic synthesis is needed, use one bounded read-only bootstrap agent and require structured output validated against a schema.
    
5. Never accept unsupported commands or architectural claims without evidence paths.
    
6. Show the proposed project capsule or a concise diff before replacing an existing managed block when interactive UI is available.
    
7. Be idempotent: running it twice without repository changes must produce no file changes.
    
8. Write files atomically.
    
9. After a successful change, call `await ctx.reload(); return;` so Pi reloads context files safely.
    
10. Provide useful noninteractive behaviour without depending on terminal dialogs.
    

Do not automatically rewrite the bootstrap on ordinary `session_start`.

### 5. Session injection

Use Pi’s native `AGENTS.md` loading as the primary mechanism for stable project knowledge.

Do not inject the same project capsule a second time through `before_agent_start`.

If `before_agent_start` is already used by the factory:

- inspect `event.systemPromptOptions.contextFiles`;
    
- avoid duplicating content already loaded from `AGENTS.md`;
    
- reserve dynamic injection for small, explicitly selected state such as an active requirement, active `/goal`, or current experiment;
    
- keep injected content deterministic and stable for prompt-cache friendliness;
    
- never perform an LLM call merely to construct the system prompt.
    

Do not use a once-per-session custom message for invariants that must survive compaction. Those invariants belong in the system prompt or `AGENTS.md`.

### 6. Subagent propagation

Inspect the existing subagent launcher and ensure that every child:

- starts with the resolved project root as its working directory;
    
- does not use `--no-context-files` or `-nc`;
    
- therefore receives the same root `AGENTS.md`;
    
- receives a concise task packet rather than the full parent transcript;
    
- gets only the tools appropriate to its role;
    
- cannot recursively spawn subagents unless recursion is explicitly designed and bounded.
    

If subagents are separate noninteractive Pi processes and require project-local extensions, propagate trust only when:

- the parent reports `ctx.isProjectTrusted() === true`;
    
- the child working directory has been validated as the same trusted project;
    
- the trust propagation is explicit in code.
    

Do not blindly add `--approve` to arbitrary child processes.

### 7. Diagnostics

Implement either `/factory-doctor` or equivalent `/factory-init --check` output that verifies:

- project root resolution;
    
- profile schema and freshness;
    
- validity and uniqueness of the `AGENTS.md` managed block;
    
- whether the expected context file is loaded;
    
- presence and active status of essential factory tools;
    
- presence of `promptSnippet` and `promptGuidelines` for the subagent tool;
    
- subagent working-directory and context-file propagation configuration;
    
- drift between evidence files, `project-profile.json`, and the generated block.
    

The output must distinguish errors, warnings, and informational findings and give a concrete remediation for each error.

### 8. Tests

Add automated tests covering at least:

1. Initialisation of an empty temporary repository.
    
2. Initialisation when a user-owned `AGENTS.md` already exists.
    
3. Preservation of content outside managed markers.
    
4. Idempotent second execution.
    
5. Explicit refresh after evidence changes.
    
6. Read-only `--check`.
    
7. Malformed or duplicate marker handling.
    
8. Atomic-write failure behaviour.
    
9. Git-root resolution from a nested directory.
    
10. Non-Git fallback.
    
11. Exclusion of secrets and generated/dependency directories.
    
12. Reload being invoked only after actual changes.
    
13. Subagent startup in the project root with context-file loading enabled.
    
14. The registered subagent tool exposing its prompt snippet and guidelines.
    
15. The bootstrap remaining available after session compaction or context reconstruction.
    

Use the repository’s existing test framework and conventions.

### 9. Documentation

Document:

- why stable knowledge is stored in `AGENTS.md`;
    
- the difference between project bootstrap, active task state, and durable project memory;
    
- `/factory-init`, `--refresh`, and `--check`;
    
- how users edit or override generated knowledge;
    
- how subagents inherit project context;
    
- prompt-size and staleness considerations;
    
- migration or rollback behaviour.
    

Include a representative generated `AGENTS.md` block for this repository.

## Constraints

- Preserve existing user changes and unrelated work.
    
- Do not introduce a database, vector store, or embedding dependency for this bootstrap layer.
    
- Do not load the full specification tree into every prompt.
    
- Do not continuously learn unchecked facts from model output.
    
- Do not silently overwrite human-authored project instructions.
    
- Keep the static prompt prefix small and stable.
    
- Use the installed Pi package’s actual APIs and types rather than assuming the latest documentation matches the repository version.
    
- If an existing design conflicts with these requirements, explain the conflict with file references before choosing the smallest compatible change.
    

## Completion report

After implementation, report:

- the resulting architecture;
    
- files changed;
    
- exact commands added;
    
- an example of the generated bootstrap;
    
- tests executed and their results;
    
- any remaining limitations;
    
- one short demonstration proving that a fresh parent session and a fresh subagent both receive the known project facts without rediscovering them.