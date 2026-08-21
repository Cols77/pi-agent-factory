# Coherence Canonical Agentic I/O and Freshness Design

**Status:** design
**Date:** 2026-08-20
**Parent:** `2026-08-18-coherence-toolset-design.md`, decisions D11–D14 and §9.3

## 1. Problem

The factory sends agents several kinds of information, but each producer chooses its own
shape. RTK reduces shell text before it reaches an agent. `HarnessResult` carries simulation
metrics and trials. Evidence manifests carry Git and validation facts. The requirements
register, trace graph, plan ledger and code index expose durable state through unrelated APIs.
Consumers either learn every source or collapse it to prose and lose provenance.

Freshness is similarly fragmented. The repo already has generic dependency fingerprints, a
code index that rebuilds itself, evidence reconciliation with selected repairs, requirement
checksum checks, and a navigator catalogue of remediation commands. Each is locally useful,
but there is no shared declaration of dependencies, no compiled graph, no guarded read across
artifact kinds and no policy that decides which resolver may run automatically.

The tempting fix—put everything into one result schema—is wrong. A plan is an authoritative
artifact, a code map is a derived snapshot, and a test run is a time-bound observation. They
need common addressing, freshness and projection without pretending to share semantics.

## 2. Goals

1. Give agents one deterministic way to receive compact views of code, plans, requirements,
   Git state, tests, simulations, experiments and evidence.
2. Preserve enough provenance for gates and audits to reproduce or reject a claim.
3. Reuse existing authoritative artifacts, parsers, indexes, fingerprints and repair paths.
4. Detect stale artifact use at the read boundary instead of relying on every consumer to
   remember a bespoke check.
5. Resolve stale derived state automatically when safe, while never silently rewriting intent
   or inventing absent evidence.
6. Let each Coherence increment migrate its own producers; no flag-day rewrite.

### Non-goals

- No generic event bus, telemetry warehouse, background daemon or new database.
- No replacement for Markdown specs/plans/tasks/requirements or existing evidence artifacts.
- No claim that all domain payloads have the same fields.
- No hard dependency on RTK. Evidence capture must work when RTK is absent.
- No automatic authorship of specs, plans, requirements, deferrals or historical evidence.
- No transfer of gate execution out of the orchestrator. Recipes describe freshness and
  authority; owner packages still execute their own rebuilds or reruns.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| AIO-1 | Use two primitives: artifact/snapshot refs and observation envelopes | Durable state and time-bound claims have different validity rules. |
| AIO-2 | Common fields cover identity, provenance, routing and freshness only | Domain facts remain meaningful instead of becoming generic text. |
| AIO-3 | Projections are pure deterministic functions over validated inputs | Token savings are reproducible and cannot mutate evidence. |
| AIO-4 | Raw or domain-native output is retained by content hash when audit needs it | Compact output may truncate or redact. |
| AIO-5 | Extend `substrate.freshness`; do not create a parallel engine | Fingerprints and multiple local resolvers already exist. |
| AIO-6 | Compile declarative recipes and classify resolver authority | Detection can be universal while resolution remains safe. |
| AIO-7 | Migration follows ownership | Each subsystem adapts its producers when it moves. |

## 4. Artifact and observation contracts

### 4.1 Artifact and snapshot references

`ArtifactRef` addresses authoritative content without copying it:

```json
{
  "schema": 1,
  "kind": "spec",
  "ref": "spec:2026-08-20-coherence-agentic-io-design.md",
  "location": "docs/superpowers/specs/2026-08-20-coherence-agentic-io-design.md",
  "content_hash": "sha256:…",
  "scope_refs": ["feat:FEAT-…"],
  "media_type": "text/markdown"
}
```

`SnapshotRef` identifies derived state from one or more artifacts:

```json
{
  "schema": 1,
  "kind": "code-map",
  "ref": "snapshot:code-map:<fingerprint>",
  "fingerprint": "<source-set fingerprint>",
  "producer": {"name": "substrate.codemap", "version": 1, "engine": "tree-sitter"},
  "inputs": [{"ref": "git:<commit>", "content_hash": "sha256:…"}],
  "generated_at": "<ISO-8601>"
}
```

A stale snapshot remains addressable for history but is never rendered as current.

### 4.2 Observation envelope

`ObservationEnvelope` wraps a time-bound result:

```json
{
  "schema": 1,
  "id": "obs:<producer>:<stable-id>",
  "kind": "test-run",
  "producer": {"name": "pytest-adapter", "version": 1},
  "observed_at": "<ISO-8601>",
  "scope_refs": ["sr:SR-032", "task:T-067"],
  "inputs": [{"ref": "git:<commit>"}, {"ref": "artifact:requirements/SR-032.md"}],
  "outcome": "pass|fail|invalid|interrupted|unknown",
  "facts": {"schema": "test-run/v1", "passed": 41, "failed": 1},
  "diagnostics": [{"code": "ASSERTION_FAILED", "summary": "…"}],
  "artifacts": [{"ref": "artifact:evidence/…/pytest.json", "content_hash": "sha256:…"}]
}
```

The envelope does not prescribe `facts`; the named payload schema does. Both levels must
validate before an observation may satisfy a gate.

### 4.3 Projections

`substrate.projections` provides:

- `machine`: complete validated JSON for tools and gates;
- `human`: explanatory output with commands and artifact locations;
- `agent_compact`: deterministic, token-budgeted output containing outcome, material facts,
  diagnostics, scope refs and retrieval pointers.

Every projection carries its source id, schema and freshness plus `truncated` and `redacted`
flags. A projection cannot change outcome, validity or the existence of diagnostics.

## 5. Freshness compiler and resolver

### 5.1 Existing implementation reused

The design promotes existing pieces into shared contracts:

- `factory.freshness.fingerprint` already fingerprints files, values, tool versions and Git
  trees.
- `factory.codeindex.store.ensure_fresh` already performs a guarded read and deterministic
  rebuild when source or parser engine changes.
- `factory.evidence.reconcile` already compares manifest dependencies and repairs only cases
  with explicit provenance, including disposable indexes and publication retries.
- `factory.requirements` already detects stale binding checksums and exposes explicit bind or
  reaffirm writers.
- `factory.system.remediation` already maps gap states to commands but intentionally never
  runs them.

There is therefore no new fingerprint algorithm and no generic “repair everything” command.
The missing piece is a common declaration, compilation and dispatch boundary.

### 5.2 Freshness recipe

Each derived artifact or observation kind declares:

```json
{
  "schema": 1,
  "output_kind": "code-map",
  "inputs": ["project-profile", "source-set", "parser-engine"],
  "fingerprinter": "codemap/v1",
  "resolver": "codemap.ensure-fresh/v1",
  "resolution_class": "derived_auto",
  "limits": {"attempts": 1, "timeout_s": 30}
}
```

Compilation resolves input selectors, validates that every resolver exists, rejects duplicate
output ownership and cycles, and builds the dependency graph used by guarded reads and status
sweeps. Recipes are declarations; owner packages provide the implementations.

### 5.3 Guarded read and resolution

1. Resolve the requested ref and its compiled recipe.
2. Recompute dependency fingerprints.
3. Return the current object when fingerprints match.
4. On mismatch, emit a `stale` observation naming expected and actual inputs.
5. Dispatch only a resolver permitted by the active policy.
6. Revalidate the replacement and record `supersedes` lineage.
7. If resolution is forbidden or fails, return a typed blocker and route it to status/inbox.

Resolution is attempted once per recipe/input fingerprint per run. A resolver cannot trigger
itself through its own output, and compilation rejects dependency cycles.

### 5.4 Resolution classes

| Class | Examples | Behaviour |
|---|---|---|
| `derived_auto` | code index, trace/index snapshot, requirement index, compact projection | Rebuild automatically; deterministic and disposable. |
| `repeatable_policy` | tests, simulations, audits, validation | Rerun only inside configured time, cost and side-effect limits. |
| `authoritative_gate` | spec, plan, requirement, binding, deferral | Detect and route to the owning writer/human gate; never auto-rewrite. |
| `provenance_blocked` | missing historical manifest, unattributed changes | Report a blocker; no resolver may invent evidence. |

## 6. Code navigation and planning artifacts

### 6.1 Code navigation

The durable code index remains the source of symbols and future import edges. Its hash-keyed
index becomes a `SnapshotRef`; file/symbol results carry stable refs and line locations.
`render_index_slice` becomes an agent projection over a guarded snapshot. Its current
`ensure_fresh` path is the first `derived_auto` resolver, adapted rather than rewritten.

Tree-sitter fallback, deterministic fingerprints, stale-index rejection, token caps and direct
source-line navigation all remain.

### 6.2 Specs, plans, tasks and requirements

Markdown remains authoritative. `substrate.ledger`, `coherence.trace` and
`coherence.register` parse it into snapshots whose inputs are content-hashed `ArtifactRef`s.
Nodes and edges include `specifies`, `source_plan`, `satisfies`, `contains`, `binds` and
`demonstrates`.

Structural staleness—changed hashes, dangling refs or stale bindings—is detected
automatically. Semantic repair is `authoritative_gate`: the system can identify the owning
doctor/trace/register command, but it cannot rewrite intent. Agent projections can answer
“what plan governs this task?” and “what changed since approval?” without embedding every
document.

## 7. Domain mapping

| Source | Primitive | Freshness/resolution |
|---|---|---|
| Shell command | observation | never reused as current unless inputs are declared; raw log retained |
| Unit/sim/integration/full gate | observation | `repeatable_policy` |
| Simulation/experiment | observation | `repeatable_policy`; seeds, metrics and artifact refs preserved |
| Git working state | observation | recompute cheaply; never auto-modify the worktree |
| Evidence manifest/reconciliation | artifact + observation | existing explicit-provenance repairs; missing evidence blocked |
| Requirement closure/check | snapshot + observation | index rebuild automatic; binding/statement decisions gated |
| Code map | snapshot | `derived_auto` through existing `ensure_fresh` |
| Spec/plan/task/course | artifact + snapshot | parse/index automatic; authored content gated |

## 8. Safety and error handling

- Raw output is scanned for configured secrets before persistence; redaction is recorded.
- Binary or oversized output is referenced rather than injected into prompts.
- Unknown payload schemas are invalid and cannot satisfy a gate.
- Interrupted producers retain partial refs and never become pass/fail by inference.
- Resolver failure preserves the stale object for history and returns a typed blocker.
- Automatic resolvers may write only declared disposable outputs.
- Policy-controlled reruns expose predicted cost and timeout before dispatch.
- Authoritative and provenance-blocked classes have no automatic write capability.

## 9. Migration

1. Coherence increment 0 lands unchanged: distinguish and repair missing evidence.
2. Increment 1 moves existing fingerprints, defines contracts/recipes, compiles the graph and
   adapts code-index `ensure_fresh` as the first automatic resolver.
3. Existing evidence reconciliation repairs register as owner-provided resolvers.
4. Gate/test, measurement, Git/evidence and requirement-check adapters prove the observation
   contract.
5. Codemap and ledger expose snapshot refs without changing their stores or parsers.
6. Status, inbox, audit and navigation consume guarded refs as their increments land.
7. Legacy prose/JSON paths remain compatibility inputs for one release.

## 10. Testing and acceptance

- Contract fixtures cover each reference/envelope version.
- Every adapter has a golden domain input and expected machine envelope.
- Projection tests prove deterministic ordering, redaction and budget handling.
- Projections cannot change outcome or hide invalidity.
- Recipe compilation rejects cycles, duplicate outputs and unknown resolvers.
- Guarded reads distinguish missing, empty, stale, interrupted and invalid states.
- A stale code map rebuilds through the adapted existing resolver and records lineage.
- A stale test result reruns only when policy permits.
- A stale plan or requirement routes to its owning writer without changing the file.
- Missing historical evidence remains blocked.
- An agent can traverse task → plan → spec → requirement and file → symbol/import edge through
  stable refs without reparsing prose.

## 11. Impact on the parent Coherence design

The amendment changes the substrate boundary and the internal inputs to status, navigation,
audit, measurement and the long-run surface. It does not remove or redefine any original
Coherence capability. The parent spec's §15 records the preservation map against baseline
commit `1e31544` and the corrected TN-01 working-tree amendment.
