# Plan: Durable Tree-Sitter Code-Context Bundle

**Date:** 2026-08-14
**Status:** Draft for review
**Source:** `docs/superpowers/specs/2026-08-14-code-context-bundle-design.md`
**Required sub-skill:** superpowers:subagent-driven-development. Py: `pytest.mark.unit`;
TS: vitest; ruff 100 / pyright standard.

## Grounding (verified against current `design/curation-workflow`)

- Existing staleness engine: `src/factory/freshness/fingerprint.py`
  (`fingerprint_file`, `fingerprint_value`, `fingerprint_git_tree`).
- `/factory-init` TS (`pi-ext/factory-watch/src/factory-init.ts`,
  `factory-init-command.ts`) writes `.pi/factory/project-profile.json` with
  `source_dirs`, `hashes`, etc.
- Item 1 (`src/factory/orchestrator/context_packet.py`, from
  `2026-08-14-context-packet-*.md`) is the consumer for reference-file signatures and
  defines a stdlib signature extractor this item's index will back.
- Dependencies: `pyproject.toml` has no tree-sitter today; add as **optional**
  (try-import), keep stdlib fallback.

## Global constraints

- Reuse `factory.freshness.fingerprint`; never build a parallel checksum.
- Tree-sitter is an optional accelerator only; the factory must run without it.
- Deterministic index; consume-only when `is_fresh`.
- Additive: item 1's `context_packet` keeps its stdlib fallback; this item only
  supplies a faster/richer source when a fresh index exists.

---

### Task 1: Code index model + builder (pure, Python)

**Files:** new `src/factory/codeindex/__init__.py`, `model.py`, `build.py`; tests in
`tests/unit/codeindex/`.

^- [x] **Step 1 (tests):** `build_index` over a temp tree returns signatures for
  functions/classes/methods with stable line numbers; `engine` is
  `"tree-sitter"` when libs import, else `"stdlib-ast"`; `discover_source_files`
  reads `source_dirs` from a profile; `fingerprint_index` changes when content
  changes.
^- [x] **Step 2 (implement):** stdlib `ast`/`tokenize` extractor first (guaranteed to
  pass), then optional tree-sitter branch behind try-import; deterministic ordering.
^- [x] **Step 3:** `uv run python -m pytest -m unit` + ruff; commit.

### Task 2: Persistence + freshness + CLI

**Files:** `src/factory/codeindex/store.py`, `__main__.py`/`cli.py`; tests.

^- [x] **Step 1 (tests):** `save_index(latest.json, <fp>.json)` and `load_latest`;
  `is_fresh` recomputes fingerprint and rejects stale; `python -m factory.codeindex.build
  --root` writes a fresh latest.json (or logs a graceful fallback notice).
^- [x] **Step 2 (implement):** atomic writes (temp + rename); `is_fresh` uses
  `factory.freshness.fingerprint`; CLI catches missing tree-sitter and records
  `engine: stdlib-ast`.
^- [x] **Step 3:** unit + ruff; commit.

### Task 3: `/factory-init` trigger (TS)

**Files:** `pi-ext/factory-watch/src/factory-init.ts` / `factory-init-command.ts`;
`test/factory-init.test.ts`.

^- [x] **Step 1 (tests):** after profile write, init spawns
  `{python} -m factory.codeindex.build --root` (best-effort; a failing spawn does not
  fail init). The index path is resolved under `.factory/code-index/`.
^- [x] **Step 2 (implement):** spawnSync the builder with the detected python; log
  result to the run log; non-fatal on failure.
^- [x] **Step 3:** vitest + typecheck; commit.

### Task 4: Wire into item-1 packet + grill (integration)

**Files:** `src/factory/orchestrator/context_packet.py` +
`tests/unit/orchestrator/` (item 1 already landed), and the extension packet reader.

^- [x] **Step 1 (tests):** `build_context_packet` uses `codeindex.file_signatures` for
  reference files when `load_latest().is_fresh()`, else the stdlib fallback; a stale
  index is bypassed, not trusted. `render_index_slice` output shape matches item 1's
  signature block.
^- [x] **Step 2 (implement):** seam in `context_packet` (a small `_resolve_signatures`
  helper) + `render_index_slice`; extension grill path unchanged (it reads the same
  packet file).
^- [x] **Step 3:** full guard suite (Python unit + TS vitest) + lint; commit.

### Task 5: Review handoff

^- [x] **Step 1:** reviewer sub-agent — verify (a) `/factory-init` produces a fresh
  index or degrades gracefully; (b) stale index never used; (c) deterministic; (d)
  tree-sitter optional (stdlib fallback runs); (e) reuses fingerprint, no parallel
  checksum; (f) additive to item 1 + registry work; (g) gitignored under `.factory/`.
^- [x] **Step 2:** fix findings; tick checkboxes.

---

## Risks / open items

- Native tree-sitter under Windows is the main install risk; the optional/fallback
  design absorbs it (engine flag makes it visible).
- Post-init new files aren't in the index until re-init; the lazy `is_fresh` + stdlib
  fallback covers correctness in the gap.
