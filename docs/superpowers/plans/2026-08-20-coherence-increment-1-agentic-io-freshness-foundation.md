# Coherence Increment 1: Agentic I/O and Freshness Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the smallest reusable substrate for content-addressed artifacts, derived snapshots, validated observations, deterministic projections, and authority-aware freshness resolution; prove it with the existing code index as the first automatic resolver.

**Architecture:** Create an acyclic substrate package that owns neutral contracts and imports neither factory nor coherence. Move the existing freshness primitives into substrate.freshness with one-release factory.freshness deprecation shims, then layer recipe compilation and guarded reads over them without replacing their hashing or report semantics. Existing factory.codeindex remains its owner for this increment, but exposes an adapter conforming to the new resolver protocol and returns a SnapshotRef with supersession lineage. Domain adapters for tests, simulations, Git, evidence, requirements, plans, navigation import edges, and KB failure signatures remain follow-on increments.

**Tech Stack:** Python 3.11+, dataclasses/enums/protocols, JSON-compatible mappings, hashlib/pathlib, existing factory freshness and code-index implementation, pytest, Ruff, Pyright.

## Execution Coordination

- Prerequisite: Increment 0 is merged and its evidence semantics are stable.
- Tasks 2 artifact/snapshot contracts and 3 observation/projection contracts are parallel after Task 1 establishes the substrate package/import-shim convention.
- Freshness recipe/guard work is serial after Task 1 because it relocates the existing primitives; the codemap resolver adapter is serial after the guard contract.
- Increment 1B waits for this plan; do not begin broad substrate moves against an unstable ArtifactRef, ObservationEnvelope, or resolver interface.

## Scope and Authority Boundaries

- This is an interface foundation, not a giant event store and not an RTK-style raw-text capture replacement.
- Raw producer output stays with the owning domain adapter/evidence store. ArtifactRef only addresses it; projections are views and cannot become evidence.
- A SnapshotRef is derived and may be automatically rebuilt. A stale snapshot remains historical and must never be returned as current.
- ObservationEnvelope validates its wrapper plus a named facts schema before it is gate-eligible; unknown or invalid facts never become pass.
- Automatic resolution is limited to derived_auto. Tests/simulations, authored documents/requirements, and missing provenance have different authority classes and no automatic write path in this increment.
- Do not move validation document helpers, ledger, backend, skills, or KB in this plan. Their present dependency edges point back into factory and need an ownership/inversion design before a safe extraction.
- Do not add transitive-import analysis (TN-13) or KB error-signature wiring (TN-14) here. Preserve factory.coverage.imports behavior.

## File Structure

**Create:**

- src/substrate/__init__.py
- src/substrate/artifacts.py
- src/substrate/observations.py
- src/substrate/projections.py
- src/substrate/freshness/__init__.py
- src/substrate/freshness/model.py
- src/substrate/freshness/fingerprint.py
- src/substrate/freshness/evaluate.py
- src/substrate/freshness/recipes.py
- src/substrate/freshness/guard.py
- src/factory/codeindex/substrate.py
- tests/unit/substrate/test_artifacts.py
- tests/unit/substrate/test_observations.py
- tests/unit/substrate/test_projections.py
- tests/unit/substrate/test_freshness_recipes.py
- tests/unit/substrate/test_freshness_guard.py
- tests/unit/substrate/test_compatibility_shims.py

**Modify:**

- src/factory/freshness/model.py
- src/factory/freshness/fingerprint.py
- src/factory/freshness/evaluate.py
- tests/unit/freshness/test_freshness.py
- tests/unit/codeindex/test_codeindex.py

## Task 1: Establish substrate and retain backwards-compatible freshness imports

**Files:**

- Create: src/substrate/__init__.py
- Create: src/substrate/freshness/__init__.py
- Create: src/substrate/freshness/model.py
- Create: src/substrate/freshness/fingerprint.py
- Create: src/substrate/freshness/evaluate.py
- Create: tests/unit/substrate/test_compatibility_shims.py
- Modify: src/factory/freshness/model.py
- Modify: src/factory/freshness/fingerprint.py
- Modify: src/factory/freshness/evaluate.py

- [ ] **Step 1: Map and freeze the existing freshness public surface.**

Before moving code, write a parametrised test importing both substrate.freshness and each former factory.freshness module. Assert the canonical exports preserve identity/behaviour for:

    factory.freshness.model: DependencyFingerprint, FreshnessSeverity,
      FreshnessIssue, FreshnessReport, GATE_FAILING_SEVERITIES
    factory.freshness.fingerprint: sha256_bytes, fingerprint_file,
      fingerprint_value, fingerprint_tool, fingerprint_git_tree
    factory.freshness.evaluate: compare_dependencies

For each old import, catch warnings and assert exactly one DeprecationWarning says to import the corresponding substrate path. Also assert a substrate import emits no deprecation warning and that no substrate.freshness module imports factory or coherence.

- [ ] **Step 2: Run tests and record the expected missing-package failure.**

Run: rtk proxy uv run python -m pytest tests/unit/substrate/test_compatibility_shims.py tests/unit/freshness/test_freshness.py -q

Expected: failure because substrate does not yet exist.

- [ ] **Step 3: Move implementation, do not fork it.**

Copy the current source logic verbatim into substrate/freshness/model.py, fingerprint.py, and evaluate.py, changing internal imports only to substrate.freshness. Preserve dependency fingerprint digests, FreshnessSeverity values, GATE_FAILING_SEVERITIES, FreshnessIssue/FreshnessReport serialization, and evaluation results exactly.

Replace each old factory.freshness module with a thin re-export shim:

    warnings.warn(
        "factory.freshness.<module> is deprecated; import substrate.freshness.<module>",
        DeprecationWarning,
        stacklevel=2,
    )
    from substrate.freshness.<module> import ...

Place the warning in each old module, not in substrate. Avoid a star import where it would obscure the legacy public surface; maintain an explicit __all__. Do not change factory.freshness/__init__.py: it has no public re-exports today. Old consumers must still work for one release.

- [ ] **Step 4: Run parity, compatibility, and static tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate/test_compatibility_shims.py tests/unit/freshness/test_freshness.py -q
    rtk proxy uv run ruff check src/substrate src/factory/freshness tests/unit/substrate tests/unit/freshness
    rtk proxy uv run pyright

Expected: passing tests, no fresh lint/type findings. Existing users see no warning by default; the test captures it explicitly.

- [ ] **Step 5: Commit the compatibility extraction.**

    git add src/substrate src/factory/freshness tests/unit/substrate/test_compatibility_shims.py
    git commit -m "refactor(substrate): extract freshness contracts"

## Task 2: Add immutable ArtifactRef and SnapshotRef contracts

**Files:**

- Create: src/substrate/artifacts.py
- Create: tests/unit/substrate/test_artifacts.py

- [ ] **Step 1: Write round-trip and rejection tests.**

Implement JSON-contract fixtures for the spec's ArtifactRef and SnapshotRef examples. Test:

1. from_dict/to_dict round-trips identically with stable tuple/list ordering.
2. ArtifactRef requires schema 1, nonblank kind/ref/location, content_hash prefixed sha256: with 64 lowercase hex digits, unique scope_refs, and an optional media_type.
3. SnapshotRef requires schema 1, nonblank kind/ref/fingerprint, a producer mapping with name/version, non-empty input references, and UTC generated_at.
4. A SnapshotRef may carry an optional supersedes reference, but it cannot equal ref.
5. Unknown fields, a duplicate scope/input ref, invalid hash/time, missing producer version, and an ArtifactRef supplied where a snapshot input only needs ref/content_hash are all rejected with field-specific errors.
6. The types validate/address data only: they neither read locations nor write/copy artifact contents.

- [ ] **Step 2: Run to prove the module is absent.**

Run: rtk proxy uv run python -m pytest tests/unit/substrate/test_artifacts.py -q

Expected: import failure for substrate.artifacts.

- [ ] **Step 3: Implement frozen model objects.**

Define frozen dataclasses ArtifactRef, SnapshotInputRef, ProducerRef, and SnapshotRef. Each exposes from_dict and to_dict; all validation is performed at construction/factory time, not deferred to consumers. Use a small internal validation helper rather than JSON Schema to keep these in-process contracts dependency-light. Serialize tuple fields as JSON lists and retain user-supplied stable ordering after rejecting duplicates.

The SnapshotRef input type intentionally contains only ref and optional content_hash, matching the design contract. A full ArtifactRef may be used by a caller to create that narrow input but no snapshot owns/copies the artifact.

- [ ] **Step 4: Run contract tests and package-wide checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate/test_artifacts.py -q
    rtk proxy uv run ruff check src/substrate tests/unit/substrate
    rtk proxy uv run pyright

Expected: pass.

- [ ] **Step 5: Commit.**

    git add src/substrate/artifacts.py tests/unit/substrate/test_artifacts.py
    git commit -m "feat(substrate): add artifact and snapshot references"

## Task 3: Validate time-bound observations and make projections non-authoritative

**Files:**

- Create: src/substrate/observations.py
- Create: src/substrate/projections.py
- Create: tests/unit/substrate/test_observations.py
- Create: tests/unit/substrate/test_projections.py

- [ ] **Step 1: Define failing envelope tests around a named payload registry.**

Create a tiny test-only facts validator for test-run/v1. Test that ObservationEnvelope accepts the example test-run result only when both its envelope and the registered facts schema validate. It must reject unknown facts schemas, a payload rejected by its registered validator, an unknown outcome, malformed diagnostics, invalid artifact refs, and invalid observed_at.

Assert invalid/unknown observations expose outcome invalid or unknown exactly as supplied and cannot be classified gate-eligible. The constructor must never silently turn a rejected payload into pass.

- [ ] **Step 2: Define failing deterministic projection tests.**

For the same valid and invalid envelopes, assert:

1. machine is the full validated JSON plus source_id/schema/freshness/truncated/redacted metadata;
2. human is deterministic, names outcome, diagnostics, source location/ref, and freshness;
3. agent_compact honors a specified character budget, stable-sorts facts/diagnostics/artifact pointers, and sets truncated true if it omits material text;
4. configured redaction replaces only declared sensitive values and sets redacted true;
5. all projections retain outcome and every diagnostic code; no projection makes invalid/unknown pass or hides the fact that it is invalid.

- [ ] **Step 3: Run and confirm initial import failures.**

Run: rtk proxy uv run python -m pytest tests/unit/substrate/test_observations.py tests/unit/substrate/test_projections.py -q

Expected: failure for missing modules.

- [ ] **Step 4: Implement strict envelope and pure renderers.**

In observations.py define:

    Outcome = Literal["pass", "fail", "invalid", "interrupted", "unknown"]
    FactsValidator = Callable[[Mapping[str, object]], None]
    PayloadRegistry
    ObservationEnvelope

The envelope has schema, id, kind, ProducerRef, observed_at, scope_refs, SnapshotInputRef inputs, outcome, facts, diagnostics, and ArtifactRef artifacts. facts requires a string schema key. Registry validation must be explicit at construction or validate_for_gate(); no global mutable registry may decide a past observation's interpretation.

In projections.py implement pure functions machine(envelope, freshness), human(envelope, freshness), and agent_compact(envelope, freshness, max_chars, redactions=()). Each returns a projection structure carrying source_id, schema, freshness, truncated, and redacted. The functions must not write files, call tools, modify the envelope, or decide a resolution policy.

- [ ] **Step 5: Run focused regression and static checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate/test_observations.py tests/unit/substrate/test_projections.py -q
    rtk proxy uv run ruff check src/substrate tests/unit/substrate
    rtk proxy uv run pyright

Expected: pass.

- [ ] **Step 6: Commit.**

    git add src/substrate/observations.py src/substrate/projections.py tests/unit/substrate/test_observations.py tests/unit/substrate/test_projections.py
    git commit -m "feat(substrate): validate observations and projections"

## Task 4: Compile freshness recipes and guard resolution by authority class

**Files:**

- Create: src/substrate/freshness/recipes.py
- Create: src/substrate/freshness/guard.py
- Create: tests/unit/substrate/test_freshness_recipes.py
- Create: tests/unit/substrate/test_freshness_guard.py

- [ ] **Step 1: Add compiler rejection tests.**

Write declaration fixtures around this shape:

    {
      "schema": 1,
      "output_kind": "code-map",
      "inputs": ["project-profile", "source-set", "parser-engine"],
      "fingerprinter": "codemap/v1",
      "resolver": "codemap.ensure-fresh/v1",
      "resolution_class": "derived_auto",
      "limits": {"attempts": 1, "timeout_s": 30}
    }

Assert compile_recipes rejects an unknown resolver, unsupported schema, duplicate output_kind ownership, duplicate input selectors, limits with attempts other than one, a cycle among output selectors, and an input that feeds its own resolver output. Assert it returns a deterministic topological order for valid declarations.

- [ ] **Step 2: Add guarded-read policy tests.**

Use fake deterministic fingerprinters/resolvers and a per-run GuardSession. Cover:

1. A current snapshot returns without resolver invocation.
2. A stale derived_auto snapshot calls its resolver exactly once for recipe plus input fingerprint, validates the replacement, and emits a stale observation plus SnapshotRef whose supersedes names the stale ref.
3. Re-reading the same stale key does not call again; it returns the prior typed failure/blocker or validated replacement.
4. repeatable_policy yields a typed policy blocker in this increment, even when a resolver is registered.
5. authoritative_gate and provenance_blocked never invoke a resolver and name the owning action/blocker.
6. A resolver that returns an invalid/re-stale snapshot is rejected and cannot be reported current.

- [ ] **Step 3: Run to establish absent modules.**

Run: rtk proxy uv run python -m pytest tests/unit/substrate/test_freshness_recipes.py tests/unit/substrate/test_freshness_guard.py -q

Expected: import failure.

- [ ] **Step 4: Implement recipes without reimplementing fingerprints.**

In recipes.py define ResolutionClass exactly as derived_auto, repeatable_policy, authoritative_gate, provenance_blocked; FreshnessLimits; FreshnessRecipe; Resolver protocol; ResolverRegistry; CompiledRecipes; and compile_recipes. The recipe compiler only validates/dependency-orders declarations and resolver names. It must not read project files, execute a resolver, or mutate the registry.

In guard.py define GuardSession, StalenessObservation, ResolutionBlocker, and guarded_read. It accepts a compiled recipe, current candidate, a caller-supplied input-fingerprint function, validator, and registry. It recomputes dependencies, compares them to the candidate, dispatches only derived_auto, records an at-most-once attempt key, validates a returned replacement, and records supersedes lineage. Reuse DependencyFingerprint and existing freshness comparison/evaluation utilities; do not introduce another hashing algorithm or severity enum.

- [ ] **Step 5: Run foundation tests plus existing freshness regressions.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate/test_freshness_recipes.py tests/unit/substrate/test_freshness_guard.py tests/unit/freshness/test_freshness.py -q
    rtk proxy uv run ruff check src/substrate tests/unit/substrate
    rtk proxy uv run pyright

Expected: pass.

- [ ] **Step 6: Commit.**

    git add src/substrate/freshness/recipes.py src/substrate/freshness/guard.py tests/unit/substrate/test_freshness_recipes.py tests/unit/substrate/test_freshness_guard.py
    git commit -m "feat(substrate): compile guarded freshness recipes"

## Task 5: Adapt the existing code map as the first derived_auto resolver

**Files:**

- Create: src/factory/codeindex/substrate.py
- Modify: tests/unit/codeindex/test_codeindex.py
- Create: tests/unit/substrate/test_codemap_resolver.py

- [ ] **Step 1: Preserve old code-index behavior with regression tests.**

Before wiring any recipe, run the existing tests proving ensure_fresh rebuilds after source content changes, rebuilds after a parser-engine upgrade, and reuses when engine/fingerprint match. Add a test that the legacy ensure_fresh public return remains CodeIndex; no caller is forced to understand SnapshotRef yet.

- [ ] **Step 2: Add a failing guarded adapter test.**

Create a repository with an initial persisted code index, then change a source file. Build a code-map FreshnessRecipe using codemap.ensure-fresh/v1 and register an adapter around ensure_fresh. Assert guarded_read:

1. sees the stale content/engine fingerprint;
2. calls the adapter once;
3. persists through existing store semantics;
4. returns a SnapshotRef with kind code-map, a stable fingerprint/ref, producer name/version/engine, input refs, and supersedes pointing to the prior snapshot;
5. revalidates that the new snapshot matches current source/engine fingerprints.

Include a no-files case so it returns a valid no-files snapshot and does not claim an old map current.

- [ ] **Step 3: Implement the adapter beside the current owner.**

Keep ensure_fresh as the single code-index build/read implementation. Add a narrow factory.codeindex.substrate adapter that:

- creates a current candidate SnapshotRef from load_latest when possible;
- calculates inputs from the same source-set fingerprint and parser engine conditions already used by ensure_fresh;
- invokes ensure_fresh only when the substrate guard authorises derived_auto;
- converts the resulting CodeIndex to SnapshotRef without copying index content;
- persists no new data beyond the existing .factory/code-index files;
- never imports factory from substrate; factory supplies the resolver registration at the composition boundary.

Do not alter tree-sitter fallback, source discovery, token caps, render_index_slice, or coverage/imports.py.

- [ ] **Step 4: Run adapter, code-index, and substrate regressions.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate/test_codemap_resolver.py tests/unit/codeindex/test_codeindex.py tests/unit/substrate -q
    rtk proxy uv run ruff check src/factory/codeindex src/substrate tests/unit/codeindex tests/unit/substrate
    rtk proxy uv run pyright

Expected: pass. The adapter test proves automatic staleness resolution is bounded and lineage-preserving; existing tests prove code navigation behavior was retained.

- [ ] **Step 5: Commit.**

    git add src/factory/codeindex/substrate.py src/substrate tests/unit/codeindex/test_codeindex.py tests/unit/substrate/test_codemap_resolver.py
    git commit -m "feat(codemap): resolve stale indexes through substrate"

## Final Verification and Handoff Boundary

- [ ] **Step 1: Run all affected unit tests and static checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate tests/unit/freshness tests/unit/codeindex -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright
    rtk git diff --check HEAD~5..HEAD

Expected: all test/static checks pass and no whitespace errors.

- [ ] **Step 2: Validate the authority matrix with direct test names.**

Record in the implementation handoff that:

- derived_auto: the code-map adapter rebuilt exactly once;
- repeatable_policy: was blocked, not run;
- authoritative_gate: was routed, not rewritten;
- provenance_blocked: was reported, not repaired.

- [ ] **Step 3: Stop before broad relocation or new producer adapters.**

Create no compatibility shims for document validators, ledger, pi backend/skills, KB, requirements, trace, evidence, tests, simulations, Git, or planning artifacts in this increment. The next planning slice must first resolve their current imports from factory.validation, factory.orchestrator roles/types, and current runner signature sources. It will then add domain adapters on top of the stable contracts built here.

## Plan Self-review

- This lands the new design's reusable contracts and the first safe staleness resolver without changing original coherence increment ownership or pretending raw terminal output is evidence.
- Code navigation is covered concretely through the existing code index and SnapshotRef; planning/spec/requirement artifacts are intentionally contract-ready but not auto-mutated.
- The plan preserves existing fingerprints, code-index persistence and fallbacks, evidence provenance boundaries, and coverage import analysis.
- Broad substrate extraction is deliberately deferred because current document validation and orchestrator modules still import factory-owned dependencies. Moving them mechanically would create the dependency inversion the architecture is intended to eliminate.

## Review Amendments

Task 2 is a prerequisite for Task 3: ProducerRef and SnapshotInputRef are defined in artifacts.py before ObservationEnvelope imports them. A payload that fails its named validator is retained as RejectedObservation(id, kind, producer, observed_at, outcome="invalid", diagnostics, raw_artifacts), which is renderable only with explicit invalid metadata and is never gate-eligible. A valid ObservationEnvelope with outcome invalid is also gate-ineligible but remains projectable; no rejected/invalid value is converted to pass.

FreshnessRecipe compilation owns both registries. Add Fingerprinter protocol, FingerprinterRegistry, and compile-time rejection for an unknown fingerprinter; guarded_read obtains its dependency function from compiled.fingerprinters[recipe.fingerprinter], not a caller-supplied substitute. The artifacts/observations streams may prepare tests in parallel, but production Task 3 begins only after Task 2.
