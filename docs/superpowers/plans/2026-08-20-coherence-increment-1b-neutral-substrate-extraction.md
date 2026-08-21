# Coherence Increment 1B: Neutral Substrate Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the remaining neutral shared models into substrate without allowing a substrate import of factory or coherence, while preserving the current factory APIs for one release.

**Architecture:** Move pure paths, schemas, schema validation, task/plan parsing, declarative gate configuration, agent result primitives, skill loading, and evidence manifest reading to substrate. Where a current module combines neutral parsing with factory execution composition, split it: substrate owns the pure part and factory remains an explicit compatibility/composition adapter. Every old path warns and re-exports; write-side evidence, connector registries, role catalogues, and polish construction remain factory-owned.

**Tech Stack:** Python 3.11+, pathlib, dataclasses, Protocol, JSON Schema, Python frontmatter, pytest, Ruff, Pyright.

---

## Execution Coordination

- **Prerequisite:** the Increment 1 agentic-I/O/freshness foundation is merged.
- **Parallel after Task 1:** paths, schema-validator/schemas, ledger/plan parser, and declarative config extraction are file-disjoint streams. One integration worker owns substrate/__init__.py and all package-level exports.
- **Serial:** manifest-validator inversion precedes evidence read-model migration; agent inversion precedes Pi-backend/skills migration; compatibility shims and all caller retargeting are merged only after each canonical module’s parity suite passes.
- **Do not parallelise:** changes to factory.orchestrator.__main__, factory.orchestrator.skills, and factory.evidence.manifests; they compose multiple streams.

## File Structure

**Create:**

- src/substrate/paths.py
- src/substrate/schemas/ with every current JSON schema byte-preserved
- src/substrate/validators/{__init__,schema,kb,session,manifest}.py
- src/substrate/ledger/{__init__,tasks,plans}.py
- src/substrate/config.py
- src/substrate/agents/{__init__,model,backend,skills}.py
- src/substrate/evidence/{__init__,model,read}.py
- src/substrate/documents/{__init__,adr}.py
- tests/unit/substrate/test_no_forbidden_imports.py
- tests/unit/substrate/test_compatibility_paths.py
- tests/unit/substrate/test_validator_inversion.py
- tests/unit/substrate/test_evidence_read_model.py

**Modify:**

- src/factory/paths.py
- src/factory/config.py
- src/factory/validation/{schema_validator,kb_validator,session_validator,manifest_validator}.py
- src/factory/orchestrator/{ledger,plan_to_tasks,pi_backend,skills,__main__}.py
- src/factory/orchestrator/types.py
- src/factory/evidence/{manifests,finalize,reconcile}.py
- all direct callers found by rtk rg “factory.(paths|config|validation|orchestrator.ledger|evidence.manifests)”
- tests/unit/{test_config.py,test_plan_to_tasks.py,orchestrator/test_ledger.py,orchestrator/test_ledger_satisfies.py,orchestrator/test_pi_backend.py,orchestrator/test_skills.py,evidence/test_manifests.py}

### Task 1: Guard the neutral boundary and extract paths, schemas, and pure validators

- [ ] **Step 1: Add a forbidden-import test.**

Create tests/unit/substrate/test_no_forbidden_imports.py that parses every src/substrate/**/*.py with ast and fails on:

    import factory
    import coherence
    from factory...
    from coherence...

The assertion prints each offending file and import text. Add compatibility tests importing factory.paths, factory.validation.schema_validator, factory.validation.kb_validator, and factory.validation.session_validator under warnings.catch_warnings(record=True), asserting a single DeprecationWarning naming the corresponding substrate path and identical public results.

- [ ] **Step 2: Run the new test before extraction.**

Run: rtk proxy uv run python -m pytest tests/unit/substrate/test_no_forbidden_imports.py tests/unit/substrate/test_compatibility_paths.py -q

Expected: import failure for substrate validators/paths.

- [ ] **Step 3: Move pure code and schemas.**

Move factory.paths verbatim to substrate.paths. Move every factory/schemas/*.schema.json to substrate/schemas with unchanged content and update substrate.validators.schema:

    SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
    def validate_against(instance: dict, schema: dict) -> list[str]: ...
    def validate(instance: dict, schema_path: Path | str) -> list[str]: ...

Move kb_validator and session_validator to substrate.validators, changing only their schema import. Split manifest validation into a pure substrate.validators.manifest function:

    def normalize_manifest(manifest: dict) -> dict: ...
    def context_ref_errors(manifest: dict, repo_root: Path) -> list[str]: ...
    def validate_manifest_document(manifest, repo_root, check_errors, coverage_errors) -> list[str]: ...

Its two callable arguments return lists and are invoked only after schema/context validation. The legacy factory.validation.manifest_validator.validate_manifest retains EvidenceContext, DEFAULT_REGISTRY, and coverage_errors construction, injects those callables, emits a warning, and keeps its existing signature.

- [ ] **Step 4: Verify pure and legacy behaviour.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate/test_no_forbidden_imports.py tests/unit/substrate/test_validator_inversion.py tests/unit/test_kb_validator.py tests/unit/validation -q
    rtk proxy uv run ruff check src/substrate src/factory/validation tests/unit/substrate

Expected: the same valid/invalid manifests produce the existing errors; no substrate import reaches factory/coherence.

- [ ] **Step 5: Commit the first stream.**

    git add src/substrate/paths.py src/substrate/schemas src/substrate/validators src/factory/paths.py src/factory/validation tests/unit/substrate tests/unit/test_kb_validator.py tests/unit/validation
    git commit -m "refactor(substrate): extract paths and document validators"

### Task 2: Extract task/plan parsing and neutral gate declarations

- [ ] **Step 1: Add parity tests for old and new task/plan parsers.**

For each existing ledger and plan fixture, compare:

    substrate.ledger.tasks.load_tasks(root)
    factory.orchestrator.ledger.load_tasks(root)
    substrate.ledger.plans.parse_plan_tasks(path)
    factory.orchestrator.plan_to_tasks.parse_plan_tasks(path)

Assert equality of Task/ParsedPlanTask data, NoTasksFoundError text, and status writes. Add config fixtures proving substrate.config.load_gate_declarations parses gate names/steps but never imports factory.polish.config.

- [ ] **Step 2: Confirm the new imports do not exist.**

Run: rtk proxy uv run python -m pytest tests/unit/orchestrator/test_ledger.py tests/unit/orchestrator/test_ledger_satisfies.py tests/unit/test_plan_to_tasks.py tests/unit/test_config.py -q

Expected: failure for the substrate modules.

- [ ] **Step 3: Move parsers and split configuration composition.**

Create substrate.ledger.tasks from orchestrator/ledger.py and substrate.ledger.plans from plan_to_tasks.py, including Task, load_tasks, set_status, ParsedPlanTask, NoTasksFoundError, parse_plan_tasks, and run. Old modules warn/re-export.

Create substrate.config with GateStep, GateDeclarations, GateConfigError, load_gate_declarations, and require_gates. It reads YAML and validates declaration shape only. Keep factory.config.FactoryConfig and the dynamic factory.polish.config construction in factory.config, which calls substrate.config then composes factory-specific objects. It is an adapter, not a verbatim move.

- [ ] **Step 4: Retarget assurance-side callers and run parity suites.**

Retarget direct readers in factory requirements, evidence reconciliation, and system query code to substrate imports. Keep execution-specific composition imports at factory paths. Run:

    rtk proxy uv run python -m pytest tests/unit/orchestrator/test_ledger.py tests/unit/orchestrator/test_ledger_satisfies.py tests/unit/test_plan_to_tasks.py tests/unit/test_config.py -q
    rtk proxy uv run pyright

Expected: old/new APIs are equal and no normal canonical caller triggers a warning.

- [ ] **Step 5: Commit the second stream.**

    git add src/substrate/ledger src/substrate/config.py src/factory/orchestrator/ledger.py src/factory/orchestrator/plan_to_tasks.py src/factory/config.py tests/unit
    git commit -m "refactor(substrate): extract ledger and gate declarations"

### Task 3: Invert agent composition and split the evidence read model

- [ ] **Step 1: Write agent injection and evidence read/write tests.**

Test substrate.agents.backend.PiAgentBackend with an injected:

    def scope_for(role: str) -> Scope: ...

and assert it never imports factory roles. Assert factory.orchestrator.pi_backend supplies the existing ROLE_SCOPE mapping and preserves AgentRole/AgentResult/InterruptionReason results. Test substrate.agents.skills.load_skill_block reads the same bytes as the old skill loader.

For manifests, test substrate.evidence.read.load_run_manifest/list_run_manifests against the existing fixtures, then assert factory.evidence.manifests.write_run_manifest is still the only writer and substrate.evidence exposes no write function.

- [ ] **Step 2: Run to establish the missing APIs.**

Run: rtk proxy uv run python -m pytest tests/unit/orchestrator/test_pi_backend.py tests/unit/orchestrator/test_skills.py tests/unit/evidence/test_manifests.py tests/unit/substrate/test_evidence_read_model.py -q

Expected: new substrate import failures.

- [ ] **Step 3: Implement the split.**

Move AgentResult, InterruptionReason, Scope, generic PiAgentBackend, and load_skill_block to substrate.agents. The factory wrapper translates AgentRole to string and passes:

    lambda role: ROLE_SCOPE[AgentRole(role)]

Role catalogues, prompts, and execution orchestration remain factory.

Move manifest schema version, migration/normalisation, validation, load_run_manifest, and list_run_manifests to substrate.evidence.read/model. Retain atomic write_run_manifest under factory.evidence.manifests and make it call the substrate normaliser. Retarget factory.evidence.finalize and reconcile to the substrate reader.

- [ ] **Step 4: Run agent/evidence and boundary regressions.**

Run:

    rtk proxy uv run python -m pytest tests/unit/orchestrator/test_pi_backend.py tests/unit/orchestrator/test_skills.py tests/unit/evidence/test_manifests.py tests/unit/evidence/test_reconcile.py tests/unit/substrate -q
    rtk proxy uv run pyright

Expected: all legacy calls still work with one explicit warning; canonical code uses substrate without warnings.

- [ ] **Step 5: Commit the third stream.**

    git add src/substrate/agents src/substrate/evidence src/factory/orchestrator/pi_backend.py src/factory/orchestrator/skills.py src/factory/evidence tests/unit
    git commit -m "refactor(substrate): separate agents and evidence reads"

### Task 4: Integrate canonical imports and prove one-release compatibility

- [ ] **Step 1: Add a parameterised legacy-import matrix.**

Cover every old moved module, its new canonical module, expected warning text, and one representative callable. Include factory.paths, factory.config, four validator modules, orchestrator ledger/plan/pi backend/skills, and evidence manifests.

- [ ] **Step 2: Retarget production callers.**

Use rtk rg to enumerate direct factory imports. Retarget only code that consumes neutral data to substrate; retain factory composition adapters in orchestration/finalization. No source file under substrate may be given a compatibility import merely to make a caller work.

- [ ] **Step 3: Run complete affected verification.**

Run:

    rtk proxy uv run python -m pytest tests/unit/substrate tests/unit/orchestrator tests/unit/evidence tests/unit/requirements tests/unit/validation -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright
    rtk rg -n "^(from|import) (factory|coherence)" src/substrate

Expected: tests/static checks pass; the final rg has no matches.

- [ ] **Step 4: Commit the integration.**

    git add src tests
    git commit -m "refactor(substrate): adopt neutral shared imports"

## Plan Self-review

- Covers all remaining neutral moves from the original Increment 1 except codemap/KB/signatures, which are isolated in Increment 1C.
- Preserves the crucial architecture rule by making config and manifest validation factory composition adapters rather than dishonest substrate moves.
- The parallel streams share no production files until Task 4; Task 4 owns all integration conflicts.

## Review Amendments

Split Task 1 production ownership into Task 1A paths/schema/validators and Task 1B ledger/config, with separate worktrees; Task 4 remains integration owner. substrate.documents.adr exposes parse_adr(path) -> AdrDocument(id, title, status, refs) and tests/fixtures live in tests/unit/substrate/test_adr.py. Move AgentResult and InterruptionReason from factory.orchestrator.types to substrate.agents.model; Scope stays in factory.orchestrator.roles as role-catalogue input, while substrate.agents.backend receives scope_for(role) -> ScopeLike Protocol. factory.orchestrator.types and pi_backend become warning composition wrappers.
