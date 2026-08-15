# Memory / Roadmap — Context Handoff, Durable Code Bundle & Web Research

> **Status as of 2026-08-14:** ALL three originally-reported issues are fixed and
> committed. Option A (registry+notification) = c32cdc0; item 1 (content-bearing
> context packet) = bc79955; item 2 (durable code index) = 5975208. The only
> remaining *optional* follow-ups are noted at the bottom. The sections below keep
> the full background for anyone revisiting this.

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

**STATUS: IMPLEMENTED + COMMITTED (bc79955)** — see the spec/plan. `context_packet.py`
materializes the manifest into a token-budgeted packet (primary files in full,
reference files as signatures), persisted to `<transcript_dir>/context-packet.json`,
threaded into Dev/Review, and read by the grill seed via the extension's
`readContextPacket`/`renderPacketSlice`. Falls back to path bullets / task-text-only
seed when absent.
- Feed the **grill seed** the packet too — currently `openGrillWindow` builds a fresh
  window from raw task text only (`index.ts`), so it re-reads plan + code from zero.
- Decide the packet's on-disk form (sibling JSON/SRG alongside the manifest?) and how
  `compose_prompt` embeds it for each role.

## Open work item 2 — Durable code-context bundle built by `/factory-init` (root causes 3+5)

**STATUS: IMPLEMENTED + COMMITTED (5975208)** — `factory.codeindex` (tree-sitter
preferred, stdlib-ast fallback) persists a hash-keyed symbol index under
`.factory/code-index/`. `/factory-init` builds it once; an extension `session_start`
hook runs `--ensure` on every session open, which recomputes ONLY when the cheap
checksum (fingerprint) shows the code changed (`ensure_fresh`). Item 1's packet
consumes index signatures for reference files when fresh. See the spec/plan docs.

Note on tree-sitter: wheels of tree_sitter_languages are ABI-mismatched with the
top-level tree-sitter binding on this machine across versions; the engine reports
`stdlib-ast` here and degrades safely. The optional dep is documented in pyproject.

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

## Suggested next session entry point (OPTIONAL follow-ups only)
Everything the user asked for is done and committed. If continuing to evolve this
area, the only remaining *optional* upgrades from the web research are: (a) a
PageRank-ranked retrieval layer over the index (aider-style), and (b) an MCP/query
server instead of the bundled static artifact. Both would replace/upgrade
`render_index_slice`'s consumption path; the index format is stable for that.
