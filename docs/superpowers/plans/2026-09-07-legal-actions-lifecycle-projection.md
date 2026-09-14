# Legal-Actions Lifecycle Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the already-drafted Codex guided-planning skill, fix the confirmed cross-run collision in intent materialization, and extend `coherence.planning.session.legal_actions_session()` from a post-handoff-only projection into one that correctly reports capture-stage and author/review-stage legal actions — closing the exact deadlock CODEX_INTENT.md observed and that the drafted Codex skill is independently blocked on.

**Architecture:** `legal_actions_session()` remains the single, host-neutral, read-only projection every host (Claude Code, Codex, Hermes) can query. Today it only understands one state: "handoff exists and validates" vs. "blocked." This plan teaches it three more states it already has the data to compute — not-started, capture (with/without unresolved challenges), and intent-provisional-awaiting-authoring — using only data `session.py` already persists (the capture journal, the derived `PlanningSession`, and the materialized intent document). No new persistence format, no new journal, no new backend authority is introduced. The finer-grained per-artifact author/review handshake CODEX_INTENT's "Decisions confirmed" section describes (route-selection journal events, per-artifact hash-bound attestation) is explicitly deferred — see "Explicitly out of scope" below.

**Tech Stack:** Python 3.11/3.12, `uv`, pytest, Ruff, Pyright, `coherence` CLI (`plan` group).

**Spec:** `CODEX_INTENT.md` (the design discussion this plan resolves) and the grill conducted in this session (five questions: #1–#3 already settled by CODEX_INTENT's own "Decisions confirmed" section; #4 verified as a real bug via code reading, fixed in Task 2; #5 is the test design in Task 3). The resolution of each question is recorded in this plan's Global Constraints below so an executor does not need to re-derive it from the conversation.

## Global Constraints

- The legal-actions projection is host-neutral and read-only: it never mutates planning state, never starts downstream work (`starts_automatically` stays `false` always), and never invents an action the backend does not actually support.
- Semantic action IDs are distinct from CLI verb names (grill Q1): capture verbs `start`/`append`/`resolve`/`finalize` are exposed as `start-capture`/`capture-answer`/`resolve-challenge`/`finalize-capture` in the registry.
- Exactly one legal-actions projection is authoritative across capture, author/review, and post-handoff (grill Q3) — do not add a second, capture-only projection function.
- "No answers and no challenges" in a fresh capture is normal and must not be treated as complete or silently advanced to spec authoring (CODEX_INTENT, "Agreed capture behavior").
- `SR-044`'s no-self-cert invariant applies: this module never grants consent, never infers completion, and never chooses a challenge disposition or terminal status on the human's behalf.
- Every focused test/lint/type command in a task must actually be run and its real output recorded before that task is marked complete.
- No push, no merge to `main`. Commit locally; stop for explicit authorization before merge/push.

## Explicitly out of scope (do not attempt in this plan)

Modeling `author-spec → review-spec → author-plan → review-plan` as individually-gated, artifact-hash-bound legal actions (CODEX_INTENT's full two-phase select → perform → attest-completion handshake, with route-selection journal events) is **not** implemented here. Task 3 exposes all four IDs as a flat set once capture is finalized and no handoff exists yet, matching what the already-drafted Codex skill (Task 1) already expects and gates on — but the backend does not yet enforce their internal order or bind them to artifact hashes. That finer-grained enforcement needs its own design pass first: specifically, where the backend persists the canonical spec/plan artifact path for a run (today `bootstrap`/`check` take `--spec`/`--plan` as caller-supplied arguments with no backend record of "the" canonical path), which is a real open question this session's investigation surfaced but did not resolve. Do not guess at that design inside this plan.

---

### Task 1: Land the drafted Codex guided-planning skill

**Objective:** `.agents/skills/coherence-plan/SKILL.md`, `.agents/skills/coherence-plan/agents/openai.yaml`, and `tests/unit/codex/test_coherence_plan_contract.py` are already rewritten and uncommitted in the working tree (from before this plan existed) to drive `guided_entrypoint`/`guided_pipeline` directly instead of the legacy `coherence plan start`/`resume` verbs. Verified this session: internally consistent, and its own contract test passes (`uv run pytest tests/unit/codex/test_coherence_plan_contract.py -q -o addopts=''` → 5 passed). Commit it as its own logical change before building Task 2/3 on top.

**Files:**
- Commit (no edits): `.agents/skills/coherence-plan/SKILL.md`
- Commit (no edits): `.agents/skills/coherence-plan/agents/openai.yaml`
- Commit (no edits): `tests/unit/codex/test_coherence_plan_contract.py`

**Interfaces:** None — this task changes no code, only lands already-written files.

- [ ] **Step 1: Confirm the working tree still holds exactly this diff and nothing else**

```bash
git status --short .agents/skills/coherence-plan/SKILL.md .agents/skills/coherence-plan/agents/openai.yaml tests/unit/codex/test_coherence_plan_contract.py
```

Expected: all three show as modified (`M`), nothing else. If any file differs from what this plan describes (e.g., someone edited it further), stop and re-read it before proceeding — do not blindly commit an unreviewed diff.

- [ ] **Step 2: Run the contract test**

```bash
uv run pytest tests/unit/codex/test_coherence_plan_contract.py -q -o addopts=''
```

Expected: `5 passed`.

- [ ] **Step 3: Run Ruff on the changed test file** (`SKILL.md`/`openai.yaml` are not Python, nothing to lint there)

```bash
uv run ruff check tests/unit/codex/test_coherence_plan_contract.py
```

Expected: no findings.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/coherence-plan/SKILL.md .agents/skills/coherence-plan/agents/openai.yaml tests/unit/codex/test_coherence_plan_contract.py
git commit -m "feat(codex): drive coherence-plan through the guided entrypoint/pipeline modules"
```

---

### Task 2: Fix the cross-run collision in intent materialization (grill Q4)

**Objective:** `session.py::_intent_path()` hardcodes a single global `.intent/intent.json`, shared by every run ID. `materialize_intent()` unconditionally overwrites that one file with whichever run just mutated — confirmed exploitable today: this repo has two concurrent capture runs (`FEAT-003`, `FEAT-3`) that already clobber each other's snapshot on every mutation. Scope the materialized path per run under `.factory/planning/<run_id>/intent.json`, alongside that run's own journal and state (which are already run-scoped). `cli.py`'s `_session_command` reads the same global path for its `challenges` field and must move with it. `bootstrap.py`/`check.py` are unaffected — they take `--intent`/`intent_path` as a caller-supplied argument and never hardcode this path.

**Files:**
- Modify: `src/coherence/planning/session.py`
- Modify: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_session.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `_intent_path(root: Path, run_id: str) -> Path` (new required `run_id` parameter — Task 3 must call it with the same signature).

- [ ] **Step 1: Write the failing test proving two runs no longer collide**

Add to `tests/unit/coherence/test_planning_session.py`:

```python
def test_concurrent_runs_do_not_clobber_each_others_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "First request")
    start_session(tmp_path, "run-002", "Second request")
    append_session_answer(tmp_path, "run-001", "goal", "Q1?", "Answer one")
    append_session_answer(tmp_path, "run-002", "goal", "Q2?", "Answer two")

    intent_one = json.loads(
        (tmp_path / ".factory" / "planning" / "run-001" / "intent.json").read_text(encoding="utf-8")
    )
    intent_two = json.loads(
        (tmp_path / ".factory" / "planning" / "run-002" / "intent.json").read_text(encoding="utf-8")
    )
    assert intent_one["run_id"] == "run-001"
    assert intent_one["answers"][0]["text"] == "Answer one"
    assert intent_two["run_id"] == "run-002"
    assert intent_two["answers"][0]["text"] == "Answer two"
    assert not (tmp_path / ".intent").exists()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/coherence/test_planning_session.py::test_concurrent_runs_do_not_clobber_each_others_intent_snapshot -q -o addopts=''
```

Expected: FAIL — both runs currently materialize to the same `.intent/intent.json`, so `run-002`'s answer overwrites `run-001`'s and the `.factory/planning/run-001/intent.json` path does not exist yet.

- [ ] **Step 3: Update `_intent_path` and its two call sites in `session.py`**

Change:

```python
def _intent_path(root: Path) -> Path:
    return _inside(root, ".intent", "intent.json")
```

to:

```python
def _intent_path(root: Path, run_id: str) -> Path:
    return _inside(root, ".factory", "planning", run_id, "intent.json")
```

Update `_materialize`:

```python
def _materialize(root: Path, run_id: str) -> None:
    """Materialize the journal without replacing the last good snapshot on failure."""
    try:
        materialize_intent(root, run_id, _intent_path(root, run_id))
    except IntentError as exc:
        raise SessionError(str(exc)) from exc
```

Update the one other call site, in `append_session_answer`:

```python
    document = read_intent(_intent_path(root, run_id), project_root=root)
```

(was `read_intent(_intent_path(root), project_root=root)`).

- [ ] **Step 4: Update `cli.py`'s `_session_command`**

Change:

```python
        intent = read_intent(args.project_root / ".intent" / "intent.json", project_root=args.project_root)
```

to:

```python
        intent = read_intent(
            args.project_root / ".factory" / "planning" / args.run_id / "intent.json",
            project_root=args.project_root,
        )
```

- [ ] **Step 5: Update the six existing tests in `test_planning_session.py` that assert the old global path**

In each of these, replace `tmp_path / ".intent" / "intent.json"` with `tmp_path / ".factory" / "planning" / "run-001" / "intent.json"` (all six use run ID `"run-001"`):

- `test_start_progressively_materializes_initial_request`
- `test_append_progressively_materializes_each_answer`
- `test_resume_rebuilds_snapshot_from_journal_after_interruption`
- `test_materialization_failure_preserves_last_known_good_snapshot`
- `test_append_and_finalize_project_user_text`
- `test_finalize_progressively_materializes_each_status`

- [ ] **Step 6: Run the new test, then the full file**

```bash
uv run pytest tests/unit/coherence/test_planning_session.py -q -o addopts=''
```

Expected: all pass, including the new `test_concurrent_runs_do_not_clobber_each_others_intent_snapshot`.

- [ ] **Step 7: Confirm nothing else in the planning suite depended on the old global path**

```bash
uv run pytest tests/unit/coherence/test_planning_bootstrap.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_run.py tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_cli.py -q -o addopts=''
```

Expected: all pass unchanged (these tests supply their own explicit `--intent`/`intent_path` fixture paths and do not depend on `session.py`'s default; verified this session by reading each production call site — `bootstrap.py`/`check.py` never hardcode `.intent/intent.json`).

- [ ] **Step 8: Ruff and Pyright**

```bash
uv run ruff check src/coherence/planning/session.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_session.py
```
```bash
uv run pyright src/coherence/planning/session.py src/coherence/planning/cli.py
```

Expected: both exit clean.

- [ ] **Step 9: Commit**

```bash
git add src/coherence/planning/session.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_session.py
git commit -m "fix(planning): scope materialized intent snapshots per run id"
```

---

### Task 3: Extend `legal_actions_session()` to model capture and author/review progression

**Objective:** Replace the current all-or-nothing "handoff exists and validates, or `SESSION_NOT_READY`" logic with one that reports the correct legal action for every state `_project()` can already produce (`capture`, `intent_provisional`, `blocked`) and for the not-yet-started case. This is the exact fix CODEX_INTENT.md's Codex session needed, and the exact fix the skill landed in Task 1 needs to get past capture at all (its "Authority and projection" section already allowlists `author-spec`/`author-plan`/`review-spec`/`review-plan` and expects the registry to declare them).

**Files:**
- Modify: `src/coherence/planning/session.py`
- Test: `tests/unit/coherence/test_planning_session.py`

**Interfaces:**
- Consumes: `_intent_path(root, run_id)` from Task 2 (signature already takes `run_id`).
- Produces: no change to `legal_actions_session`'s public signature (`(project_root: Path, run_id: str) -> dict[str, object]`); only its return payload's `blocked`/`reason`/`state`/`legal_next_actions`/`action_registry` contents change. `legal_actions_adapter.py`'s `parse_legal_actions_projection()` already accepts any string list for `legal_next_actions` and any string (or `None`) for `reason` — no change needed there.

- [ ] **Step 1: Write the failing tests**

Replace the existing `test_legal_actions_are_closed_and_block_until_handoff_is_persisted` test in `tests/unit/coherence/test_planning_session.py` with these five:

```python
def test_legal_actions_offer_start_capture_before_a_run_exists(tmp_path: Path) -> None:
    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["run_id"] == "run-001"
    assert projection["blocked"] is False
    assert projection["reason"] is None
    assert projection["state"] == "not_started"
    assert projection["legal_next_actions"] == ["start-capture"]
    assert projection["starts_automatically"] is False
    assert "start-capture" in projection["action_registry"]["legal_ids"]


def test_legal_actions_offer_capture_answer_and_finalize_with_no_open_challenges(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == ["capture-answer", "finalize-capture"]
    assert projection["run_identity"]["run_id"] == "run-001"


def test_legal_actions_offer_resolve_challenge_when_one_is_unresolved(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(
        tmp_path, "run-001", "goal", "What is the goal?",
        "It should have zero cost and be infinitely fast.",
    )

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == ["resolve-challenge"]


def test_legal_actions_offer_author_review_actions_after_provisional_finalize(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(tmp_path, "run-001", "goal", "What is the goal?", "Keep it deterministic")
    finalize_session(tmp_path, "run-001", "provisional")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "intent_provisional"
    assert projection["legal_next_actions"] == ["author-spec", "author-plan", "review-spec", "review-plan"]


def test_legal_actions_block_as_capture_cancelled_after_finalize_cancelled(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")

    finalize_session(tmp_path, "run-001", "cancelled")
    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "CAPTURE_CANCELLED"
    assert projection["legal_next_actions"] == []
```

Add `finalize_session` to this test file's existing import line from `coherence.planning.session` (it is already imported — confirm, do not duplicate the import).

Note: `test_legal_actions_reject_stale_persisted_identity` (the other existing legal-actions test) is unaffected by this task and must still pass unchanged.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_session.py -k "legal_actions" -q -o addopts=''
```

Expected: the five new tests FAIL (current code still returns `SESSION_NOT_READY`/`blocked: true` for all of them since none has a `handoff.json`); `test_legal_actions_reject_stale_persisted_identity` still PASSES (unrelated code path, untouched so far).

- [ ] **Step 3: Implement**

Replace the action registry:

```python
_LEGAL_ACTION_IDS = (
    "start-capture",
    "capture-answer",
    "resolve-challenge",
    "finalize-capture",
    "author-spec",
    "author-plan",
    "review-spec",
    "review-plan",
    "inspect-handoff",
    "revalidate-handoff",
    "select-downstream-workflow",
    "create-downstream-session",
    "resolve-blocking-input",
)
```

Add a small helper above `legal_actions_session`:

```python
def _run_identity(session: PlanningSession) -> dict[str, object]:
    return {
        "run_id": session.run_id,
        "next_sequence": session.next_sequence,
        "journal_sha256": session.journal_sha256,
    }
```

Replace the full body of `legal_actions_session`:

```python
def legal_actions_session(project_root: Path, run_id: str) -> dict[str, object]:
    """Return the closed, fail-closed host action projection for a run.

    The persisted session snapshot is the only source of run identity.  This
    function never accepts caller-provided actions and never invokes a menu
    action or starts downstream work.
    """
    root = _root(project_root)
    _validate_run_id(run_id)
    base: dict[str, object] = {
        "schema": 1,
        "run_id": run_id,
        "legal_next_actions": [],
        "selected_downstream_workflow": None,
        "starts_automatically": False,
        "action_registry": {
            "schema": 1,
            "legal_ids": list(_LEGAL_ACTION_IDS),
            "registry_hash": _ACTION_REGISTRY_HASH,
        },
    }

    if not _journal(root, run_id).exists():
        base.update({
            "blocked": False,
            "reason": None,
            "state": "not_started",
            "legal_next_actions": ["start-capture"],
        })
        return base

    try:
        session = status_session(root, run_id)
    except SessionError:
        base.update({"blocked": True, "reason": "STALE_SESSION_STATE"})
        return base

    if session.state == "blocked":
        base.update({
            "blocked": True,
            "reason": "CAPTURE_CANCELLED",
            "state": session.state,
            "run_identity": _run_identity(session),
        })
        return base

    if session.state == "capture":
        try:
            intent = read_intent(_intent_path(root, run_id), project_root=root)
            unresolved = any(challenge.status == "unresolved" for challenge in intent.challenges)
        except IntentError:
            unresolved = False
        legal = ["resolve-challenge"] if unresolved else ["capture-answer", "finalize-capture"]
        base.update({
            "blocked": False,
            "reason": None,
            "state": session.state,
            "run_identity": _run_identity(session),
            "legal_next_actions": legal,
        })
        return base

    # session.state == "intent_provisional"
    handoff = _inside(root, ".factory", "planning", run_id, "handoff.json")
    if not handoff.is_file():
        base.update({
            "blocked": False,
            "reason": None,
            "state": session.state,
            "run_identity": _run_identity(session),
            "legal_next_actions": ["author-spec", "author-plan", "review-spec", "review-plan"],
        })
        return base
    try:
        # Import lazily to keep session persistence independent of handoff code.
        from coherence.planning.handoff import validate_handoff

        handoff_payload = validate_handoff(root, handoff)
    except (OSError, ValueError, TypeError, RuntimeError):
        base.update({"blocked": True, "reason": "HANDOFF_INVALID", "state": session.state})
        return base
    base.update({
        "blocked": False,
        "reason": None,
        "state": session.state,
        "run_identity": _run_identity(session),
        "selected_downstream_workflow": handoff_payload.get("selected_workflow"),
        "legal_next_actions": ["inspect-handoff", "revalidate-handoff"],
    })
    return base
```

- [ ] **Step 4: Run GREEN**

```bash
uv run pytest tests/unit/coherence/test_planning_session.py -q -o addopts=''
```

Expected: all tests pass, including all five new ones and the untouched `test_legal_actions_reject_stale_persisted_identity`.

- [ ] **Step 5: Run the broader planning regression suite**

```bash
uv run pytest tests/unit/coherence/test_planning_*.py -q -o addopts=''
```

Expected: same or better than this session's baseline (430 passed, 0 failed, 8 skipped) — no new failures. If `test_planning_guided.py` or `test_legal_actions_adapter.py` fail, read the failure before changing anything else: `legal_actions_adapter.py`'s `parse_legal_actions_projection()` validates shape only (any string list, any string-or-`None` reason), so a failure there means an actual contract break, not an expected update.

- [ ] **Step 6: Ruff and Pyright**

```bash
uv run ruff check src/coherence/planning/session.py tests/unit/coherence/test_planning_session.py
```
```bash
uv run pyright src/coherence/planning/session.py
```

Expected: both exit clean.

- [ ] **Step 7: Manually exercise the fix against this repo's own live, currently-stuck runs**

```bash
uv run coherence plan legal-actions --project-root . --run-id FEAT-003 --json
```
```bash
uv run coherence plan legal-actions --project-root . --run-id FEAT-3 --json
```

Expected: neither reports `SESSION_NOT_READY` anymore; each reports `state: capture` (both have a `capture_started` event and nothing else per this session's earlier inspection) and `legal_next_actions: ["capture-answer", "finalize-capture"]`. This is the concrete, observable proof that the bug CODEX_INTENT reported against this exact command is fixed, using this repo's own pre-existing stuck runs rather than a synthetic example.

- [ ] **Step 8: Commit**

```bash
git add src/coherence/planning/session.py tests/unit/coherence/test_planning_session.py
git commit -m "fix(planning): model capture and author/review progression in legal-actions"
```

---

## Self-review notes

- **Spec coverage:** grill Q1 (semantic IDs) → registry design in Task 3. Q2 (state after `finalize(provisional)`) → the `intent_provisional` branch in Task 3, bounded per "Explicitly out of scope." Q3 (one projection) → `legal_actions_session` remains the sole function touched. Q4 (concurrent run IDs) → Task 2, with a regression test proving the fix. Q5 (which tests) → the five new tests in Task 3 plus the concurrent-run test in Task 2. CODEX_INTENT's "Agreed capture behavior" (empty capture is normal, must not silently advance) → covered by `test_legal_actions_offer_capture_answer_and_finalize_with_no_open_challenges` exercising exactly the empty-capture case.
- **Placeholder scan:** every step has literal code, exact test names, and exact commands. Task 3's "Explicitly out of scope" section is a deliberate scope boundary stated once at the top, not a placeholder buried in a step.
- **Type/name consistency:** `_intent_path(root, run_id)` (Task 2) is called with the same two-argument signature everywhere it appears in Task 3's replacement `legal_actions_session` body. `_run_identity(session)` (introduced in Task 3) takes a `PlanningSession` and is used consistently in place of the three inline dict literals the current code repeats.
