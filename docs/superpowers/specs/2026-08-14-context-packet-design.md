# Design: Content-Bearing Context Packet

Date: 2026-08-14
Status: Draft for review
Builds on:
- `2026-08-14-context-handoff-roadmap.md` — memory item 1 (this is the first open
  work item).
- `docs/superpowers/specs/2026-08-12-grill-understanding-node-design.md` and
  `src/factory/orchestrator/prompts.py` — where the manifest is currently rendered
  as bare file-path bullets.

## 1. Problem

The context-gatherer produces a manifest whose `context.source_files` is a list of
**file-path pointers**, not content. When handed to Dev, `compose_prompt` renders it
as `## Context (from manifest)` → `- <path>` bullets. Every downstream node (dev,
and especially the grill, which currently receives *no* manifest at all) must
re-read the plan, the spec and every file from zero, paying the full discovery
token cost the gatherer was supposed to save. The gatherer's work is effectively
discarded — its output is a certificate of coherence, not a package of context.

## 2. Goals / non-goals

Goals:
- Materialize the gatherer's `source_files` into a **content-bearing context packet**
  that Dev, Review and the Grill all consume, so nothing re-discovers what the
  gatherer already did.
- Deterministic, token-budgeted: primary files in full, reference files as
  signature summaries (not full dumps).
- Persisted to a stable on-disk path both Python (`compose_prompt`) and the
  extension (grill seed) can read.

Non-goals (item 2 of the roadmap — separate):
- A durable **cross-run** code index (tree-sitter symbol graph / PageRank) built by
  `/factory-init`. Item 1 uses a simple deterministic stdlib extractor; item 2 swaps
  in tree-sitter and makes the index reusable across runs. Item 1 is
  per-task, on-the-fly.

## 3. The packet

A pure module `src/factory/orchestrator/context_packet.py`:

- `primary_paths(task, manifest) -> set[str]` — path globs of `Modify:`/`Create:`
  deliverables (reuse `parse_deliverables`) that are also present in
  `context.source_files`. These are files the agent must read in full.
- `build_context_packet(task, manifest, repo_root) -> dict` — for each
  `source_files` entry:
  - **primary** → full file content, per-file size-capped (a file over the cap
    falls back to signature summary so one huge file can't blow the budget);
  - **reference** → a **signature summary**: top-level `def`/`class` signatures +
    line numbers + a one-line module docstring/header, via stdlib `ast`/`tokenize`
    (dependency-free until item 2 swaps in tree-sitter). No bar. no secrets.
  - missing/unreadable files are recorded (not fatal).
  - bounded total bytes (env-tunable cap, mirroring `FACTORY_*` env contracts).
- `render_packet(packet) -> str` — the deterministic markdown block consumed by
  `compose_prompt`: a per-file section with full content (primary) or signatures
  (reference).
- Persisting: `write_context_packet(packet, transcript_dir)` writes
  `<transcript_dir>/context-packet.json` (same directory as `review-guide.json` /
  `validation-report.json`), so the extension reads it for the grill seed.

## 4. Wiring

- **Python (`nodes.py` / `runner.py`):** after the context-gatherer passes, build the
  packet once, persist it to the transcript dir, and thread it into `compose_prompt`
  for **Dev** and into `run_review` for **Review**. `compose_prompt` gains an
  optional `packet` parameter: when present, it embeds `render_packet(packet)`
  instead of the bare file-path bullets; the bullets remain as the fallback when no
  packet is supplied (e.g. resumed runs).
- **Grill (extension `index.ts`):** `openGrillWindow` currently builds the seed from
  task text + explainer list only. Add a `readContextPacket(cwd, sessionId)` helper
  (mirrors `readFreshExplainerSummary`) that reads `<transcript_dir>/context-packet.json`
  and injects a bounded rendered slice (or a clear "context packet not available"
  fallback) into `buildGrillSeedPrompt`. This closes the "grill re-reads from zero"
  gap: the grill agent arrives already knowing the task + code.

## 5. Token budget policy

- `PRIMARY_FILE_CAP_CHARS` (default ~12k) per primary file; over-cap → signature.
- `REFERENCE_MAX_SIGS` (default ~40) signatures per reference file.
- `TOTAL_PACKET_CAP_CHARS` (default ~60k) overall.
- All env-tunable (`FACTORY_PACKET_*`), consistent with existing `FACTORY_*_TIMEOUT_S`.
- `render_packet` truncates defensively and always closes its fence/markdown.

## 6. Risks / open items

- **Determinism:** content is read fresh each run; the packet is not a cache (item 2
  is the cache). No hash/fingerprint needed for item 1; freshness is inherited from
  the current file contents.
- **Non-code files** (`.md`, `.svg`, binary): signature extraction only applies to
  code; other types fall back to a short head-slice or are left as pointers.
- **Prompt length:** caps keep the added tokens bounded; the reference-signature
  form is the main guard. Review/Dev share one packet build (no duplicate reading).
- **Grill window size:** the injected packet slice must respect the same
  total-cap; the grill re-reads the file itself if it needs more (interactive
  window has its own tools).

## 7. Acceptance

- Dev prompt contains primary-file content from the manifest (not just paths).
- Review receives the packet (its prompt includes primary content / signatures).
- Grill seed contains a bounded packet slice; a run with no packet still seeds
  (degrades to task-text-only, current behavior).
- Pure `build_context_packet`/`render_packet` are unit-tested (primary-full vs
  reference-signature, cap fallback, missing file, total cap).
