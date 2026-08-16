# Design: `/factory-init` — Deterministic Project Bootstrap

Date: 2026-08-13
Status: Approved for implementation
Builds on:
- `2026-08-06-factory-init-design.md` — project onboarding (`.factory/factory.yaml`,
  the Registry, the `init` skill). This is a *different, complementary* deliverable and
  the name collision is resolved below in §2.
- `pi-ext/factory-watch/src/index.ts` and `src/factory/orchestrator/pi_backend.py` —
  the existing extension and subagent launcher this builds on.

## 1. Problem

Every new Pi session re-discovers, by re-reading the tree and re-asking an LLM:

- which project it is in;
- how the repo is structured;
- the canonical build/test/lint/sim/validation commands;
- where specs and plans live;
- which factory capabilities exist;
- how and when to run a subagent.

The fix required by this spec: an idempotent `/factory-init` command that performs
bounded discovery **once**, persists a compact project bootstrap, and makes the same
approved knowledge deterministically available to every later parent and subagent
session — **without rescanning or reinterpreting the repo on every session**.

## 2. Conflict with the existing factory-init design

`docs/superpowers/specs/2026-08-06-factory-init-design.md` is *project onboarding*: it
writes `.factory/factory.yaml`, introduces the extension `Registry`, a `factory init`
CLI and a vendored `init` skill, and (§13) explicitly lists "Registering `/doctor` or
`/init` as commands" as a non-goal.

This spec is *project bootstrap for every session*: it writes
`<root>/AGENTS.md` (a managed block) and `<root>/.pi/factory/project-profile.json`,
registers a `/factory-init` extension **command**, and adds tool + subagent knowledge
to the extension.

**Resolution (smallest compatible change): the two are cleanly separable and do not
touch the same files.**
- The existing design owns: `.factory/factory.yaml`, `src/factory/registry.py`,
  `src/factory/init/*`, `.pi/skills/init/SKILL.md`.
- This design owns: root `AGENTS.md` managed block, `.pi/factory/project-profile.json`,
  `/factory-init` + `/factory-doctor` extension commands, `subagent` tool metadata,
  subagent propagation in `pi_backend.py`.

No file is owned by both. The only lexical collision is the word "init": the existing
surface is `factory init <verb>` (CLI) and `/skill:init`; this surface is the
`/factory-init` **command**. Because the names are distinct invocations (`factory init`
CLI vs `/factory-init` slash-command) they can coexist. If a future change decides
otherwise, the command can be renamed to `/factory-init`'s documented alias with a
one-line registration change in `pi-ext/factory-watch/src/factory-init-command.ts`.

This spec does **not** resurrect the `harnesses.*.scorers` seam or any content the
onboarding design deliberately removed; those migrations are the other design's scope
and are left untouched.

## 3. Architecture

```
pi-ext/factory-watch/src/
  factory-init.ts          PURE, Pi-free core
      resolveProjectRoot()         git -> cwd fallback
      collectEvidence(root)        deterministic inspection, every fact evidenced
      buildProfile(root, evidence) schema-versioned project-profile.json
      buildManagedBlock(profile)   compact AGENTS.md block (500-900 tokens)
      replaceManagedBlock()        byte-for-byte outer preservation
      atomicWrite()                temp + rename
      runFactoryInit() / runFactoryCheck()
  factory-init-command.ts  /factory-init, /factory-doctor, reload-after-change
  subagent-tool.ts         subagent tool + buildSubagentInvocation + recursion guard
  factory-path.ts          shared FACTORY_ROOT / agentExtensionPath (breaks the cycle)

src/factory/orchestrator/pi_backend.py   subagent recursion depth + nc-flag refusal
```

## 4. Decisions

1. **Discovery is deterministic code, not an LLM.** Commands and invariants are derived
   from evidence paths (`pyproject.toml`, `package.json`, `.factory/factory.yaml`,
   README first paragraph). No model output is ever accepted without evidence. §4 of the
   onboarding design draws the same line for its CLI.
2. **Evidence is primary; the block is a projection.** `project-profile.json` holds
   hashes of every evidence source file; the managed block is regenerated from it. Drift
   is detected by recomputing hashes, never by asking a model.
3. **AGENTS.md is the session-injection vehicle, once.** Pi loads `<root>/AGENTS.md`
   natively, so the capsule reaches every parent and (via `pi_backend.py`/`subagent` tool
   cwd=project-root, no `-nc`) every subagent. `before_agent_start` is **not** used to
   re-inject the capsule — that would duplicate it. It is reserved for small dynamic
   state and no such injection is added here.
4. **Idempotent and atomic.** Writes are a no-op unless bytes change; a run that changes
   nothing does not call `ctx.reload()`.
5. **Tool knowledge lives with the tool.** `promptSnippet` + `promptGuidelines` on the
   registered tools (trace_*, system_context, subagent) teach the parent that a tool
   exists, independently of `AGENTS.md`.
6. **Subagent recursion is bounded.** `pi_backend.py` refuses to spawn beyond
   `PI_FACTORY_SUBAGENT_DEPTH` limit; the `subagent` tool returns rather than constructing
   a deeper invocation. The child contract (project root cwd, no `--no-context-files`,
   concise `@file` packet, `--mode json`) is enforced in `_build_command`.
7. **`generated_at` is metadata, not content.** The idempotency comparison excludes it so
   a no-op run does not rewrite the profile.
8. **`_source_files`/hashes never include** `.venv`, `node_modules`, build/cache dirs, or
   `.env*`; they are allowlisted, not dumped.

## 5. The managed `AGENTS.md` block

Markers (stable, schema-versioned):

```html
<!-- pi-agent-factory:bootstrap:start schema=1 -->
<!-- pi-agent-factory:bootstrap:end -->
```

Contents limited to: one-paragraph purpose; key components and boundaries; canonical
spec/plan locations; exact common commands; non-negotiable rules; pointers to deeper
knowledge. Targeting ~500–900 tokens. Everything outside the markers is preserved
byte-for-byte. Malformed/duplicate markers fail safely (throw before any write) rather
than guess.

Representative block for this repository is reproduced in `docs/project-bootstrap.md` §9.

## 6. Command surface

```
/factory-init            initialise if missing; else validate + report
/factory-init --refresh  rediscover and update only factory-managed content
/factory-init --check    read-only validation + drift check
/factory-doctor          diagnostics: root, profile, block, tools, subagent metadata
```

`/factory-init` shows the proposed capsule / a concise diff before replacing an existing
managed block when interactive (`ctx.hasUI`), with a well-defined noninteractive fallback.
After an actual change it calls `await ctx.reload(); return;` per Pi's contract; on a
no-op run it does not reload.

## 7. Testing

Covered in `pi-ext/factory-watch/test/factory-init.test.ts` (16 tests) and
`tests/unit/orchestrator/test_pi_parse.py` (3 new tests), mapping to the full required
list: empty-repo init; user-owned AGENTS.md; byte-for-byte preservation; idempotency;
explicit refresh after evidence change; read-only check; malformed/duplicate markers;
atomic-write failure; git-root resolution from a nested dir; non-git fallback; exclusion
of secrets/generated/dependency dirs; reload-only-on-change; subagent start in project
root with context files; subagent tool prompt metadata; determinism across reconstruction.

## 8. Non-goals

- No database/vector store/embedding (constraint).
- No full-spec-tree loading into every prompt (constraint).
- No continuous learning from unchecked model output (constraint).
- No silent overwrite of human-authored `AGENTS.md` content (constraint).
- No `.factory/factory.yaml` / Registry changes — that belongs to the onboarding design,
  which this spec leaves untouched (§2).
