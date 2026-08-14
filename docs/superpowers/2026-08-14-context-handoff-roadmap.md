# Memory / Roadmap — Context Handoff, Durable Code Bundle & Web Research

> **Purpose of this doc:** a memory to *come back to* in order to **specify and plan
> what is still missing**. The Option-A fix (shared pipeline node registry +
> transition-driven notification, `2026-08-14-pipeline-node-registry-*.md`) has been
> **implemented** (node-registry.json/ts, pipeline-diff.ts, dashboard/status-format
> derived from the registry, index.ts transition watcher). Everything below in items 1–2
> is **not yet specified or planned** — it is the design work still open. Treat it as the
> starting point for the next session that picks this up.

## Why this exists (the three reported bugs and one architectural root)

During a review session on 2026-08-14 the user reported: (1) the grill node never
shows in mission control (you must re-run `/factory-watch`), (2) context-gather
seems wasted — downstream nodes (grill/dev/review) re-read the codebase instead of
consuming gathered context, and (3) `/factory-init` shouldn't re-discover the
codebase every session.

The architectural root under all of them (verified in code):
- The pipeline node graph is duplicated across Python (`runner.py`/`nodes.py`) and
  TS (`status-format.ts`/`mission-control-dashboard.ts`/`index.ts`) with no shared
  contract → adding a node is shotgun surgery.
- Mission control is **pull-only** over a detached producer → blocking state can't
  push; notification is bolted on (widget string).
- Each node is a **fresh `pi` process**; the only inter-node channel is the prompt
  string. The context manifest is a *validation* artifact whose data payload is just
  **file-path pointers** (`context.source_files` → `- <path>` in `compose_prompt`),
  not content. The grill session gets neither the manifest nor any content.
- There is **no durable code-content layer**: `/factory-init` persists commands/
  components/invariants but zero code contents, so re-reading is forced.

Option A (registry + transition notification) fixes the first two. **Remaining open
design work (the real prize) is the context/content problem below.**

## Open work item 1 — Content-bearing context packet (root cause 4)

The gatherer's manifest should carry content, not just paths, so its work is consumed
by grill, dev and review instead of discarded:
- Primary/modify files: full content (or near-full) in the packet.
- Reference files: signature-level summaries, not full dumps (token budget).
- Feed the **grill seed** the packet too — currently `openGrillWindow` builds a fresh
  window from raw task text only (`index.ts`), so it re-reads plan + code from zero.
- Decide the packet's on-disk form (sibling JSON/SRG alongside the manifest?) and how
  `compose_prompt` embeds it for each role.

## Open work item 2 — Durable code-context bundle built by `/factory-init` (root causes 3+5)

Extend the project bootstrap to emit a machine-built, hash-keyed **code index** that is
reused across sessions/nodes. Reuse the existing `factory.freshness.fingerprint`
engine (the grill spec explicitly says "do not build a parallel checksum").

## Web research (2026-08-14) — existing tools to borrow from

Access: no dedicated websearch tool in this harness; used `curl` → GitHub Search API
(unauthenticated) and PyPI. Key, directly-relevant open-source prior art:

- **Aider** (`Aider-AI/aider`, ~48k★) — the canonical **repo-map**: tree-sitter AST →
  ranked symbol map, **PageRank**, then a **token-budgeted** slice (tiktoken) served on
  demand. This is *the* model for "index once, feed a budgeted slice per task."
- **tree-sitter / tree-sitter-languages** (PyPI, binary wheels, 28+ langs) — the
  practical AST parsing layer for the bundle in item 2; avoids dropping whole files.
- **Repo-map ports:** `dereira/goldfish` (Go: tree-sitter + PageRank, "token-budgeted
  repo maps for LLM context") — directly named as a port of aider's repomap.
- **MCP code-intelligence servers** (the dominant current form factor):
  - `DeusData/codebase-memory-mcp` (~38k★) — persistent knowledge graph code index.
  - `jcodemunch-mcp` (~2.5k★) — "cut AI token costs ~95% on code exploration", precise
    symbol-level retrieval.
  - `forloopcodes/contextplus` (~2k★), `Cranot/roam-code` (SQLite code graph, 28 langs).
  - `nduc99911/repo-context-mcp` — repo map + code search + **token-aware context packs**.
- **Slimmer per-task / context-pack tools:** `nduc99911/repo-context-mcp`,
  `shanirsh/prismodev` (scans repo, finds token waste, generates smaller packs),
  `mauriziofonte/toktoken` (ctags+SQLite).

**Takeaway for the spec/plan we still need:** the mature pattern is *index the codebase
once into a persistent, queryable structure, then serve a token-budgeted, task-relevant
slice on demand*. We should confirm we want a bundled static artifact (simplest,
matches "read once, reuse many") vs. a tree-sitter MCP/local server (more powerful,
more moving parts). Recommend: **start with a bundled tree-sitter symbol index +
token-budgeted slice** emitted by `/factory-init`, and treat an MCP/query server as a
later option if the bundled slice proves too coarse.

## Outstanding questions to resolve when planning
- Do we vendor `tree-sitter`/`tree-sitter-languages` as a dependency, or shell out to
  a small binary? (Windows constraints matter for this repo.)
- Where the code index lives, its freshness contract (fingerprint reuse), and its
  token-budget policy (per-role caps).
- Whether the context packet and the code bundle are one mechanism or two (likely one
  layered mechanism: global index from init + per-task packet from gatherer).

## Suggested next session entry point
Read this doc + the Option-A spec/plan (now implemented), then write a **spec + implementation plan** for
open work item 1 (context packet), followed by item 2 (durable bundle). Keep root causes
in mind so the fix is structural, not a patch.
