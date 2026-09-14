# FEAT-017 Coordinated Closure Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the evidence-first FEAT-017 lifecycle that exposes exactly one permitted planning action, enforces per-SR consent and a compiled planning gate pack, and keeps existing Claude Code workflows usable as a compatibility route.

**Architecture:** Add a pure `coherence.planning.lifecycle` projection layer that consumes only validated run evidence and returns either one display-only action or an attributable block. Keep mutations in existing session, review, and handoff entrypoints; the projector neither writes nor invokes commands. Introduce run-local artifact/consent/gate evidence formats so content mutation invalidates successor stages, then make session and thin host adapters render that canonical result verbatim.

**Tech Stack:** Python 3.12, dataclasses, JSON/JSONL evidence files, pytest, Ruff, Pyright, existing Coherence CLI/Claude Code/Hermes adapters.

---

## File map

- `src/coherence/planning/lifecycle.py` — pure lifecycle evidence loader and one-action/block projection.
- `src/coherence/planning/artifacts.py` — safe run-local manifest, content hashing, freshness, and required-artifact helpers.
- `src/coherence/planning/consent.py` — strict per-SR, hash-bound human-decision schema and validator.
- `src/coherence/planning/gates.py` — versioned planning-gate-pack schema, compiler, evaluator, and result validator; retain legacy consent readers only as compatibility shims.
- `src/coherence/planning/session.py` — validates persisted session identity and delegates all legal-action selection to `lifecycle.py`.
- `src/coherence/planning/intent.py` and `model.py` — structured semantic-challenge event contract and materialization.
- `src/coherence/planning/review.py` (new) — deterministic cross-artifact relation/task-declaration findings used as review evidence.
- `src/coherence/planning/handoff.py` — require a fresh successful planning gate-pack result rather than defaulting to pass.
- `src/coherence/planning/cli.py` and `guided_entrypoint.py` — explicit mutation verbs for lifecycle evidence plus canonical projector rendering.
- `.claude/commands/coherence-plan.md`, `.claude/hooks/*.py`, `.hermes/plugins/coherence-plan/*` — retain the documented compatibility path and add only a guided-projection presentation seam.
- `tests/unit/coherence/test_planning_{artifacts,consent,lifecycle,review,gates,handoff,session,intent,guided}.py` — focused unit/contract coverage.

### Task 1: Establish run-local artifact evidence and freshness primitives

**Files:**
- Create: `src/coherence/planning/artifacts.py`
- Create: `tests/unit/coherence/test_planning_artifacts.py`
- Modify: `src/coherence/planning/__init__.py`

- [ ] **Step 1: Write failing manifest and freshness tests**

```python
def test_manifest_records_sorted_safe_artifacts_and_current_hashes(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("spec v1", encoding="utf-8")

    manifest = build_artifact_manifest(tmp_path, "run-001", {"spec": spec})

    assert manifest["schema"] == 1
    assert manifest["run_id"] == "run-001"
    assert manifest["artifacts"] == [{"kind": "spec", "path": "docs/spec.md", "sha256": sha256_file(spec)}]


def test_manifest_freshness_fails_closed_after_content_mutation(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("v1", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, "run-001", {"spec": spec})
    spec.write_text("v2", encoding="utf-8")

    assert validate_artifact_manifest(tmp_path, manifest) == (False, "artifact changed: docs/spec.md")
```

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_artifacts.py -q -o addopts=''`

Expected: import failure for `coherence.planning.artifacts`.

- [ ] **Step 3: Implement a strict, read-only manifest contract**

Implement `sha256_file(path)`, `build_artifact_manifest(root, run_id, artifacts)`, `write_artifact_manifest(root, run_id, manifest)`, `read_artifact_manifest(root, run_id)`, and `validate_artifact_manifest(root, manifest)`. Require schema `1`, a safe run ID, sorted unique `kind` values, root-relative forward-slash paths, and 64-character lowercase SHA-256 digests. Use `safe_root`/`safe_resolve`; reject missing files, symlink escapes, malformed JSON, duplicate kinds, and altered bytes with stable reasons. `build_*` and `validate_*` remain pure/read-only; only `write_*` atomically writes `.factory/planning/<run>/artifacts.json`.

- [ ] **Step 4: Add negative tests**

```python
@pytest.mark.parametrize("artifacts", [
    {"spec": Path("../outside.md")},
    {"spec": Path("docs/spec.md"), "plan": Path("docs/spec.md")},
])
def test_manifest_rejects_unsafe_or_duplicate_sources(tmp_path: Path, artifacts: dict[str, Path]) -> None:
    with pytest.raises(ArtifactError):
        build_artifact_manifest(tmp_path, "run-001", artifacts)
```

- [ ] **Step 5: Run focused verification and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_artifacts.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning/artifacts.py tests/unit/coherence/test_planning_artifacts.py`

Run: `rtk uv run pyright src/coherence/planning/artifacts.py`

Expected: all commands exit zero.

Commit: `git add src/coherence/planning/artifacts.py src/coherence/planning/__init__.py tests/unit/coherence/test_planning_artifacts.py && git commit -m "feat(planning): add hash-bound artifact evidence"`

### Task 2: Replace set-wide adoption with per-SR hash-bound human consent

**Files:**
- Create: `src/coherence/planning/consent.py`
- Create: `tests/unit/coherence/test_planning_consent.py`
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/cli.py`

- [ ] **Step 1: Write RED tests for independent consent and invalidation**

```python
def test_each_candidate_sr_requires_its_own_human_hash_bound_decision(tmp_path: Path) -> None:
    hashes = {"requirements/SR-071.md": "1" * 64, "requirements/SR-072.md": "2" * 64}
    write_sr_decision(tmp_path, "run-001", "SR-071", hashes["requirements/SR-071.md"], "approve", "human", CONSENT_PHRASE)

    result = validate_sr_decisions(tmp_path, "run-001", {
        "SR-071": hashes["requirements/SR-071.md"], "SR-072": hashes["requirements/SR-072.md"],
    })

    assert result == (False, "missing human consent: SR-072")


def test_changed_requirement_invalidates_only_its_own_consent(tmp_path: Path) -> None:
    write_sr_decision(tmp_path, "run-001", "SR-071", "1" * 64, "approve", "human", CONSENT_PHRASE)
    write_sr_decision(tmp_path, "run-001", "SR-072", "2" * 64, "approve", "human", CONSENT_PHRASE)

    assert validate_sr_decisions(tmp_path, "run-001", {"SR-071": "9" * 64, "SR-072": "2" * 64}) == (
        False, "stale human consent: SR-071"
    )
```

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_consent.py -q -o addopts=''`

Expected: import failure until the new module exists.

- [ ] **Step 3: Implement the versioned per-SR decision record**

Use `.factory/planning/<run>/consent/<SR-ID>.json` with exact fields: `schema`, `run_id`, `sr_id`, `requirement_sha256`, `decision`, `reviewer`, `phrase`, and `reason`. Accept only `decision == "approve"`, `reviewer == "human"`, and the exact consent phrase. `validate_sr_decisions` takes the current `{sr_id: sha256}` mapping, verifies the exact record for every candidate, and returns a stable missing/stale/malformed reason. Never accept a review pass, warning acceptance, agent provenance, or a consent record for another SR.

- [ ] **Step 4: Preserve compatibility without letting it satisfy the new lifecycle**

Keep `validate_sr_consent()` readable for legacy callers, mark it as a compatibility validator in its docstring, and add a separate lifecycle-only call path to `validate_sr_decisions()`. Update CLI parsing so an explicit `record-sr-consent` command can write one decision at a time; require `--sr-id`, `--requirement-sha256`, decision metadata, and exact phrase. Do not add a bulk-consent flag.

- [ ] **Step 5: Verify and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_consent.py tests/unit/coherence/test_planning_review_resolution.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning/consent.py src/coherence/planning/gates.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_consent.py`

Run: `rtk uv run pyright src/coherence/planning/consent.py src/coherence/planning/gates.py`

Commit: `git add src/coherence/planning/consent.py src/coherence/planning/gates.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_consent.py && git commit -m "feat(planning): require per-sr hash-bound human consent"`

### Task 3: Add the pure one-action lifecycle projector

**Files:**
- Create: `src/coherence/planning/lifecycle.py`
- Create: `tests/unit/coherence/test_planning_lifecycle.py`
- Modify: `src/coherence/planning/session.py`
- Modify: `src/coherence/planning/legal_actions_adapter.py`

- [ ] **Step 1: Write the lifecycle transition table as RED tests**

```python
@pytest.mark.parametrize(("evidence", "expected"), [
    (LifecycleEvidence.not_started("run-001"), LifecycleProjection.action("author-requirements")),
    (LifecycleEvidence.with_requirements_missing_consent("run-001"), LifecycleProjection.action("record-sr-consent")),
    (LifecycleEvidence.with_consented_requirements("run-001"), LifecycleProjection.action("author-spec")),
    (LifecycleEvidence.with_spec("run-001"), LifecycleProjection.action("author-plan")),
    (LifecycleEvidence.with_plan("run-001"), LifecycleProjection.action("review-spec")),
    (LifecycleEvidence.with_clean_spec_review("run-001"), LifecycleProjection.action("review-plan")),
    (LifecycleEvidence.with_clean_plan_review("run-001"), LifecycleProjection.action("run-planning-gates")),
])
def test_project_returns_exactly_one_next_action(evidence: LifecycleEvidence, expected: LifecycleProjection) -> None:
    assert project_lifecycle(evidence) == expected
```

Add separate tests asserting: changed requirement returns `STALE_SR_CONSENT`; changed spec returns `STALE_SPEC_REVIEW`; a required unresolved challenge returns `UNRESOLVED_CHALLENGE`; failed/missing/stale gate results block handoff; and a valid handoff returns exactly `inspect-handoff`.

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_lifecycle.py -q -o addopts=''`

Expected: import failure for `LifecycleEvidence`, `LifecycleProjection`, and `project_lifecycle`.

- [ ] **Step 3: Implement a side-effect-free evidence model**

Define frozen `LifecycleEvidence` and `LifecycleProjection` dataclasses. `LifecycleProjection.to_dict()` must contain `schema`, `run_id`, `blocked`, `reason`, `state`, `legal_next_actions`, `run_identity`, `starts_automatically`, and a versioned action registry. Enforce `len(legal_next_actions) in {0, 1}`. The ordered action IDs are exactly `author-requirements`, `record-sr-consent`, `author-spec`, `author-plan`, `review-spec`, `review-plan`, `run-planning-gates`, `create-handoff`, then valid-handoff actions. The projector cannot import subprocess, write helpers, or host adapters.

- [ ] **Step 4: Delegate session legal actions**

Replace session’s handoff-presence branch with a validated evidence loader that calls `status_session()`, `read_intent()`, artifact/consent/review/gate validators, and `validate_handoff()` before passing normalized evidence to `project_lifecycle()`. Preserve stale session rejection. Remove all lifecycle ordering from `session.py`; it must only adapt validated facts into `LifecycleEvidence`.

- [ ] **Step 5: Add adapter contract tests**

```python
def test_legal_actions_adapter_preserves_single_backend_action() -> None:
    projection = parse_legal_actions_projection(json.dumps({
        "schema": 2, "run_id": "run-001", "blocked": False, "reason": None,
        "state": "author_spec", "legal_next_actions": ["author-spec"],
        "starts_automatically": False, "run_identity": {"run_id": "run-001", "next_sequence": 2, "journal_sha256": "a" * 64},
        "action_registry": {"schema": 2, "legal_ids": ["author-spec"], "registry_hash": "b" * 64},
    }), "run-001")
    assert projection["legal_next_actions"] == ["author-spec"]
```

- [ ] **Step 6: Verify and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_lifecycle.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_legal_actions_adapter.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning/lifecycle.py src/coherence/planning/session.py src/coherence/planning/legal_actions_adapter.py tests/unit/coherence/test_planning_lifecycle.py`

Run: `rtk uv run pyright src/coherence/planning/lifecycle.py src/coherence/planning/session.py`

Commit: `git add src/coherence/planning/lifecycle.py src/coherence/planning/session.py src/coherence/planning/legal_actions_adapter.py tests/unit/coherence/test_planning_lifecycle.py && git commit -m "feat(planning): project one authoritative lifecycle action"`

### Task 4: Persist host-triggered semantic challenges without granting reviewer authority

**Files:**
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/intent.py`
- Modify: `src/coherence/planning/session.py`
- Modify: `src/coherence/planning/guided_entrypoint.py`
- Modify: `tests/unit/coherence/test_planning_intent.py`
- Modify: `tests/unit/coherence/test_planning_guided.py`

- [ ] **Step 1: Write RED tests for structured semantic review events**

```python
def test_semantic_challenge_is_proposed_not_resolved_by_its_reviewer(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Make planning trustworthy")
    append_semantic_challenge(tmp_path, "run-001", {
        "id": "semantic-1", "kind": "unmeasurable_success", "claim": "trustworthy",
        "rationale": "No observable success criterion is supplied.",
        "evidence_needed": "measurable acceptance criterion", "provenance": "host:claude-agent",
    })

    challenge = read_intent(run_intent_path(tmp_path, "run-001"), project_root=tmp_path).challenges[0]
    assert challenge.status == "unresolved"
    assert challenge.provenance == "host:claude-agent"
```

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_guided.py -k semantic -q -o addopts=''`

Expected: missing session/entrypoint verb and strict event validator.

- [ ] **Step 3: Implement the semantic proposal event**

Add `semantic_challenge_proposed` to the allowed journal event kinds, with exact text fields `id`, `kind`, `claim`, `rationale`, `evidence_needed`, and `provenance`. Replay it into the same `PlanningChallenge` representation as deterministic `challenge_raised`, always setting status to `unresolved`. Reject duplicate IDs and reject any proposed payload containing status, response, resolution, or reviewer-generated consent fields. Keep `challenge_resolved` exclusively in `resolve_capture_challenge()` and require human provenance there.

- [ ] **Step 4: Expose a transport-only entrypoint**

Add `propose-challenge` to `SESSION_VERBS`, require its six fields, and validate its response with the existing run-ID/session contract. It must merely transport host output to the journal. Do not invoke a model, auto-disposition a challenge, or change the keyword detector; retain `detect_challenges()` as supplementary deterministic tripwire.

- [ ] **Step 5: Verify and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_guided.py tests/unit/coherence/test_planning_hooks.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning/model.py src/coherence/planning/intent.py src/coherence/planning/session.py src/coherence/planning/guided_entrypoint.py`

Commit: `git add src/coherence/planning/model.py src/coherence/planning/intent.py src/coherence/planning/session.py src/coherence/planning/guided_entrypoint.py tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_guided.py && git commit -m "feat(planning): persist semantic challenge proposals"`

### Task 5: Make cross-artifact review and task SR declarations measurable

**Files:**
- Create: `src/coherence/planning/review.py`
- Create: `tests/unit/coherence/test_planning_review.py`
- Modify: `src/coherence/planning/workflow.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `tests/unit/coherence/test_planning_workflow.py`

- [ ] **Step 1: Write RED finding-class tests**

```python
@pytest.mark.parametrize("fixture_name", ["missing", "dangling", "duplicate", "weak", "overstated", "contradictory"])
def test_relation_review_reports_each_required_finding_class(tmp_path: Path, fixture_name: str) -> None:
    finding = review_relations(load_relation_fixture(tmp_path, fixture_name)).findings[0]
    assert finding.code == f"RELATION_{fixture_name.upper()}"
    assert finding.severity == "error"


def test_generated_task_that_changes_production_requires_affected_srs() -> None:
    report = review_task_declarations([{"id": "T-017", "files": ["src/coherence/planning/session.py"]}])
    assert report.findings[0].code == "TASK_SR_DECLARATION_MISSING"
```

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_review.py -q -o addopts=''`

Expected: missing review module.

- [ ] **Step 3: Implement deterministic review evidence**

Implement `ReviewEvidence`, `ReviewReport`, `review_relations()`, and `review_task_declarations()`. Consume canonical `implemented_by`/`verified_by` relation records and generated task metadata; emit stable `PlanningFinding`s for missing, dangling, duplicate, weak, overstated, and contradictory links. Require non-empty sorted `affected_srs` for a task that changes `src/`, `tests/`, `requirements/`, or gate configuration, and reconcile its SR IDs against canonical source/validation relations and generated/mirrored task outputs.

- [ ] **Step 4: Integrate review evidence before semantic stage completion**

Have `PlanningWorkflow.run_stage()` run deterministic review first for plan and derivation stages. Persist the report in `.factory/planning/<run>/cross-artifact-review.json` and put its hash in stage evidence. Deterministic errors block before the reviewer callback; warnings are included in semantic context but cannot be silently accepted as consent.

- [ ] **Step 5: Verify and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_review.py tests/unit/coherence/test_planning_workflow.py tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning/review.py src/coherence/planning/workflow.py src/coherence/planning/run.py tests/unit/coherence/test_planning_review.py`

Commit: `git add src/coherence/planning/review.py src/coherence/planning/workflow.py src/coherence/planning/run.py tests/unit/coherence/test_planning_review.py tests/unit/coherence/test_planning_workflow.py && git commit -m "feat(planning): enforce cross-artifact trace review"`

### Task 6: Compile and enforce a versioned planning gate pack at handoff

**Files:**
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/handoff.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `tests/unit/coherence/test_planning_gates.py`
- Modify: `tests/unit/coherence/test_planning_handoff.py`

- [ ] **Step 1: Write RED gate-pack tests**

```python
def test_compiled_gate_pack_has_stage_resolver_dependencies_evidence_and_failure() -> None:
    pack = compile_planning_gate_pack("FEAT-017", version=1)
    assert {"stage", "required", "resolver", "dependencies", "evidence", "failure"} <= set(pack["gates"][0])


@pytest.mark.parametrize("result", [None, {"status": "fail"}, {"status": "pass", "evidence": []}, {"status": "pass", "pack_sha256": "0" * 64}])
def test_handoff_rejects_missing_failed_unevidenced_or_stale_required_gate(tmp_path: Path, result: object) -> None:
    with pytest.raises(HandoffError, match="planning gate"):
        build_handoff(tmp_path, clean_report(tmp_path), gate_summary=result)
```

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_gates.py tests/unit/coherence/test_planning_handoff.py -q -o addopts=''`

Expected: tests fail because handoff currently defaults `gate_summary` to `{"status": "pass"}`.

- [ ] **Step 3: Implement pack compilation and result validation**

Add `compile_planning_gate_pack(feature_id, version)`, `evaluate_planning_gate_pack(root, run_id, pack)`, and `validate_planning_gate_result(root, run_id, result)`. Each entry must declare `id`, `stage`, `required`, `resolver`, sorted `dependencies`, expected `evidence`, and `failure`. Evaluation may inspect planning artifacts/evidence only; prohibit subprocess execution and implementation-gate claims. Write both immutable pack and result under the run directory; bind result to the pack hash and every evidence hash.

- [ ] **Step 4: Remove default-pass handoff behavior**

Make `build_handoff()` require a validated current planning-gate result. Include `planning_gate_pack_sha256` and `planning_gate_result_sha256` in the handoff payload. Extend `validate_handoff()` to revalidate both hashes and gate evidence, failing closed for missing, failed, unevidenced, stale, downgraded, or unexecuted required gates.

- [ ] **Step 5: Add the explicit CLI operation**

Expose `coherence plan run-planning-gates --project-root ... --run-id ... --json`. It compiles/evaluates the planning pack only, emits a structured result, and must not run `unit`, `integration`, `full`, or any factory execution gate.

- [ ] **Step 6: Verify and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_gates.py tests/unit/coherence/test_planning_handoff.py tests/unit/coherence/test_planning_cli.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning/gates.py src/coherence/planning/handoff.py src/coherence/planning/cli.py`

Run: `rtk uv run pyright src/coherence/planning/gates.py src/coherence/planning/handoff.py`

Commit: `git add src/coherence/planning/gates.py src/coherence/planning/handoff.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_gates.py tests/unit/coherence/test_planning_handoff.py && git commit -m "feat(planning): enforce compiled gate pack before handoff"`

### Task 7: Preserve host compatibility while presenting the guided projection verbatim

**Files:**
- Modify: `.claude/commands/coherence-plan.md`
- Modify: `.claude/hooks/coherence_channel_guard.py`
- Modify: `.claude/hooks/coherence_finalize_gate.py`
- Modify: `.claude/hooks/coherence_challenge_surface.py`
- Modify: `.claude/settings.json`
- Modify: `.hermes/plugins/coherence-plan/plugin.py`
- Modify: `.hermes/plugins/coherence-plan/README.md`
- Modify: `tests/unit/coherence/test_planning_hooks.py`
- Modify: `tests/unit/coherence/test_planning_guided.py`

- [ ] **Step 1: Write RED compatibility assertions**

```python
def test_claude_compatibility_route_does_not_claim_lifecycle_stage() -> None:
    command = Path(".claude/commands/coherence-plan.md").read_text(encoding="utf-8")
    assert "Compatibility route" in command
    assert "backend-derived lifecycle stage" not in command


def test_hermes_renders_the_backend_single_action_without_reordering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin, "legal_actions_report", lambda *_: {"legal_next_actions": ["author-plan"]})
    assert plugin.render_guided_status(Path("."), "run-001")["legal_next_actions"] == ["author-plan"]
```

- [ ] **Step 2: Run RED**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_hooks.py tests/unit/coherence/test_planning_guided.py -q -o addopts=''`

Expected: guided renderer/documentation assertions fail until the new distinction is documented and implemented.

- [ ] **Step 3: Keep both routes explicit**

Document the existing Claude slash-command/hooks route as compatibility workflow and the new guided route as a separately selected, backend-projected workflow. Retain channel/finalize hooks as defense in depth for both routes, but ensure neither computes a stage or writes an approval. Let a Claude semantic agent hook call only `propose-challenge`; Hermes must render the result from `legal_actions_report` and never reconstruct ordered actions. Do not introduce host-specific persistence.

- [ ] **Step 4: Verify and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_hooks.py tests/unit/coherence/test_planning_guided.py tests/unit/coherence/test_legal_actions_adapter.py -q -o addopts=''`

Run: `rtk uv run ruff check .claude/hooks/coherence_channel_guard.py .claude/hooks/coherence_finalize_gate.py .claude/hooks/coherence_challenge_surface.py .hermes/plugins/coherence-plan/plugin.py`

Commit: `git add .claude .hermes/plugins/coherence-plan tests/unit/coherence/test_planning_hooks.py tests/unit/coherence/test_planning_guided.py && git commit -m "feat(planning): retain host workflow compatibility"`

### Task 8: Bind FEAT-017 requirements and run an end-to-end non-executing proof

**Files:**
- Modify: `requirements/SR-043.md`
- Modify: `requirements/SR-044.md`
- Modify: `requirements/SR-053.md`
- Modify: `requirements/SR-054.md`
- Modify: `requirements/SR-055.md`
- Modify: `requirements/SR-065.md`
- Modify: `requirements/SR-072.md`
- Modify: `tests/unit/coherence/test_planning_trace_contract.py`
- Create: `tests/unit/coherence/test_planning_closure_e2e.py`
- Modify: `requirements/index.json`, `docs/features/FEAT-017.md`, `bundles/FEAT-017.json`, and their generated mirrors only through the project’s canonical regeneration command.

- [ ] **Step 1: Write the full guided lifecycle proof**

```python
def test_guided_lifecycle_reaches_only_nonexecuting_handoff_actions(tmp_path: Path) -> None:
    run = "run-001"
    seed_current_requirement_artifacts(tmp_path, run)
    assert legal_actions_session(tmp_path, run)["legal_next_actions"] == ["record-sr-consent"]
    record_all_individual_human_consents(tmp_path, run)
    author_current_spec_and_plan(tmp_path, run)
    record_clean_reviews_and_current_task_relations(tmp_path, run)
    evaluate_current_planning_gate_pack(tmp_path, run)
    write_current_handoff(tmp_path, run)

    projection = legal_actions_session(tmp_path, run)
    assert projection["legal_next_actions"] == ["inspect-handoff"]
    assert projection["starts_automatically"] is False
    assert no_factory_execution_was_invoked(tmp_path)
```

- [ ] **Step 2: Run RED, then implement fixture helpers only where repeated setup requires them**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_closure_e2e.py -q -o addopts=''`

Expected: fail until all earlier tasks are present; no test should mock the lifecycle projector itself.

- [ ] **Step 3: Keep the requirement scope honest**

Do not add `binding:` blocks or change a proposed SR to adopted as part of this closure implementation: those remain human-authoring decisions outside the implementation task. Update `test_planning_trace_contract.py` so its source-spec map covers SR-043, SR-044, SR-053, SR-054, SR-055, SR-065, and SR-072, and assert the planned SR-071 visualizer still has no presentation implementation path. The test must continue to validate source anchors and the distinct legacy versus lifecycle consent validators.

- [ ] **Step 4: Regenerate canonical requirement projections and verify traceability**

Run the project’s documented register/mirror regeneration command, then:

Run: `rtk uv run coherence trace check --project-root .`

Run: `rtk uv run coherence register check --project-root .`

Expected: both succeed with generated feature/bundle/index projections current.

- [ ] **Step 5: Run the closure verification suite and commit**

Run: `rtk uv run pytest tests/unit/coherence/test_planning_*.py tests/unit/coherence/test_legal_actions_adapter.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_closure_e2e.py`

Run: `rtk uv run pyright src/coherence/planning`

Run: `rtk git diff --check`

Expected: every command exits zero; handoff proof confirms no downstream work starts automatically.

Commit: `git add requirements docs/features/FEAT-017.md bundles/FEAT-017.json tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_closure_e2e.py && git commit -m "test(feat17): verify coordinated closure evidence"`

## Self-review

- **Spec coverage:** Task 1 creates the hash/freshness seam; Task 2 covers independent new-or-revised SR consent; Task 3 supplies the pure lifecycle and exact relevant action; Task 4 implements structured semantic proposals and human-only disposition; Task 5 covers all six relation finding classes plus task SR reconciliation; Task 6 closes SR-055’s default-pass gap; Task 7 preserves the Claude compatibility workflow and thin Hermes presentation; Task 8 proves traceability and the non-executing handoff boundary. SR-071 remains intentionally unimplemented while retaining the projector seam it needs.
- **No placeholders:** every code-changing task names files, concrete public functions/records, RED/GREEN commands, and a commit boundary. The test fixture helper names in Task 8 are deliberately scoped to the new test module and must be implemented there; they are not new production interfaces.
- **Consistency:** one source of action order (`project_lifecycle`), one run-local artifact manifest, one consent record per SR, one gate-pack hash-bound result, and one host-neutral challenge record are used throughout.
