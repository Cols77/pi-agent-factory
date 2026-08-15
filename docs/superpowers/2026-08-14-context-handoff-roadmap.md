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

## Re-verification status (2026-08-15, session sm-0007)
The reviewer-subagent follow-up was attempted again. The subagent tool **still
fails on this machine** (`(no stderr)` on a minimal probe) — the re-verification
was therefore run **in-session** against each plan's reviewer checklist, and all
three pass (evidence in `docs/superpowers/2026-08-14-handoff.md` §1 + the
session-memory note sm-0007):

- **Pipeline node registry** (plan Task 4 a–e): vitest 58+43 green; `diffBlocked`
  drives `maybeOfferGrill` on transition (pre-loop one-shot removed); nag-free via
  double self-guard; no `STAGE_ORDER`/`NODE_LABELS` literals remain (only comments);
  commit `c32cdc0` touches 0 Python files.
- **Context packet** (plan Task 4 a–f): pytest 18 + vitest 58 green; packet threaded
  to Dev (`runner.py:242`) and Review (`runner.py:310`), grill seed consumes a
  bounded `renderPacketSlice` slice and degrades to task-text-only; stdlib-only
  (tree-sitter appears only in a comment + the item-2 codeindex seam); caps are
  `FACTORY_PACKET_*` env-tunable; no parallel freshness engine.
- **Code bundle** (plan Task 5 a–g): pytest 25 + vitest 19 green; `--ensure` reports
  `stdlib-ast` over 148 files (expected on this machine — ABI mismatch); stale index
  bypassed via `is_fresh` in `context_packet._resolve_index`; `fingerprint_for`
  reused from `factory.freshness`; `.factory/code-index/` gitignored; tree-sitter is
  an optional pyproject extra.

## Tree-sitter now engages (2026-08-15, session sm-0007)
Item-2 follow-up **done**: tree-sitter no longer degrades to `stdlib-ast` on this
machine. Root cause was NOT ABI — `tree_sitter_languages` 1.10.2 calls the old
`Parser(language)` API while the installed top-level `tree-sitter` 0.26 moved that
arg out of `__init__` (`TypeError: __init__() takes exactly 1 argument (2 given)`).
Fix in `src/factory/codeindex/sigs.py`:
- New `_get_parser(language)` prefers the **per-language grammars** the tree-sitter
  org ships ABI-matched to the binding (`tree-sitter-python`, `tree-sitter-typescript`,
  plus go/rust/java/c/cpp/ruby/php/bash/javascript), falling back to the bundle.
- New `_make_parser` bridges the 0.25/0.26+ `Parser(language)` vs `Parser()+.language`
  API split.
- The tree-sitter walker was generalized to non-Python node types
  (`function_declaration`/`class_declaration`/`method_definition` in TS/JS, go, rust,
  etc.) with class-depth tracking so class methods still classify as `method`—not
  `function`—matching the stdlib extractor's output shape.
- `pyproject.toml` `code-index` extra now also installs `tree-sitter-python` +
  `tree-sitter-typescript` (the languages this repo actually contains: 148 .py, 67 .ts).

Verified: `factory.codeindex --root .` now **reports engine `tree-sitter`** over 148
files; unit tests pass (11 in codeindex, incl. 2 new optional tests locking in
python-method + Typescript classification); ruff clean. Note: the CLI indexes only
`source_dirs` (default `["src"]`), so `pi-ext/...` is not in the `--root .` index
unless source_dirs includes it — a pre-existing discovery-scope matter, separate from
this fix.

## Normal-session code-context injection (2026-08-15)
Next follow-up done: a `before_agent_start` extension hook now injects a **bounded slice**
of the project's durable code index into an ordinary pi session (not just the factory
pipeline). New `pi-ext/factory-watch/src/code-context-inject.ts`:
- `renderIndexSlice(root)` shells out to `factory.codeindex --root <root> --slice <chars>`
  (default 24k) so freshness/ordering/caps stay in Python — the TS side never re-derives
  them.
- Gated **once per (root, sessionId)** via `shouldInject` (uses the SDK's
  `ctx.sessionManager.getSessionId()`), so it fires on the first prompt of a session, not
  every turn.
- Non-fatal everywhere: missing index/python → skip; stale index → skipped by `is_fresh`
  (the `--slice` verb runs `ensure_fresh` first).
- Registered in `factory-init-command.ts` on `before_agent_start`; new `--slice` verb added
  to `factory.codeindex` CLI (prints bounded markdown, no banner line).

To cover a project's real code, discovery now honors `.pi/factory/project-profile.json`
`source_dirs` (written by /factory-init) instead of hard-coded `["src"]`, and skips vendor
dirs (`node_modules`, `.venv`, `dist`, ...). Verified against `cool_physical_ai_project`
(engine `tree-sitter`, 168 files) and this repo (474 files, py+ts, 13.7s).
