# Plan: Content-Bearing Context Packet

**Date:** 2026-08-14
**Status:** Draft for review
**Source:** `docs/superpowers/specs/2026-08-14-context-packet-design.md`
**Required sub-skill:** superpowers:subagent-driven-development (task-by-task,
checkboxes below). Py: `pytest.mark.unit`; TS: vitest; ruff 100 / pyright standard.

## Grounding (verified against current `design/curation-workflow`)

- The manifest is not persisted; it is passed in-memory from `run_context_gatherer`
  → `run_dev` (via `compose_prompt(AgentRole.DEV, task, manifest, kb_entries, ...)`)
  and `run_review` gets only `kb_entries` + `events` (no manifest).
- `compose_prompt` (`src/factory/orchestrator/prompts.py`) renders `source_files` as
  bare `- <path>` bullets under `## Context (from manifest)`.
- `parse_deliverables`/`modified_deliverables`/`created_deliverables`
  (`src/factory/orchestrator/deliverables.py`) already extract Modify/Create/Test paths.
- The grill seed (`pi-ext/factory-watch/src/skill-prompt.ts` `buildGrillSeedPrompt`,
  `index.ts` `openGrillWindow`) uses task text + explainer summary only.
- Transcript dir (shared by review-guide.json / validation-report.json / the grill
  result) is `sessions/.factory-transcripts/<session_id>`, known to both Python
  (`transcript_dir`) and the extension (`grillResultPath`).

## Global constraints

- Deterministic, stdlib-only content extraction for item 1 (tree-sitter swap is item
  2 of the roadmap — do not add it here).
- **No Python-side dependency on the extension** and vice-versa: the packet is a
  plain JSON artifact both read; no import across the boundary.
- Additive/backwards-compatible: `compose_prompt` without a `packet` still renders
  the old bullet list (resumed runs / tests); a run with no persisted packet still
  seeds the grill (task-text-only, current behavior).
- Caps are env-tunable (`FACTORY_PACKET_*`); do not build a parallel staleness engine.

---

### Task 1: Pure packet builder

**Files:** new `src/factory/orchestrator/context_packet.py`, tests in
`tests/unit/orchestrator/`.

- [ ] **Step 1 (failing tests):** `primary_paths(task, manifest)` returns the
  intersection of Modify/Create deliverables with `source_files`;
  `build_context_packet(...)` returns full content for primary files,
  signature summaries for reference files, and a `missing` list for unreadable
  files; `render_packet(...)` returns a closed markdown block. Cap fallback: an
  over-cap primary file renders as a signature, not truncated junk; a file over
  the total cap is excluded with a notice.
- [ ] **Step 2 (implement):** stdlib `ast`/`tokenize` signature extractor
  (`def`/`class` name + signature + line + module docstring one-liner); robust
  encoding (utf-8, errors="replace"); env-tunable caps.
- [ ] **Step 3:** `uv run python -m pytest -m unit` + ruff; commit.

### Task 2: Wire into the pipeline + persist

**Files:** `nodes.py`, `runner.py`, `prompts.py`, `tests/unit/orchestrator/`.

- [ ] **Step 1 (failing tests):** after a passing context-gather, the run persists
  `<transcript_dir>/context-packet.json`; the Dev compose prompt embeds primary
  content from the packet (not just paths); Review receives the packet; without a
  packet the Dev prompt falls back to the old bullet list.
- [ ] **Step 2 (implement):** add `packet` param to `compose_prompt` and thread it
  from `run_dev`/`run_review`; build + persist the packet once in `run_task` after
  the gatherer passes; `write_context_packet` + a `read_context_packet` helper.
- [ ] **Step 3:** unit suite + integration smoke + ruff; commit.

### Task 3: Grill seed consumes the packet (extension)

**Files:** `pi-ext/factory-watch/src/index.ts`, `src/skill-prompt.ts`,
`src/grill.ts` (or a new `context-packet.ts`), `test/handler.test.ts`.

- [ ] **Step 1 (failing tests):** a new `readContextPacket(cwd, sessionId)`
  reads `<transcript_dir>/context-packet.json`; `buildGrillSeedPrompt` accepts an
  optional packet slice argument; a handler test with a persisted packet asserts the
  seed contains primary-file content; without one, the seed degrades to
  task-text-only.
- [ ] **Step 2 (implement):** read + inject a bounded `render_packet` slice into the
  grill seed; keep the existing explicit-explainers path.
- [ ] **Step 3:** vitest + typecheck + full guard suite; commit.

### Task 4: Review handoff

- [ ] **Step 1:** reviewer sub-agent — verify (a) Dev prompt carries primary content;
  (b) Review receives the packet; (c) grill seed carries a bounded packet slice and
  degrades gracefully; (d) deterministic/stdlib (no tree-sitter in item 1); (e)
  additive, no collision with in-progress `/visual-explain` or registry work; (f) no
  parallel staleness engine.
- [ ] **Step 2:** fix findings; tick checkboxes.

---

## Risks / open items

- One shared packet build per run (no duplicate reading across Dev/Review); the
  grill reads the same persisted file.
- The signatures are a low-cost stand-in until item 2's tree-sitter index; item 2
  should keep `render_packet`'s output shape so switching is a drop-in.
