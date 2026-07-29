# Coherence Evidence Connectors — Design

**Date:** 2026-07-29
**Status:** Approved (design), pending implementation plan
**Consumer (v1):** the context-gather coherence gate (`validate_manifest`)

## Problem

The context-gather gate today (`src/factory/validation/manifest_validator.py`)
proves a manifest is **well-formed, self-consistent, and points at real files**.
But the semantic core — `coherence.proven` and every `coherence.checks[].pass` —
is **self-attested by the LLM**. The agent writes `"proven": true` and fills its
own checklist with `"pass": true`; the validator only confirms the agent's
*claim*. This is the "hollow coherence proof" hole: an agent can declare
trivially-true or irrelevant checks, they pass honestly, `proven` derives true,
and a meaningless proof is accepted.

The context-gatherer runs with `bash="deny"` (`roles.py`), so it cannot execute
anything itself — it only reads files. Any "re-runnable" verification must be
performed by **trusted factory code**, not by the agent.

## What this design does and does NOT solve

Re-running agent-authored checks proves those checks are **honest** (they really
pass), not that they are **sufficient** (that the agent chose the *right*
checks). Sufficiency is task-specific semantic judgment — the exact job we
delegate to the LLM — and cannot be fully mechanized.

Therefore the design is **two layers**:

1. **Factory-derived required coverage (agent-independent).** Mechanically
   generated from what the *task itself declares* (its deliverables). This is
   the real "did you gather the right things" floor; the agent cannot opt out of
   it.
2. **Connector-verified checks (honesty layer).** The agent's own coherence
   claims, re-executed by trusted code. This can only *strengthen* a proof above
   the floor; it cannot establish sufficiency.

**Honest ceiling:** above what the task structurally declares, sufficiency
remains LLM judgment. Layer 1 guarantees the floor; layer 2 guarantees the agent
is not lying about the rest. Nothing here claims to prove "all required
information is present" in the general case — that is not mechanically decidable.

## Architecture

### New unit — evidence subsystem (`src/factory/evidence/`)

A connector-based, extensible evidence framework. `kind`s are pluggable
connectors over heterogeneous evidence sources.

```
Connector (Protocol)
  kind: str                          # unique; matched against checks[].kind
  args_schema: dict                  # JSON-schema for agent-supplied args (UNTRUSTED)
  side_effect_free: bool             # static read vs. executes something
  evaluate(args, ctx) -> CheckResult # CheckResult(passed: bool, evidence: str)

EvidenceContext (ctx)                # evidence-source bundle
  repo_root                          # filesystem connectors
  gates                              # GateRunner  -> test_result
  kb                                 # KB retrieval -> future kb_* connectors

Registry
  register(connector) / get(kind)
  evaluate_checks(checks, ctx) -> list[CheckResult]
```

A connector touches only the sources it needs; new evidence sources are added to
`ctx` without changing existing connectors.

### Trust boundary (load-bearing)

- Connector **code** is trusted: it lives in-repo and is code-reviewed.
- Connector **args** are untrusted: they come from the agent's manifest.

A connector maps args to **fixed operations** and never interpolates them into a
shell. `test_result{gate: "unit"}` (fixed enum) is safe; a hypothetical
`run{cmd: "<string>"}` connector is banned by construction — it would re-open the
arbitrary-code-execution hole that `bash="deny"` deliberately closes.

### Layer 1 — factory-derived coverage (`src/factory/evidence/coverage.py`)

`required_coverage(task) -> list[RequiredRef]`, derived purely from the task:

- `parse_deliverables(task.body)` (already exists) yields `Create:` / `Modify:` /
  `Test:` targets.
- **`Modify:` and `Test:` targets** must appear as a resolved reference in
  `manifest.context` (`source_files` / `spec` / `plan`) and resolve on disk.
- **`Create:` targets** must **not** already exist — that is the already-done
  signal, handled by the existing already-done routing; this layer does not
  double-check it.
- v1 stops at deliverables. Extracting file paths from free-text DoD is
  heuristic and **out of scope for v1** (keep the floor reliable, not clever).

### Layer 2 — connectors (v1 vocabulary)

Static (pure, read-only, `side_effect_free: true`):

- `files_exist {paths}`
- `file_contains {path, pattern, mode: regex|literal}`
- `symbol_defined {path, symbol}` — AST for code, heading for markdown
- `anchor_resolves {ref: "path#anchor"}` — closes the current `_strip_anchor`
  gap, where only the pre-`#` path is checked and the anchor is discarded

Dynamic (`side_effect_free: false`, executed via the trusted `GateRunner`):

- `test_result {gate: unit|sim|full, expected: pass|fail}` — evaluated at
  context-gather time, so it is a **baseline** check:
  - `expected: pass` — a regression safety net exists (feature task).
  - `expected: fail` — the bug reproduces at baseline (bug-fix task).

## Contract change

### Schema (`src/factory/schemas/context_manifest.schema.json`)

- `coherence.checks[]` items become `{name, kind, args}` with
  `additionalProperties: false`.
- The agent-supplied `pass` (per check) and `proven` are **removed from the
  contract entirely** — the factory computes both. This deletes self-attestation
  at the schema level rather than trusting-then-checking it.

### `validate_manifest` flow (revised)

1. Schema-validate structure.
2. **Layer 1:** compute `required_coverage(task)`; every required ref must be
   present in `manifest.context` and resolve on disk, else error.
3. **Layer 2:** for each `checks[]` entry → registry looks up `kind` → validates
   `args` against the connector's `args_schema` → calls `evaluate`; any failed
   check → error. Unknown `kind` → hard error.
4. Existing `context.*` reference-existence check (kept).
5. `proven` is **derived** = layers 1+2 all pass. There is no agent `proven` to
   reconcile — it is gone.

> Note: `validate_manifest(manifest, repo_root)` currently takes only
> `repo_root`. It now also needs the `task` (for coverage) and an
> `EvidenceContext` (for connectors). Threading these from `run_context_gatherer`
> is part of the implementation plan.

### Prompt (`roles.py` `CONTEXT_GATHERER`)

Instruct the agent to:

- express coherence as typed checks drawn from the connector vocabulary;
- understand the factory **re-runs** every check, so hollow checks buy nothing;
- ensure every declared `Modify:` / `Test:` deliverable is gathered into context.

## Error handling / failure modes

- Unknown `kind`, or args failing the connector's `args_schema` → hard error
  (forces use of the real vocabulary).
- A connector raising inside `evaluate` → caught, treated as a **failed** check
  with `evidence = "<connector> errored: <summary>"`; never crashes the gate.
  Deterministic.
- `test_result` runs a gate at context-gather time (cost) — only when the agent
  declares one; reuses the existing subprocess/timeout path in
  `SubprocessGateRunner`.
- The context-gather node's existing 2-attempt loop is unchanged: a first-pass
  miss feeds the existing `handoff` and self-corrects on retry.

## Testing

- Pure unit tests per connector (read-only, deterministic; trivial to fixture).
- Registry: unknown-kind rejection, arg-schema rejection, connector-error →
  failed-check behavior.
- `coverage.required_coverage`: deliverable parsing → required refs; `Create:`
  vs `Modify:` / `Test:` handling.
- `validate_manifest` integration:
  - an honest-but-hollow check is **no longer sufficient** when a declared
    deliverable is uncovered (Layer 1 catches it);
  - a manifest still carrying agent `pass` / `proven` is **schema-rejected**;
  - `test_result{expected: fail}` bug-repro path via the existing
    `FakeGateRunner`.

## v1 scope boundary (YAGNI)

**In v1:** the framework + `Registry` + filesystem connectors + `test_result`;
Layer 1 coverage from deliverables; consumer #1 and only = the coherence gate.

**Designed-for but NOT built in v1:**

- `kb_*` connectors (KB retrieval as an evidence source) — e.g. `kb_relevant`,
  `kb_entry_exists`, and "bug description" grounding for bug-fix tasks.
- User-supplied connector discovery (dropping in custom connectors without
  touching core).
- Reuse of the same connectors as **post-work** evidence at the already-done and
  review nodes (where `test_result{expected: pass}` validates the *work*, not
  just the baseline).

The abstraction is built to accept these; the wiring is deferred until the
interface is proven by consumer #1.

## Rejected alternatives

- **Agent-authored commands run in a sandbox** — maximally expressive but
  re-opens arbitrary code execution that `bash="deny"` deliberately closes; large
  security surface. Rejected.
- **Hybrid: vocabulary + a second LLM re-check for un-expressible claims** —
  reintroduces LLM non-determinism into the gate, the exact thing being removed;
  extra cost and moving parts. Rejected.
- **Adding more *required fields* to the manifest** — the agent just fills them
  with trivially-true content. Verifiable checks beat unverifiable required
  fields. Rejected.
