# Curation Increment 1 — CLI Vocabulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `factory-requirements` the write vocabulary it never had — `bind`, `defer` — plus a closure gate (`check`) and a work queue (`next`), and stop `index` from laundering staleness.

**Architecture:** A new `factory.requirements.closure` module computes one requirement's state from existing loaders only. A new `factory.requirements.write` module owns every write, mirroring `factory.doctor.write`. `cli.py` grows subcommands that call them. Nothing else changes: no pipeline, no bundles, no navigator changes.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, python-frontmatter, pytest.

**Spec:** `docs/superpowers/specs/2026-08-10-curation-workflow-design.md`

## Global Constraints

- Requirement states are exactly: `measured-passing`, `measured-failing`, `planned`, `unmeasurable`, `declined`, `pending`. No others.
- Severity tiers reuse `factory.freshness.model.FreshnessSeverity`: `INTEGRITY`, `BLOCKING`, `WARNING`. No new enum.
- `pending` and stale are `BLOCKING`. `unmeasurable` is `WARNING`. Warnings never fail the gate.
- **Requirements are never exemptable.** `defer` only. `trace.gaps._disposition_of` already refuses to exempt `sr`/`br` nodes and this plan does not open a second route.
- A disposition is written as `trace_deferred: <reason>` in the requirement's own frontmatter — the field `trace.model._disposition` already reads. No new store.
- `defer` refuses an empty or whitespace-only reason.
- **`index` writes a checksum only where none exists.** A stale checksum is reported, never re-stamped.
- Staleness is cleared only by `bind` (new values) or `bind --reaffirm --reason` (statement changed, measurement still holds).
- `harness` is never validated against a registry. `bind` accepts a name, or nothing.
- Reuse existing loaders: `requirements.register`, `orchestrator.ledger`, `evidence.manifests`. No parallel parsing rules.
- Freshness is content-based, never mtime-based.
- All new tests are marked `pytestmark = pytest.mark.unit`.

## Verification discipline

`pyproject.toml` sets `addopts = "-m unit"`. Integration commands must pass `-m 'unit or integration'` or they collect nothing and exit green.

The `rtk` proxy has been observed misreporting pytest collection counts. Run anything collection-sensitive as `rtk proxy uv run pytest ...`.

---

## File Structure

**Create:**
- `src/factory/requirements/closure.py` — the state model: one requirement in, one state out
- `src/factory/requirements/write.py` — every write to a requirement file
- `tests/unit/requirements/test_closure.py`
- `tests/unit/requirements/test_write.py`

**Modify:**
- `src/factory/requirements/register.py` — `Binding.harness` becomes `str | None`
- `src/factory/requirements/cli.py` — `bind`, `defer`, `check`, `next` subcommands; fix `cmd_index`
- `tests/unit/requirements/test_register.py` — cover the optional harness
- `tests/unit/requirements/test_cli.py` — cover the new subcommands and the index fix

---

## Task 1: The harness becomes optional

`Binding.harness` is a required `str`. A requirement whose measurement is decided but whose instrument does not exist yet cannot be represented at all, so `bind` could never accept "not yet".

**Files:**
- Modify: `src/factory/requirements/register.py` (`Binding`, `_parse_binding`, `content_checksum`)
- Modify: `tests/unit/requirements/test_register.py`

**Interfaces:**
- Produces: `Binding.harness: str | None`, defaulting to `None`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/requirements/test_register.py`:

```python
def test_a_binding_may_name_no_harness_yet(tmp_path):
    path = tmp_path / "SR-050.md"
    path.write_text(
        "---\n"
        "id: SR-050\n"
        "title: No harness yet\n"
        'statement: "When X, the system shall Y."\n'
        "domain: behavioral\n"
        "upstream: []\n"
        "binding:\n"
        "  experiment: demo_experiment\n"
        "  metric: demo_rate\n"
        '  assert: ">= 0.90"\n'
        "---\nRationale.\n",
        encoding="utf-8",
    )
    req = parse_requirement(path)
    assert req.binding is not None
    assert req.binding.harness is None
    assert req.binding.metric == "demo_rate"


def test_an_absent_harness_does_not_change_an_existing_digest(tmp_path):
    """The canonical string uses `harness or ""`, so a real harness digests
    exactly as it did before this change. Guards against staling the register."""
    named = Binding(
        harness="demo-harness", experiment="e", metric="m", assert_expr=">= 1", trials=1, window=None
    )
    blank = Binding(
        harness=None, experiment="e", metric="m", assert_expr=">= 1", trials=1, window=None
    )
    req_named = Requirement(
        id="SR-001", title="t", statement="s", domain="behavioral", upstream=[],
        binding=named, body="", path=tmp_path / "SR-001.md",
    )
    req_blank = Requirement(
        id="SR-002", title="t", statement="s", domain="behavioral", upstream=[],
        binding=blank, body="", path=tmp_path / "SR-002.md",
    )
    assert content_checksum(req_named) != content_checksum(req_blank)
    assert content_checksum(req_named).startswith("sha256:")
```

Ensure the module imports `Binding`, `Requirement`, `content_checksum` and `parse_requirement` from `factory.requirements.register`; add only what is missing.

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/requirements/test_register.py -v`
Expected: FAIL — `KeyError: 'harness'` from `_parse_binding`.

- [ ] **Step 3: Write the implementation**

In `src/factory/requirements/register.py`, change the `Binding` field and reorder so defaulted fields stay last:

```python
@dataclass(frozen=True)
class Binding:
    experiment: str
    metric: str
    assert_expr: str
    # A requirement may have a decided measurement before its instrument exists.
    # `None` is the "no harness named yet" state -- a WARNING, never a blocker.
    harness: str | None = None
    trials: int = 1
    window: dict | None = None
    cadence: str = "every_iteration"
```

In `_parse_binding`, read it optionally:

```python
def _parse_binding(raw: dict) -> Binding:
    harness = raw.get("harness")
    return Binding(
        experiment=str(raw["experiment"]),
        metric=str(raw["metric"]),
        assert_expr=str(raw["assert"]),
        harness=str(harness) if harness else None,
        trials=int(raw.get("trials", 1)),
        window=raw.get("window"),
        cadence=str(raw.get("cadence", "every_iteration")),
    )
```

In `content_checksum`, substitute the empty string so existing digests are unchanged:

```python
    canonical = "\n".join(
        [
            req.statement.strip(),
            b.harness or "",
            b.experiment,
            b.metric,
            b.assert_expr,
            str(b.trials),
            repr(b.window),
        ]
    )
```

Every construction of `Binding(...)` elsewhere must now pass its arguments by keyword. Search for `Binding(` across `src` and `tests` and fix any positional call sites.

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/requirements -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/register.py tests/unit/requirements/test_register.py
git commit -m "feat(requirements): let a binding name no harness yet"
```

---

## Task 2: The closure state model

**Files:**
- Create: `src/factory/requirements/closure.py`
- Create: `tests/unit/requirements/test_closure.py`

**Interfaces:**
- Consumes: `factory.requirements.register.Requirement`, `is_checksum_current`
- Produces: `RequirementState` (a `str` `Enum` with members `MEASURED_PASSING = "measured-passing"`, `MEASURED_FAILING = "measured-failing"`, `PLANNED = "planned"`, `UNMEASURABLE = "unmeasurable"`, `DECLINED = "declined"`, `PENDING = "pending"`), `ClosureFinding` (frozen dataclass: `req_id: str`, `state: RequirementState`, `severity: FreshnessSeverity`, `detail: str`), and `classify(req, *, validation, linked_task_status, deferred_reason) -> ClosureFinding`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from factory.freshness.model import FreshnessSeverity
from factory.requirements.closure import RequirementState, classify
from factory.requirements.register import Binding, Requirement

pytestmark = pytest.mark.unit


def _req(tmp_path, *, binding=None, checksum=None, statement="When X, the system shall Y."):
    return Requirement(
        id="SR-001", title="t", statement=statement, domain="behavioral", upstream=[],
        binding=binding, body="", path=tmp_path / "SR-001.md", checksum=checksum,
    )


def _bound(harness="demo-harness"):
    return Binding(
        experiment="e", metric="m", assert_expr=">= 0.90", harness=harness, trials=1, window=None
    )


def _current(tmp_path, binding):
    from factory.requirements.register import content_checksum
    req = _req(tmp_path, binding=binding)
    return _req(tmp_path, binding=binding, checksum=content_checksum(req))


def test_a_passing_validation_result_is_measured_passing(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation="passing",
        linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.MEASURED_PASSING
    assert finding.severity is None, "a healthy state carries no severity"
    assert finding.req_id == "SR-001"


def test_a_failing_validation_result_is_legal_but_distinct(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation="failing",
        linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.MEASURED_FAILING, "a failing result is honest evidence"


def test_no_result_with_a_live_task_is_planned(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status="todo", deferred_reason=None,
    )
    assert finding.state is RequirementState.PLANNED


def test_no_result_with_a_done_task_is_pending_not_planned(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status="done", deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING, "a done task that produced nothing is not a plan"
    assert finding.severity is FreshnessSeverity.BLOCKING


def test_no_result_and_no_task_is_pending(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING


def test_an_unnamed_harness_is_unmeasurable_and_only_a_warning(tmp_path):
    finding = classify(
        _current(tmp_path, _bound(harness=None)), validation=None,
        linked_task_status="todo", deferred_reason=None,
    )
    assert finding.state is RequirementState.UNMEASURABLE
    assert finding.severity is FreshnessSeverity.WARNING, "an unnamed instrument never blocks"


def test_a_deferred_requirement_is_declined(tmp_path):
    finding = classify(
        _req(tmp_path), validation=None, linked_task_status=None,
        deferred_reason="no task delivers this yet",
    )
    assert finding.state is RequirementState.DECLINED
    assert "no task delivers this yet" in finding.detail


def test_an_unbound_requirement_with_no_disposition_is_pending(tmp_path):
    finding = classify(
        _req(tmp_path), validation=None, linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING
    assert finding.severity is FreshnessSeverity.BLOCKING


def test_a_stale_checksum_is_pending_whatever_else_is_true(tmp_path):
    stale = _req(tmp_path, binding=_bound(), checksum="sha256:0000")
    finding = classify(
        stale, validation="passing", linked_task_status="todo", deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING, "a stale binding may no longer measure the statement"
    assert finding.severity is FreshnessSeverity.BLOCKING
    assert "stale" in finding.detail.lower()


def test_a_deferral_wins_over_pending_but_not_over_a_real_result(tmp_path):
    declined = classify(
        _req(tmp_path), validation=None, linked_task_status=None, deferred_reason="later",
    )
    measured = classify(
        _current(tmp_path, _bound()), validation="passing",
        linked_task_status=None, deferred_reason="later",
    )
    assert declined.state is RequirementState.DECLINED
    assert measured.state is RequirementState.MEASURED_PASSING, "evidence outranks a deferral"
```

Add these two assertions to the healthy-state tests as well, so the severity policy is pinned everywhere rather than in one place:

```python
def test_healthy_states_carry_no_severity(tmp_path):
    planned = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status="todo", deferred_reason=None,
    )
    declined = classify(
        _req(tmp_path), validation=None, linked_task_status=None, deferred_reason="later",
    )
    assert planned.severity is None
    assert declined.severity is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/requirements/test_closure.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.requirements.closure'`

- [ ] **Step 3: Write the implementation**

`closure.py` holds the decision order and nothing else — no I/O, no loaders. `classify` takes already-resolved inputs so it stays a pure function and the caller owns the reading.

The decision order, which the tests pin:

1. binding present and checksum **not** current → `PENDING`, `BLOCKING`, detail names the staleness
2. a validation result exists → `MEASURED_PASSING` or `MEASURED_FAILING` (evidence outranks a deferral)
3. binding present and `harness is None` → `UNMEASURABLE`, `WARNING`
4. `deferred_reason` set → `DECLINED`, detail carries the reason
5. binding present, a linked task exists and its status is not `"done"` → `PLANNED`
6. anything else → `PENDING`, `BLOCKING`

`ClosureFinding.severity` is `FreshnessSeverity | None`: `BLOCKING` for `PENDING`, `WARNING` for `UNMEASURABLE`, and **`None` for every healthy state** (`MEASURED_PASSING`, `MEASURED_FAILING`, `PLANNED`, `DECLINED`). A healthy state is not a finding about anything, and giving it a severity would force every report to filter one out. `check` fails on `BLOCKING` and prints `WARNING`.

`MEASURED_FAILING` carrying no severity is deliberate and worth stating: a failing measurement is a healthy *closure* state — the requirement is bound, current and genuinely measured. That the system fails its own requirement is a fact for the validation report to raise, not a defect in the register's structure. Conflating the two would make an honest failing test look like a bookkeeping error.

`validation` is `"passing" | "failing" | None`. `linked_task_status` is the task's `status` string or `None`. `deferred_reason` is the `trace_deferred` string or `None`.

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/requirements -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/closure.py tests/unit/requirements/test_closure.py
git commit -m "feat(requirements): add the closure state model"
```

---

## Task 3: The write module

Every write to a requirement file goes through one place, mirroring `factory.doctor.write`.

**Files:**
- Create: `src/factory/requirements/write.py`
- Create: `tests/unit/requirements/test_write.py`

**Interfaces:**
- Consumes: `factory.requirements.register.parse_requirement`, `content_checksum`
- Produces: `write_binding(path, *, experiment, metric, assert_expr, harness, trials, window) -> None`, `reaffirm(path, reason) -> None`, `write_deferral(path, reason) -> None`, and `ReasonRequiredError(ValueError)`

- [ ] **Step 1: Write the failing test**

```python
import frontmatter
import pytest
from factory.requirements.register import is_checksum_current, parse_requirement
from factory.requirements.write import (
    ReasonRequiredError,
    reaffirm,
    write_binding,
    write_deferral,
)

pytestmark = pytest.mark.unit

_PROPOSED = """---
id: SR-009
title: Proposed requirement
statement: "When the zone clears, the system shall resume patrol."
domain: behavioral
upstream: []
---
Rationale.
"""


def _write(tmp_path, text=_PROPOSED, name="SR-009.md"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_write_binding_stamps_a_current_checksum(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="zone_clear", metric="resume_rate", assert_expr=">= 0.95",
        harness="sim-testbench", trials=3, window=None,
    )
    req = parse_requirement(path)
    assert req.binding is not None
    assert req.binding.harness == "sim-testbench"
    assert req.binding.metric == "resume_rate"
    assert is_checksum_current(req), "a freshly written binding is never stale"


def test_write_binding_accepts_no_harness(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="zone_clear", metric="resume_rate", assert_expr=">= 0.95",
        harness=None, trials=1, window=None,
    )
    req = parse_requirement(path)
    assert req.binding.harness is None
    assert is_checksum_current(req)


def test_write_binding_preserves_the_body_and_other_fields(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness=None, trials=1, window=None,
    )
    post = frontmatter.load(str(path))
    assert "Rationale." in post.content
    assert post["title"] == "Proposed requirement"


def test_reaffirm_makes_a_stale_requirement_current_again(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness="h", trials=1, window=None,
    )
    post = frontmatter.load(str(path))
    post["statement"] = "When the zone clears, the system shall resume patrol PROMPTLY."
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    assert not is_checksum_current(parse_requirement(path))

    reaffirm(path, "wording clarified; the measurement is unchanged")

    assert is_checksum_current(parse_requirement(path))
    assert "wording clarified" in path.read_text(encoding="utf-8")


def test_reaffirm_without_a_reason_is_refused(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness="h", trials=1, window=None,
    )
    with pytest.raises(ReasonRequiredError):
        reaffirm(path, "   ")


def test_write_deferral_uses_the_field_trace_already_reads(tmp_path):
    path = _write(tmp_path)
    write_deferral(path, "no current task delivers this")
    post = frontmatter.load(str(path))
    assert post["trace_deferred"] == "no current task delivers this"


def test_write_deferral_refuses_a_blank_reason(tmp_path):
    path = _write(tmp_path)
    with pytest.raises(ReasonRequiredError):
        write_deferral(path, "")


def test_a_deferral_does_not_stale_a_bound_requirement(tmp_path):
    path = _write(tmp_path)
    write_binding(
        path, experiment="e", metric="m", assert_expr=">= 1", harness="h", trials=1, window=None,
    )
    write_deferral(path, "still open")
    assert is_checksum_current(parse_requirement(path)), "a disposition is not a metric input"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/requirements/test_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.requirements.write'`

- [ ] **Step 3: Write the implementation**

Follow `src/factory/doctor/write.py` — read it first and match its idiom, including its comment that the file is re-read so the checksum covers exactly what is on disk.

- `write_binding` loads the post, sets `post["binding"]` to a dict with keys `experiment`, `metric`, `assert`, `trials`, and `harness`/`window` only when not `None` (an absent key is how "no harness" is represented — never `harness: null`), writes the file, then re-reads it and stamps `post["checksum"] = content_checksum(parse_requirement(path))` in a second write.
- `reaffirm` raises `ReasonRequiredError` on a blank reason, otherwise re-stamps the checksum the same way and records the reason. Store it as `reaffirmed: {reason: <str>, at: <ISO-8601 UTC>}` so a later reader can see the binding was re-judged rather than silently re-stamped. Use `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`, matching `orchestrator/human_review.py:_now`.
- `write_deferral` raises `ReasonRequiredError` on a blank reason, otherwise sets `post["trace_deferred"]`. It never touches the checksum.
- `ReasonRequiredError` subclasses `ValueError`, mirroring how `BundleIdMismatchError` subclasses `ValueError` so existing handling still catches it.

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/requirements -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/write.py tests/unit/requirements/test_write.py
git commit -m "feat(requirements): add the write module for bindings and deferrals"
```

---

## Task 4: Stop `index` laundering staleness

`cmd_index` recomputes and writes every bound requirement's checksum unconditionally and reports `"stale": False` regardless. Editing a statement — the event the checksum exists to catch — is silently re-stamped as current by the next routine `index` run.

**Files:**
- Modify: `src/factory/requirements/cli.py` (`cmd_index`)
- Modify: `tests/unit/requirements/test_cli.py`

**Interfaces:**
- Produces: `cmd_index` returns `{"requirements": [...]}` where a stale entry is `{"id", "checksum", "stale": True}` and its file is left untouched

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/requirements/test_cli.py`:

```python
def test_index_refuses_to_relaunder_a_stale_checksum(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    stamped = path.read_text(encoding="utf-8")

    text = stamped.replace("shall do Y", "shall do Y NOW")
    path.write_text(text, encoding="utf-8")

    result = cmd_index(tmp_path)

    entry = next(r for r in result["requirements"] if r["id"] == "SR-001")
    assert entry["stale"] is True, "index must report staleness, never absorb it"
    assert path.read_text(encoding="utf-8") == text, "a stale file is left exactly as found"
    assert "STALE" in cmd_status(tmp_path), "the signal survives an index run"


def test_index_still_stamps_a_requirement_that_has_no_checksum(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    result = cmd_index(tmp_path)
    entry = next(r for r in result["requirements"] if r["id"] == "SR-001")
    assert entry["stale"] is False
    assert entry["checksum"].startswith("sha256:")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/requirements/test_cli.py -v -k index`
Expected: FAIL — `assert False is True`, because `cmd_index` re-stamps and reports `stale: False`.

- [ ] **Step 3: Write the implementation**

Replace the body of the loop in `cmd_index`:

```python
def cmd_index(requirements_dir: Path) -> dict:
    out: list[dict] = []
    for req in load_register(requirements_dir):
        if req.binding is None:
            # Proposed: nothing to checksum, and rewriting the file would only
            # churn its formatting.
            out.append({"id": req.id, "checksum": None, "proposed": True})
            continue
        checksum = content_checksum(req)
        if req.checksum is None:
            # First stamp for a newly bound requirement.
            post = frontmatter.load(str(req.path))
            post["checksum"] = checksum
            req.path.write_text(frontmatter.dumps(post), encoding="utf-8")
            out.append({"id": req.id, "checksum": checksum, "stale": False})
            continue
        if req.checksum == checksum:
            out.append({"id": req.id, "checksum": checksum, "stale": False})
            continue
        # Stale. Re-stamping here would launder the one signal that says the
        # statement moved and nobody re-judged whether the binding still
        # measures it. Report and leave the file exactly as found; only `bind`
        # or `bind --reaffirm` may clear it.
        out.append({"id": req.id, "checksum": req.checksum, "stale": True})
    result = {"requirements": out}
    (requirements_dir / "index.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result
```

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/requirements -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/cli.py tests/unit/requirements/test_cli.py
git commit -m "fix(requirements): stop index laundering a stale checksum"
```

---

## Task 5: The `bind` and `defer` subcommands

**Files:**
- Modify: `src/factory/requirements/cli.py`
- Modify: `tests/unit/requirements/test_cli.py`

**Interfaces:**
- Consumes: `factory.requirements.write.write_binding`, `reaffirm`, `write_deferral`, `ReasonRequiredError`
- Produces: `cmd_bind(requirements_dir, req_id, *, experiment, metric, assert_expr, harness, trials, reaffirm_reason) -> str` and `cmd_defer(requirements_dir, req_id, reason) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_bind_writes_a_measurement_and_reports_it(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness="sim-testbench", trials=3, reaffirm_reason=None,
    )
    assert "SR-009" in out
    assert "sim-testbench" in out
    assert "[proposed]" not in cmd_status(tmp_path)


def test_bind_accepts_no_harness_and_says_so(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness=None, trials=1, reaffirm_reason=None,
    )
    assert "no harness" in out.lower()


def test_bind_on_an_unknown_id_is_reported_not_raised(tmp_path):
    assert "not found" in cmd_bind(
        tmp_path, "SR-999", experiment="e", metric="m", assert_expr=">= 1",
        harness=None, trials=1, reaffirm_reason=None,
    )


def test_defer_records_the_reason_where_trace_reads_it(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_defer(tmp_path, "SR-009", "no current task delivers this")
    assert "SR-009" in out
    assert "trace_deferred: no current task delivers this" in (
        tmp_path / "SR-009.md"
    ).read_text(encoding="utf-8")


def test_defer_with_a_blank_reason_is_refused(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert "reason" in cmd_defer(tmp_path, "SR-009", "   ").lower()


def test_main_wires_bind_and_defer(tmp_path, capsys):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    rc = main([
        "bind", "SR-009", "--requirements-dir", str(tmp_path),
        "--experiment", "zone_clear", "--metric", "resume_rate", "--assert", ">= 0.95",
    ])
    assert rc == 0
    assert "SR-009" in capsys.readouterr().out
    rc = main(["defer", "SR-009", "--requirements-dir", str(tmp_path), "--reason", "later"])
    assert rc == 0
```

Import `cmd_bind` and `cmd_defer` alongside the existing imports at the top of the file.

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/requirements/test_cli.py -v -k "bind or defer"`
Expected: FAIL — `ImportError: cannot import name 'cmd_bind'`

- [ ] **Step 3: Write the implementation**

Both commands resolve `requirements_dir / f"{req_id}.md"` and return `f"not found: {req_id}"` when it does not exist, matching `cmd_show`'s existing idiom — a missing id is reported, never raised.

`cmd_bind` calls `write_binding`, or `reaffirm` when `reaffirm_reason` is not `None`, and returns a one-line summary naming the id, the harness (or the words `no harness named yet`), the metric and the assertion. `cmd_defer` calls `write_deferral` and returns the id and reason; it catches `ReasonRequiredError` and returns a message containing the word `reason`.

Argparse wiring in `main`, using the existing `common` parent so `--requirements-dir` is accepted after the subcommand:

```python
    p_bind = sub.add_parser("bind", parents=[common])
    p_bind.add_argument("id")
    p_bind.add_argument("--experiment", required=True)
    p_bind.add_argument("--metric", required=True)
    p_bind.add_argument("--assert", dest="assert_expr", required=True)
    p_bind.add_argument("--harness", default=None)
    p_bind.add_argument("--trials", type=int, default=1)
    p_bind.add_argument("--reaffirm", dest="reaffirm_reason", default=None)

    p_defer = sub.add_parser("defer", parents=[common])
    p_defer.add_argument("id")
    p_defer.add_argument("--reason", required=True)
```

`--harness` deliberately has no `required=True` and no registry check: omitting it is the supported "not yet" answer.

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/requirements -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/cli.py tests/unit/requirements/test_cli.py
git commit -m "feat(requirements): add the bind and defer subcommands"
```

---

## Task 6: The `check` gate and the `next` queue

**Files:**
- Modify: `src/factory/requirements/cli.py`
- Modify: `tests/unit/requirements/test_cli.py`

**Interfaces:**
- Consumes: `factory.requirements.closure.classify`, `RequirementState`, `ClosureFinding`; `factory.orchestrator.ledger.load_tasks`; `factory.evidence.manifests.list_run_manifests`
- Produces: `cmd_check(project_root) -> tuple[str, int]` and `cmd_next(project_root) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_check_fails_on_a_pending_requirement_and_says_why(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    report, code = cmd_check(tmp_path)
    assert code == 1, "an undecided requirement fails the gate"
    assert "SR-009" in report
    assert "pending" in report.lower()


def test_check_passes_when_every_requirement_is_decided(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    cmd_defer(tmp_path / "requirements", "SR-009", "no task delivers this yet")
    report, code = cmd_check(tmp_path)
    assert code == 0
    assert "0 pending" in report


def test_an_unmeasurable_requirement_warns_without_failing(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    cmd_bind(
        tmp_path / "requirements", "SR-009", experiment="e", metric="m",
        assert_expr=">= 1", harness=None, trials=1, reaffirm_reason=None,
    )
    report, code = cmd_check(tmp_path)
    assert code == 0, "an unnamed harness is a warning, never a blocker"
    assert "unmeasurable" in report.lower()
    assert "SR-009" in report


def test_check_reports_a_stale_requirement_as_blocking(tmp_path):
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    path = _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    path.write_text(
        path.read_text(encoding="utf-8").replace("shall do Y", "shall do Y NOW"), encoding="utf-8"
    )
    report, code = cmd_check(tmp_path)
    assert code == 1
    assert "SR-001" in report


def test_next_names_the_first_undecided_requirement(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    out = cmd_next(tmp_path)
    assert "SR-009" in out
    assert "When the zone clears" in out, "the statement is what the judgment is made against"


def test_next_says_so_when_nothing_is_open(tmp_path):
    (tmp_path / "requirements").mkdir()
    assert "nothing" in cmd_next(tmp_path).lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/requirements/test_cli.py -v -k "check or next"`
Expected: FAIL — `ImportError: cannot import name 'cmd_check'`

- [ ] **Step 3: Write the implementation**

Both take a **project root**, not a requirements dir, because they need tasks and evidence too. They read `project_root / "requirements"`, `project_root / "tasks"` and `project_root / "evidence"`.

For each requirement, resolve the three inputs and call `classify`:

- `deferred_reason` — `trace_deferred` from the requirement's frontmatter, read via `frontmatter.load`.
- `linked_task_status` — scan `load_tasks(project_root / "tasks")` for a task whose `satisfies` contains this requirement id; take the status of the first match, or `None`. Prefer a task that is not `done` when several match, so one stale done task cannot mask a live one.
- `validation` — scan `list_run_manifests(project_root / "evidence")` for `validation` entries naming this id. `"failing"` if any entry has `passed` false, else `"passing"` if any entry names it, else `None`. Never read the `report` blob.

`cmd_check` mirrors `trace.cli.cmd_check`'s shape exactly: a summary line, then a blocking section headed with the note that the gate fails on these, then a warning section. It returns `(report, 1 if any BLOCKING else 0)`. Read `src/factory/trace/cli.py:43-66` and follow it — the two reports should look like siblings.

`cmd_next` returns the first `PENDING` requirement's id, title and statement, plus the ids of any tasks that mention it as a candidate, or a line containing `nothing` when there are none.

Wire both into `main` with a `--project-root` argument defaulting to `Path(".")`, matching `trace.cli._add_root`. `main` returns the exit code from `cmd_check`.

- [ ] **Step 4: Run the suite and static checks**

Run: `rtk proxy uv run pytest tests/unit -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 5: Run the check against the real drone register**

Run: `cd ../cool_physical_ai_project && uv run python -m factory.requirements check`
Expected: a non-zero exit naming a large number of pending requirements — this is the first time the register's real state is reported. Record the actual counts in the task report. Do **not** fix them; this increment builds the instrument, not the content.

- [ ] **Step 6: Commit**

```bash
git add src/factory/requirements/cli.py tests/unit/requirements/test_cli.py
git commit -m "feat(requirements): add the closure gate and the decision queue"
```

---

## Plan self-review

**Spec coverage.** §3.1 states → Task 2. §3.2 staleness and the `index` defect → Tasks 3 and 4. §3.3 optional harness → Tasks 1, 3 and 5. §4 `bind`/`bind --reaffirm` → Tasks 3 and 5; `defer` → Tasks 3 and 5; `check`/`next` → Task 6; `index` fix → Task 4. §4's "requirements are never exemptable" → no `exempt` verb appears in any task. §4's disposition storage → Task 3's `write_deferral` uses `trace_deferred`. §5 pipeline → Increment 3, out of scope. §3.4 bundles → Increment 2, out of scope.

**Type consistency.** `Binding.harness: str | None` is defined in Task 1 and consumed in Tasks 2, 3 and 5. `RequirementState` and `ClosureFinding` are defined in Task 2 and consumed in Task 6. `write_binding`/`reaffirm`/`write_deferral`/`ReasonRequiredError` are defined in Task 3 and consumed in Task 5. `cmd_bind`/`cmd_defer` are defined in Task 5 and used by Task 6's tests. `classify`'s three inputs — `validation`, `linked_task_status`, `deferred_reason` — have the same names and types in Task 2's tests, Task 2's implementation and Task 6's resolution logic.

**Known gap carried from the spec.** `measured-failing` has no observed example anywhere: no requirement in any repository has a failing validation result, because only SR-001 is bound at all. Task 2 tests it with a constructed `validation="failing"` input, which is legitimate because `classify` is a pure function over that input — but the *resolution* logic in Task 6, which decides when to pass `"failing"`, is exercised only against a manifest shape observed once, in a passing state. The executor must record this as unproven rather than claim coverage it does not have.

**One deliberate omission.** Task 1 reorders `Binding`'s fields so defaulted ones stay last, which breaks any positional `Binding(...)` construction. Task 1 Step 3 says to find and fix those call sites rather than listing them, because the list depends on the tree at execution time; `rtk proxy uv run pytest tests/unit -q` in Task 1 Step 4 is what proves none was missed.
