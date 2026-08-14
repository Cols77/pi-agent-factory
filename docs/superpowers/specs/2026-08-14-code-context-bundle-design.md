# Design: Durable Tree-Sitter Code-Context Bundle

Date: 2026-08-14
Status: Draft for review
Builds on:
- `2026-08-14-context-handoff-roadmap.md` — memory item 2 (this spec + a sibling
  plan make it actionable).
- `2026-08-14-context-packet-design.md` — item 1, the consumer of this index for
  reference-file signatures.
- `src/factory/freshness/fingerprint.py` — the existing staleness engine we reuse.
- `.pi/factory/project-profile.json` + `pi-ext/factory-watch/src/factory-init.ts` —
  the `/factory-init` bootstrap that owns long-lived project artifacts.

## 1. Problem

Every session (and every node: dev, review, grill) re-reads the codebase because
nothing durable exposes code structure. Item 1 materializes the task's own files,
but that is still **per-task, on-the-fly** and re-parses each time it runs. The
roadmap's goal is: index the codebase **once** into a persistent, queryable
structure, then serve a token-budgeted, task-relevant slice on demand — so the
gatherer, dev, review and grill stop re-paying discovery. This is the "read once,
reuse many" store at the root of root causes 3+5.

## 2. Goals / non-goals

Goals:
- A **durable, hash-keyed symbol index** of the codebase, built at `/factory-init`
  time and reused across sessions and nodes.
- **Tree-sitter** preferred for parsing (accurate multi-language AST), with a
  **stdlib `ast` fallback** so the factory still works if the (optional) dependency
  is absent on a given machine/Windows setup.
- A stable, deterministic on-disk format consumed by Python (`context_packet.py`
  signature extraction) and, via the same file, by the extension (grill seed).
- **Reuse `factory.freshness.fingerprint`** for staleness — do not invent a parallel
  checksum.

Non-goals:
- Not a full query server / MCP (that was a "later option" in the roadmap); this is
  the bundled static artifact.
- Not embeddings / semantic search (out of scope; PageRank-ranked retrieval could be
  a follow-up).
- Not replacing item 1: item 1 gives the packet full content for primary files; this
  index supplies the *reference-file signature summaries* (and a faster,
  cross-run signature source).

## 3. The index

A Python package `src/factory/codeindex/`:

**On-disk layout** (stable, under `.factory/code-index/`, gitignored):
```
.factory/code-index/
  <fingerprint>.json     # symbol index for one source-set fingerprint
  latest.json            # { fingerprint, engine, generated_at, manifest }
```

**Index format** (`<fingerprint>.json`):
```json
{
  "schema": 1,
  "engine": "tree-sitter" | "stdlib-ast",
  "generated_at": "<ISO>",
  "fingerprint": "<fingerprint of the source set>",
  "files": {
    "src/a/b.py": {
      "language": "python",
      "module_doc": "one-line purpose (first docstring/comment block)",
      "signatures": [
        {"kind": "function"|"class"|"method", "name": "...", "signature": "def f(a, b) -> T",
         "line": 12, "summary": "one-line from docstring first line"}
      ]
    }
  }
}
```

**Pure API** (`src/factory/codeindex/model.py` + `build.py`):
- `discover_source_files(repo_root) -> list[str]` — the code files under the
  `source_dirs` recorded in `project-profile.json` (extensions from a language map).
- `build_index(repo_root, files=None) -> CodeIndex` — parse the set; prefer
  tree-sitter, fall back to stdlib `ast`/`tokenize`. Deterministic (stable file
  order, deterministic signature lines).
- `fingerprint_index(files, repo_root) -> str` — reuse
  `factory.freshness.fingerprint` to hash the source set's current content.
- `load_latest(repo_root) -> CodeIndex | None`; `is_fresh(index, repo_root) -> bool`
  (recompute fingerprint vs stored; replaces nothing — callers never trust a stale
  index).
- `file_signatures(index, path) -> list[Signature] | None`;
  `render_index_slice(index, paths, cap) -> str` — the token-budgeted markdown the
  packet/gatherer consume.

**Integration seam (item 1 uses this):**
`context_packet.build_context_packet` calls `codeindex` for **reference-file**
signature summaries; when no fresh index exists it falls back to the bundled stdlib
signature extractor from item 1. `render_index_slice`'s output shape matches item 1's
`render_packet` signature block, so swapping is drop-in.

## 4. Trigger / freshness lifecycle

- **`/factory-init`** (TS, `factory-init-command.ts`): after writing
  `project-profile.json`, spawn the builder:
  `{python} -m factory.codeindex.build --root <root>` (best-effort, non-fatal on
  failure — log to the run log). This is the "bundle built at init" step.
- **Lazy consumer**: the packet builder reads `latest.json`, and uses the index only
  if `is_fresh` is true (recompute fingerprint cheaply). Otherwise it falls back to
  item 1's stdlib extractor (correct, just slower) — a stale index is never trusted,
  it is simply bypassed. No parallel staleness engine.
- **Dependency**: `tree-sitter` + `tree-sitter-languages` registered as optional
  (try-import at build time); the fallback keeps the factory runnable without them.

## 5. Token budget / determinism

- `render_index_slice` caps per-file signatures and total bytes (env-tunable
  `FACTORY_INDEX_*`, consistent with item 1's `FACTORY_PACKET_*`).
- Signatures carry `line` numbers so dev/review/grill can jump straight to the source
  instead of scanning.

## 6. Risks / open items

- Tree-sitter language grammar availability per file type; unknown types fall back to
  a head-slice or are left as pointers.
- The index covers the repo's code dirs at init time; files created *after* init are
  not in it until a re-init — the lazy `is_fresh` check + stdlib fallback absorbs
  that gap (task files not in the index still get correct signatures, just from
  stdlib).
- Windows: `tree-sitter-languages` ships binary wheels; if the native dep is
  unavailable, the fallback path is exercised (flag `engine` makes this visible).

## 7. Acceptance

- `/factory-init` produces a fresh `latest.json` index for the repo (or degrades
  gracefully to stdlib engine with a logged notice).
- `context_packet` consumes index signatures for reference files when fresh, else
  stdlib.
- A stale index (checked-in + then source edited) is never used as-is.
- Deterministic: same source set → same signatures.
