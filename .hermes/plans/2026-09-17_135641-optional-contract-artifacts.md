# Optional Contract Artifacts and Compilation Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Make Coherence optionally model declared contract artifacts as first-class trace, bundle, and freshness inputs, including deterministic local JSON Schema reference-closure compilation.

**Architecture:** Add one explicit, schema-validated project catalog under `.factory/`; compile it into an in-memory `ContractClosure` containing declared artifact identities, safe repository-relative paths, typed relationships, and transitive fingerprints. Extend existing trace, bundle, health, and freshness surfaces to consume that model. Projects without the catalog retain current behavior.

**Tech Stack:** Python 3.11, existing `jsonschema` validation helpers, `pathlib`, existing `factory.freshness` dependency/fingerprint machinery, existing `coherence trace` and `coherence navigate` command groups.

**Plan baseline:** `04c8833e190f852c18a6e77d54654633b21bf9e2` on branch `docs/optional-contract-artifacts-plan`.

---

## Decision record

### Why contract compilation belongs in the suite

SENTINEL’s schemas, fixtures, DDL manifest, and Python validators are critical interfaces. Today a prose-spec/plan trace can be healthy while a local JSON Schema `$ref` target, fixture relationship, or declared validator has drifted. A deterministic compiler gives the native tooling one reusable representation of that closure rather than creating a SENTINEL-only manifest checker.

### Scope of “compile” in the first increment

`compile` means **parse, validate, normalize, resolve safe local relationships, and hash**. It does **not** mean code generation, arbitrary protocol semantics, network retrieval, shelling out to validators, or creating a second authoritative artifact. The compiler is read-only and in-memory in the first increment.

An optional materialized lock/closure file may be considered only after the in-memory compiler and consumers have a demonstrated performance or review-use case. It is not part of this increment.

### Command-surface decision

Do not add a new top-level CLI group. Contract diagnostics surface through existing `trace check`, `navigate health`, `navigate freshness`, bundle/membership checks, and JSON status projections. A narrowly scoped `coherence navigate contracts` read-only view may be added only if existing explain/status output cannot expose catalog entries and compiler diagnostics clearly; it must be a thin formatter over the same compiler.

### Required human decision before implementation

The Coherence requirement register needs a small feature allocation and semantic SRs for this new behavior. Before authoring them, present the exact source anchors and acceptance criteria for human consent. Do not auto-author or auto-accept SR semantics merely because this plan exists.

## Compatibility contract

- Absence of `.factory/contracts.yaml` is valid and produces no contract-specific findings.
- Presence of a catalog makes every declared entry authoritative and fail-closed: malformed declarations, duplicate IDs/paths, unresolved relationships, unsafe paths, and missing files are visible findings.
- Only local repository-relative paths and local `$ref` values are supported initially. Absolute paths, parent traversal, URLs, and symlink/reparse-point escapes are rejected before resolution.
- No generic scan of JSON files is allowed. A project opts in by listing exact artifacts.
- Existing bundle member kinds and JSON outputs remain backward-compatible; `contract:<id>` is additive.
- Existing freshness fingerprint formats are reused. This plan must not create a parallel hashing, dependency-graph, or evidence subsystem.

## Proposed catalog model

Create `.factory/contracts.yaml`, validated against a new substrate JSON Schema. The authored catalog is the inventory; each contract file remains authoritative for its own semantics.

```yaml
schema: coherence.contract-catalog.v1
contracts:
  - id: SENTINEL-V0-WIRE
    path: docs/superpowers/specs/contracts/sentinel-v0-wire.schema.json
    kind: json_schema
    authority: spec:SPEC-SENTINEL-WP0
    consumers:
      - code:src/sentinel/contracts/schemas.py
      - test:tests/contracts/test_schema_validation.py
    status: active
  - id: SENTINEL-V0-MOUNTAIN-FIXTURE
    path: docs/superpowers/specs/contracts/mountain-v0.fixture.json
    kind: fixture
    validates_against: contract:SENTINEL-V0-MOUNTAIN-SCHEMA
    status: active
```

Initial `kind` values: `json_schema`, `fixture`, `template`, `ddl_manifest`, `protocol`, and `other`. The compiler owns path and graph mechanics, not project-specific semantic validation. Existing test gates validate semantics.

## Task 1: Freeze the feature boundary and add consent-gated requirements

**Objective:** Establish an implementation feature and the few requirement anchors needed to make the tooling change traceable without creating a broad new governance system.

**Files:**
- Create after consent: `requirements/SR-*.md`, `docs/features/FEAT-*.md`, `bundles/FEAT-*.json`
- Modify: `requirements/index.json` only through the native producer
- Reference: `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md`
- Reference: `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`

**Step 1:** Present four proposed, independently consentable SR themes: opt-in catalog compatibility; lexical path safety; deterministic local contract closure; trace/bundle/freshness observability.

**Step 2:** After consent, author only the accepted SRs with exact design source anchors and acceptance criteria. Create one FEAT dossier and one bundle that cover those SRs and the implementation/test artifacts.

**Step 3:** Run `uv run coherence register index --project-root .` and `uv run coherence register check --project-root .`.

**Expected:** The feature is traceable, while no unrelated requirements or historical plans are changed.

## Task 2: Define the catalog schema and pure model

**Objective:** Create a bounded, versioned input model without coupling it to CLI or project-specific code.

**Files:**
- Create: `src/substrate/schemas/contract_catalog.schema.json`
- Create: `src/coherence/contracts/model.py`
- Test: `tests/unit/coherence/contracts/test_model.py`

**Step 1: Write failing tests** for a minimal valid catalog; absent-catalog compatibility; unsupported `kind`; duplicate raw IDs; duplicate normalized repository paths; absent/empty IDs; and malformed relationship refs.

**Step 2:** Add frozen dataclasses such as `ContractDeclaration`, `ContractRelation`, `ContractDiagnostic`, and `ContractClosure`. Keep them serializable through explicit `to_dict()` methods rather than leaking `Path` objects into command projections.

**Step 3:** Implement JSON Schema validation through the existing substrate validation facilities. Require explicit `schema: coherence.contract-catalog.v1` and reject unknown top-level fields unless there is a documented compatibility reason.

**Step 4:** Run `uv run python -m pytest tests/unit/coherence/contracts/test_model.py -q`.

**Expected:** Parsing is deterministic and has no filesystem traversal beyond catalog parsing.

## Task 3: Implement lexical path safety and catalog loading

**Objective:** Load catalog entries without allowing a declaration to escape the project root.

**Files:**
- Create: `src/coherence/contracts/catalog.py`
- Modify: `src/coherence/contracts/model.py`
- Test: `tests/unit/coherence/contracts/test_catalog.py`

**Step 1: Write failing tests** for absolute Windows/POSIX paths, `..` components, current-drive rooted paths, missing declared files, symlink/reparse-point escape, duplicate canonical paths, and a project with no catalog.

**Step 2:** Implement path validation before canonicalization: reject rooted forms and lexical parent components first; then verify every resolved component remains under the resolved repository root. Do not let a target that happens to resolve in-tree compensate for unsafe input syntax.

**Step 3:** Make `load_contract_catalog(root)` return an explicit empty closure state when the file is absent, and structured diagnostics when the opt-in file is present but invalid.

**Step 4:** Run `uv run python -m pytest tests/unit/coherence/contracts/test_catalog.py -q`.

**Expected:** Catalog discovery is safe, opt-in, and fail-closed once enabled.

## Task 4: Add deterministic contract compilation

**Objective:** Compile declared artifacts into a normalized dependency closure and per-node fingerprint inputs.

**Files:**
- Create: `src/coherence/contracts/compiler.py`
- Modify: `src/coherence/contracts/model.py`
- Test: `tests/unit/coherence/contracts/test_compiler.py`

**Step 1: Write failing tests** for stable ordering across filesystem order; declared `validates_against`; declared `consumers`; local JSON Schema `$ref`; missing `$ref`; cycles; duplicate URI/path aliases; and non-JSON artifacts that receive only their own content hash.

**Step 2:** For `json_schema`, parse JSON and traverse only local `$ref` values. Reject network URLs and non-file URI schemes. Normalize local references to catalog-declared or in-repository files and record source-to-target edges.

**Step 3:** Compute a stable content fingerprint from each artifact plus its ordered local dependency closure. Use the existing freshness hashing conventions where available; do not introduce a second content-hash algorithm.

**Step 4:** Keep semantic schema validation out of the compiler. The compiler reports syntax and reference closure; project gates and declared consumer tests remain responsible for domain semantics.

**Step 5:** Run `uv run python -m pytest tests/unit/coherence/contracts/test_compiler.py -q`.

**Expected:** A change to a referenced wire schema invalidates a root contract’s compiled fingerprint, even if the root file did not change.

## Task 5: Add contract nodes and typed edges to trace

**Objective:** Make contracts inspectable in the existing graph and ensure broken declarations produce explainable findings.

**Files:**
- Modify: `src/coherence/trace/model.py`
- Modify: `src/coherence/trace/graph.py`
- Modify: `src/coherence/trace/gaps.py`
- Modify: `src/coherence/trace/explainers.py`
- Test: `tests/unit/coherence/trace/test_contract_nodes.py`
- Test: `tests/unit/coherence/trace/test_contract_gaps.py`

**Step 1: Write failing tests** that assert `contract:<id>` nodes are absent without a catalog; appear with a valid catalog; connect through `defines`, `consumed_by`, `validated_by`, `validates_against`, and `references` edges; and preserve deterministic edge ordering.

**Step 2:** Extend `NodeKind` and node discovery through the compiler output rather than JSON globbing. Add contract-specific findings for missing provenance, broken reference, missing consumer, stale consumer, stale fixture, and unavailable validation.

**Step 3:** Make diagnostics cite the catalog declaration and the exact artifact path. Never report a contract as “covered” merely because its file exists.

**Step 4:** Run `uv run python -m pytest tests/unit/coherence/trace/test_contract_nodes.py tests/unit/coherence/trace/test_contract_gaps.py -q` and `uv run coherence trace check --project-root .`.

**Expected:** Native trace output explains contract relationships without a separate SENTINEL checker.

## Task 6: Permit contracts in feature bundles and coverage

**Objective:** Include contract artifacts in feature scope/membership without changing the role of the contract catalog.

**Files:**
- Modify: `src/coherence/navigate/bundles.py`
- Modify: `src/substrate/schemas/system_bundle.schema.json` only if it restricts member-ref formats
- Modify: `src/coherence/navigate/coverage.py`
- Test: `tests/unit/coherence/navigate/test_bundles.py`
- Test: `tests/unit/coherence/navigate/test_contract_coverage.py`

**Step 1: Write failing tests** for `contract:<id>` member parsing; unresolved contract IDs; a valid bundle whose contract is cataloged; and a project with no catalog whose existing bundles remain valid.

**Step 2:** Add `contract` to the existing member-kind parser and resolve it through the same compiled catalog used by trace. Do not copy catalog parsing into bundle loading.

**Step 3:** Extend coverage output and health dimensions so a declared contract can be reported as bundled, unbundled, missing, or invalid without changing existing scope-ref semantics.

**Step 4:** Run the targeted bundle/coverage tests plus `uv run coherence navigate membership --gate --repo-root .`.

**Expected:** Bundles describe feature membership; the catalog remains the artifact authority.

## Task 7: Reuse freshness dependency and evidence machinery

**Objective:** Propagate contract closure changes to declared consumers and evidence using the existing freshness engine.

**Files:**
- Modify: `src/factory/freshness/deps.py`
- Modify: `src/factory/freshness/policy.py` only if the current policy cannot classify contract invalidation
- Modify: `src/coherence/navigate/health.py`
- Modify: `src/coherence/navigate/snapshots.py` only for documented snapshot/projection changes
- Test: `tests/unit/factory/freshness/test_contract_dependencies.py`
- Test: `tests/unit/coherence/navigate/test_contract_freshness.py`

**Step 1: Write failing tests** for a changed root contract, a changed transitive `$ref`, a changed fixture, a consumer with stale recorded evidence, and missing provenance. Include a no-catalog regression proving no new invalidation occurs.

**Step 2:** Materialize compiler relationships as normal freshness dependency edges (`contract`, `code`, `test`, and evidence refs as supported by the existing model). Reuse `compute_impact()` and existing reconciliation policy; do not fork its graph or its evidence record format.

**Step 3:** Add stable finding codes and JSON fields for `CONTRACT_REFERENCE_BROKEN`, `CONTRACT_MISSING_PROVENANCE`, `CONTRACT_STALE`, `CONTRACT_CONSUMER_STALE`, `CONTRACT_FIXTURE_STALE`, and `CONTRACT_VALIDATION_UNAVAILABLE`.

**Step 4:** Run `uv run python -m pytest tests/unit/factory/freshness/test_contract_dependencies.py tests/unit/coherence/navigate/test_contract_freshness.py -q` and `uv run coherence navigate freshness --repo-root . --json`.

**Expected:** Freshness is non-vacuous only for declared relationships and points to the invalidated consumer/evidence chain.

## Task 8: Expose concise native diagnostics and documentation

**Objective:** Make the feature usable through existing automation and explain its boundaries.

**Files:**
- Modify: `src/coherence/trace/cli.py` and/or the existing CLI projection owners only as required by accepted diagnostics
- Modify: `src/coherence/navigate/cli.py`
- Modify: `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md`
- Modify: `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`
- Create: `docs/contract-artifacts.md`
- Test: CLI tests under the existing `tests/unit/coherence/` command-owner directory

**Step 1:** Add JSON and human-readable examples for catalog absent, valid catalog, malformed catalog, broken `$ref`, and stale consumer/evidence.

**Step 2:** Document the strict local-only model, catalog ownership, compiler boundary, relationship vocabulary, bundle behavior, and how a consumer project records validation evidence.

**Step 3:** Add CLI tests that assert stable machine-readable codes and deterministic sorted output; do not test only prose strings.

**Step 4:** Run the command-owner test targets and `uv run coherence status --project-root . --json`.

**Expected:** Existing automation gets contract state without a new heavyweight suite or host-specific adapter.

## Task 9: Add an end-to-end fixture project and acceptance verification

**Objective:** Demonstrate a real consumer-style contract closure independently from SENTINEL’s evolving worktree.

**Files:**
- Create: `tests/fixtures/contract_catalog_project/` with a minimal catalog, root schema, referenced schema, fixture, consumer, test/evidence declarations, and intentionally invalid variants
- Create or modify: focused end-to-end tests under `tests/unit/coherence/`

**Step 1:** Build one valid fixture and independent invalid fixtures for unsafe paths, a missing `$ref`, and a changed transitive dependency.

**Step 2:** Assert the complete machine-readable sequence: compile → trace nodes/edges → bundle coverage → freshness invalidation → health finding.

**Step 3:** Run, in order:

```bash
uv run python -m pytest tests/unit/coherence/contracts tests/unit/coherence/trace tests/unit/coherence/navigate tests/unit/factory/freshness -q
uv run coherence trace check --project-root .
uv run coherence navigate health --repo-root . --json
uv run coherence navigate freshness --repo-root . --json
```

**Step 4:** Run the repository’s designated unit campaign from a fresh process before claiming the implementation is verified. Preserve the exact command, revision SHA, and output artifact.

## Non-goals and deferred decisions

- Do not infer contracts from all JSON/YAML/TOML files.
- Do not fetch remote schemas or resolve HTTP(S) `$ref` values.
- Do not execute external schema compilers, code generators, or provider tools.
- Do not invent a generic protocol compiler or semantic validator framework.
- Do not add a materialized lock/closure file until an evidence-backed need exists.
- Do not declare a consumer contract “validated” based solely on the compiler. Validation remains an executed gate/evidence assertion.
- Do not alter existing projects without a catalog.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Path traversal or Windows reparse-point escape | Reject unsafe lexical paths before resolution; test symlink/reparse behavior explicitly. |
| Catalog becomes a stale duplicate of contract semantics | Catalog contains identity, relationships, and status only—not schema content or semantic rules. |
| Staleness results become noisy | Require explicit declarations and evidence links; classify missing provenance separately from stale evidence. |
| Generic compiler scope expands uncontrollably | Keep first release to local JSON Schema `$ref` closure plus generic file hashes; defer more formats. |
| CLI proliferation | Extend fixed existing command groups; add a subview only if indispensable. |

## Handoff to SENTINEL

The linked SENTINEL plan is blocked until Tasks 2–7 expose a released/landed Coherence version with catalog, bundle, trace, and freshness support. SENTINEL may prepare its authority document and candidate SR wording in parallel, but must not fake contract freshness evidence or rely on unimplemented `contract:` bundle references.
