# Coherence Increment 3: Navigation, Presentation, Goals, and Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the assurance-side navigator, presentation, goals, and simulation surfaces to coherence; add draft bundle authoring and a safe typed remediation-action protocol.

**Architecture:** Transfer goals and simulation independently, then move navigation, its scope-ref parser, and presentation as a coordinated consumer cutover because system CLI/queries currently import all three. Canonical navigation reads stable artifact/snapshot references through substrate guarded reads, so stale data is marked or routed rather than rendered current. Browser remediation uses a strict typed action allow-list that calls existing writers, never arbitrary shell commands.

**Tech Stack:** Python 3.11+, argparse, dataclasses, JSON, substrate references/freshness, TypeScript Pi extension, pytest, npm test.

---

## Execution Coordination

- **Prerequisite:** Increment 2 canonical trace/register and Increment 1C codemap/snapshot APIs.
- **Parallel:** goals and simulation module transfers; navigation shared model/scope-ref transfer; bundle-new fixtures after trace; typed action protocol UI fixtures after its Python action schema freezes.
- **Serial:** presentation moves after navigation scope parsing; all-route CLI integration and factory shims are one integration lane.
- **Successor:** Increment 4 can develop audit/measurement in parallel after Increment 2, but may not change these navigation-owned files.

## File Structure

**Create:**

- src/coherence/navigate/{__init__,cli,models,refs,queries,actions,bundles,adr,worker}.py
- src/coherence/presentation/{__init__,router,level,sim,ide,browser,cli}.py
- src/coherence/goals/ and src/coherence/simulation/ canonical moved modules
- tests/unit/coherence/test_navigate_actions.py
- tests/unit/coherence/test_snapshot_navigation.py

**Modify:**

- src/factory/system/*, src/factory/presentation/*, src/factory/goals/*, src/factory/simulation/*
- src/coherence/{cli,__main__}.py
- pi-ext/factory-watch/src/{system-worker,docs-server,system-bootstrap,system-comprehension,system-renderers}.ts
- pi-ext/factory-watch/test/{system-worker,system-comprehension,system-page}.test.ts
- tests/unit/{system,presentation,goals,simulation}/*

### Task 1: Move goals and simulation through canonical substrate inputs

- [ ] **Step 1: Write old/new module and CLI parity tests.**

For each existing goals/simulation fixture, compare public models, registries, evaluation output, and CLI text/exit from factory and coherence paths. Assert canonical code uses coherence.register/substrate evidence rather than factory requirements/ledger. Include a stale SnapshotRef fixture that returns a stale marker or typed blocker, never a current-looking value.

- [ ] **Step 2: Move modules and create shims.**

Move factory.goals schema/registry/lifecycle/evaluator/cli and factory.simulation registry/evidence/sensitivity/cli to coherence. Retarget neutral data imports to substrate and register imports to coherence.register. Replace old modules with warning forwarding shims, including __main__.

- [ ] **Step 3: Verify transfers.**

Run: rtk proxy uv run python -m pytest tests/unit/goals tests/unit/simulation -q

Expected: old/new behavioural parity and no coherence->factory imports.

- [ ] **Step 4: Commit.**

    git add src/coherence/goals src/coherence/simulation src/factory/goals src/factory/simulation tests/unit/goals tests/unit/simulation
    git commit -m "refactor(coherence): migrate goals and simulation"

### Task 2: Move navigation and presentation as one consumer cutover

- [ ] **Step 1: Freeze scope-reference and route contracts.**

Add tests for all nine current scope kinds:

    sr:, task:, feat:, file:, adr:, diag:, metric:, goal:, bundle:

Every route scope, brief, matrix, timeline, story, reverse, vcycle, guide, membership, bundle, goal, sim, diagram, present must echo the canonical scope ref and expose source SnapshotRef/freshness. A stale snapshot must produce a stale marker and resolver/action, never a normal current narrative.

- [ ] **Step 2: Transfer coordinated modules.**

Move factory.system modules to coherence.navigate and factory.presentation modules to coherence.presentation. Place parse_scope_ref/labels/models in coherence.navigate, and retarget presentation.router to it. Retarget query reads to substrate evidence/ledger and coherence trace/register/goals/simulation. Replace all factory modules with warnings/re-exports; do not update TypeScript callers yet because legacy Python paths must remain valid.

- [ ] **Step 3: Rename coverage to membership compatibly.**

Add coherence navigate membership --gate as the canonical spelling. It invokes the existing membership calculation and preserves coverage --gate result/exit. Keep both factory.system coverage and coherence navigate coverage as one-release warning aliases. Test singular membership, legacy coverage, and internal cmd_memberships spelling produce one result.

- [ ] **Step 4: Verify all routes.**

Run:

    rtk proxy uv run python -m pytest tests/unit/system tests/unit/presentation tests/unit/coherence/test_snapshot_navigation.py -q
    rtk proxy uv run python -m coherence navigate membership --gate

Expected: every route remains available; stale snapshots cannot be rendered as current.

- [ ] **Step 5: Commit.**

    git add src/coherence/navigate src/coherence/presentation src/factory/system src/factory/presentation tests/unit/system tests/unit/presentation tests/unit/coherence
    git commit -m "refactor(coherence): migrate navigation and presentation"

### Task 3: Add draft bundle authoring

- [ ] **Step 1: Write bundle-new tests.**

For a feature with traceable members, assert:

    coherence navigate bundle new --from feat:FEAT-001 --output <path>

derives deterministic draft membership from the trace graph, refuses an existing output unless --force is explicitly supplied, writes no file before a destination is supplied, and passes existing bundle check --draft after write.

- [ ] **Step 2: Implement a draft-only writer.**

Add create_draft_bundle(root, feature_ref, output) to coherence.navigate.bundles. It reads the graph, writes an atomic Markdown/YAML draft clearly marked draft, and does not alter trace links or any authoritative feature/task/spec document. Register bundle new in navigate CLI.

- [ ] **Step 3: Run bundle regression.**

Run: rtk proxy uv run python -m pytest tests/unit/system/test_bundles.py tests/unit/system/test_cli.py -q

Expected: deterministic authoring/check round trip.

- [ ] **Step 4: Commit.**

    git add src/coherence/navigate/bundles.py src/coherence/navigate/cli.py tests/unit/system/test_bundles.py tests/unit/system/test_cli.py
    git commit -m "feat(navigate): author draft trace bundles"

### Task 4: Add typed browser remediation actions

- [ ] **Step 1: Specify allowed action tests.**

Define:

    Action(kind="trace_link" | "trace_defer" | "register_bind", args: dict)

Test unknown kinds, unexpected args, missing required reason, and a browser request without explicit confirmation are refused. Test trace_link calls coherence.trace.write, trace_defer calls its typed writer, and register_bind calls coherence.register.write; no action accepts a shell command string.

- [ ] **Step 2: Implement Python action service and extension bridge.**

Create coherence.navigate.actions with validate_action and execute_confirmed_action. It maps exactly the three enum values to typed writers and returns a structured result/ref. Add extension request/confirmation rendering in the named system worker/browser files; browser code displays the action/reason and never executes supplied command text.

- [ ] **Step 3: Run Python and extension tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_navigate_actions.py tests/unit/system -q
    rtk proxy npm test --prefix pi-ext/factory-watch -- system-worker system-comprehension system-page

Expected: allow-list actions execute only after confirmation; arbitrary command injection is impossible by API shape.

- [ ] **Step 4: Commit.**

    git add src/coherence/navigate/actions.py pi-ext/factory-watch/src pi-ext/factory-watch/test tests/unit/coherence/test_navigate_actions.py
    git commit -m "feat(navigate): add confirmed remediation actions"

### Task 5: Integrate the navigate console group

- [ ] **Step 1: Add console dispatch tests.**

Test python -m coherence navigate for every documented route and assert unknown routes exit 2. Extend coherence.cli GROUPS with navigate, presentation, goals, and simulation only after their modules have passed parity tests.

- [ ] **Step 2: Run final Increment 3 verification.**

Run:

    rtk proxy uv run python -m pytest tests/unit/system tests/unit/presentation tests/unit/goals tests/unit/simulation tests/unit/coherence -q
    rtk proxy npm test --prefix pi-ext/factory-watch
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: complete route migration, legacy compatibility, and extension bridge pass.

- [ ] **Step 3: Commit.**

    git add src/coherence src/factory pi-ext/factory-watch tests
    git commit -m "feat(coherence): expose navigation assurance surfaces"

## Plan Self-review

- Covers Increment 3 migrations, TN-06 bundle authoring, TN-10 typed remediation, TN-08 membership naming, and snapshot-backed navigation.
- The coordinated cutover prevents the current system/presentation/query import cycle from crossing the new boundary.

## Review Amendments

create_draft_bundle writes schema-compatible JSON at the explicit --output path: {"id": "bundle:<feature-id>", "label": "<feature title> draft", "members": [sorted refs], "draft": true}. It rejects any existing output unless --force; --force atomically replaces only that exact path. bundle check --draft consumes this JSON without a format conversion.

Create coherence.navigate.snapshots.resolve_navigation_snapshot(root, ref) -> GuardedNavigationSnapshot(ref, freshness, artifact_ref, resolver_cmd). cmd_brief, cmd_matrix, cmd_timeline, cmd_story, cmd_reverse, cmd_vcycle, cmd_guide, and presentation.router.resolve_intent call it before reading code/plan/spec content. Add a current and stale plan fixture plus a current/stale code-map fixture to test_snapshot_navigation.py; stale output must contain its snapshot ref and resolver command and omit the current-content label.
