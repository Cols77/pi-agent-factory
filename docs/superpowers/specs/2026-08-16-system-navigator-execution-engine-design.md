# System Navigator Execution Engine: Persistent Worker + Combined Dossier

**Status:** implemented 2026-08-16
**Amends:** 2026-08-13-spb-health-performance-design.md (§4 execution model),
2026-08-08-system-navigator-briefing-validation-guide-design.md (§6.1 API surface)
**Scope:** docs server (`pi-ext/factory-watch`) + `factory.system` CLI

## Problem (measured)

Every `/system` scope navigation fires up to seven `/api/system/*` requests,
and each request previously spawned a fresh `uv run python -m factory.system
<cmd> --json` process. On this machine the per-process budget was:

| stage | time |
| --- | --- |
| `uv` + interpreter boot | 0.3–0.5 s |
| module import graph (~200 modules incl. yaml, schema chain) | 0.5–0.9 s |
| actual computation | 0.2–0.4 s |

cProfile showed `health` spending essentially all of its ~1.35 s in module-load
machinery (`nt.stat`, `_io.open`, `marshal.loads`, `find_spec`) — no
`factory.*` computation function appears in the top 20 self-time entries.
Optimizing computation logic would have been a few percent; changing the
execution model is a 10–30× change.

## Design

### 1. `factory.system worker` — one long-lived JSON-lines process

New CLI subcommand (`src/factory/system/worker.py`). The docs server spawns one
worker per served repo root and speaks a two-line protocol over stdin/stdout:

```
→ {"id": 1, "cmd": "brief", "params": {"scope": "bundle:evidence-lifecycle"}}
← {"id": 1, "ok": true, "value": {...}}
← {"id": 1, "ok": false, "error": "...", "kind": "ScopeNotFoundError"}
```

Rules, enforced by the worker:

- stdout carries **only** response lines; one response per request; the loop
  exits 0 on stdin EOF (that is how the server shuts it down).
- Only read-only projections are served (`goal evaluate` and `guide --export`
  — the package's write affordances — have no handler; the browser has no
  write path).
- Every handler is the same `cmd_*` function the one-shot CLI uses, so a warm
  answer is byte-for-byte the same *computed* JSON as a cold one. Startup and
  imports are amortized; nothing else changes.

`pi-ext/factory-watch/src/system-worker.ts` owns the child: lazy spawn, request
ids matched against responses, 20 s per-request timeout (a hung worker is
discarded and the next request respawns), and crash/exit rejection of every
pending request. **A request resolves `null` when the worker is unusable** —
never a guessed payload — and the route then falls back to the existing
one-shot CLI runner, so every route behaves exactly as before with a dead or
missing worker. `stopDocsServer()` stops the worker.

### 2. `factory.system dossier` — the combined navigation payload

New CLI subcommand (`src/factory/system/dossier.py`): one invocation computes
brief + matrix + timeline + guide (+ vcycle for `feat:`/`sr:`, + validation
for `sr:`) in one process. Section semantics mirror the browser's per-endpoint
contract exactly:

- brief/matrix/timeline are strict — a failure fails the dossier, precisely as
  a failing individual endpoint fails a scope load today;
- guide/vcycle/validation are best-effort — `null` + `_error` degrade only
  their own tab, with the same degrade-only-that-tab text the legacy path
  renders. Every key is always present (null when inapplicable) so the browser
  branches on one stable shape.

The full `factory.system` JSON shapes are unchanged; dossier only groups them.

### 3. Docs-server routes and browser

- Every `/api/system/*` route goes through a single worker-first helper
  (`docs-server.ts` `systemRequest`) with the one-shot loader as fallback.
- The browser (`system-bootstrap.ts`) fetches `/api/system/dossier?scope=` for
  bundle/sr/feat navigation and renders from the single payload; on any
  fast-path failure (non-ok, malformed shape, transport error) it falls back
  to the legacy per-endpoint fetches. Traversal stays a separate best-effort
  fetch in both paths (it keeps its own abort timeout). The legacy per-endpoint
  endpoints all still exist and are unchanged for compat and for the fallback.

### 4. What did NOT change

- **Python-computes / browser-renders contract**: Python computes every
  payload; TS renders, never re-derives freshness/ordering/provenance.
- **No persistent cache**: the worker recomputes every request from current
  files; nothing is cached to disk or retained between requests. SP-B's
  "no persistent cache" boundary is untouched.
- All existing `/api/system/*` endpoints, their payloads, and the SP-B async
  behavior (never block Node's event loop) are preserved. The worker is
  strictly faster at both: requests are async I/O and no per-request spawn.

## Measurements (this machine, fixture repo with 10 SRs + 1 bundle)

| path | before | after |
| --- | --- | --- |
| `health` | ~1.0–1.9 s (one-shot) | ~0.2 s warm (0.75 s incl. one-time boot) |
| `brief` | ~1.0 s (one-shot) | ~0.02 s warm |
| `labels` | ~1.6 s (one-shot) | ~0.7 s warm (compute-bound: reads every spec/plan) |
| `dossier` (bundle) | 4–7 one-shot processes, ~1.5–2 s wall | ~0.06 s warm, one process |

On a product-scale repo the fixed ~1 s boot is fully amortized, and dossier
collapses the fan-out from 5–7 processes to 1.

## Failure semantics (tested)

- worker spawn impossible / crash / hang / protocol corruption → request
  resolves `null` → one-shot fallback → same 503/200 the route always had;
- structured Python error through the worker → non-null `{ok:false}` → 503
  with the Python error text, identical to the one-shot path;
- browser fast-path unavailable → legacy per-endpoint fetches, byte-identical
  rendered DOM.

## Tests

- Python: `tests/unit/system/test_worker.py` (protocol, dispatch, error kinds,
  EOF shutdown, write-command refusal, dossier mirroring of one-shot output),
  `tests/unit/system/test_cli.py` (dossier subcommand JSON/text/error).
- TS: `test/system-worker.test.ts` (protocol, id matching, crash/timeout
  fallback), `test/system-cli.test.ts` (dossier loader), `test/docs-server.test.ts`
  (dossier route + 503), `test/system-page-navigation.test.ts` (browser fast
  path + legacy fallback), `test/system-page.test.ts` (worker-shaped harness:
  worker-served health/traversal, worker domain error → 503, crashed-worker
  fallback).

Gates: python unit 1449 passed, vitest 1019 passed, tsc clean, ruff clean,
pyright at pre-existing baseline (21, none new).
