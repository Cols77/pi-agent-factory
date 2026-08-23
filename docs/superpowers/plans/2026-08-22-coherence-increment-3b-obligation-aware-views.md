# Coherence Increment 3B: Obligation-Aware Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the already-shipped navigator, presentation, goal and simulation views (Increment
3) a way to show a scope's effective profile and compiled obligations, and explain in plain words
why any one obligation applies — the "why required" projection spec §4 requires alongside the
`Obligation` contract itself.

**Architecture (corrected — see review round finding #5):** The real code map is NOT "present/
goal/sim are navigator subcommands, not separate untouched packages" for every consumer. It is
two genuinely separate CLI entry points wrapping the same underlying data, plus two more
lower-traffic ones this plan makes a real, stated decision about:

- `coherence.navigate.cli` (`python -m factory.system`, a deprecated-shim-forwarded alias) owns
  `present`/`goal show`/`sim run` as its own subcommands, dispatched from `main()` in that file.
  The docs-server's `coherence.navigate.worker` is a separate JSON-lines surface: its current
  handler table exposes `goal_show` and `sim_run` (`src/coherence/navigate/worker.py`), but it has
  **no `present` handler**. The browser's `/api/system/goal` and `/api/system/sim/run` routes may
  therefore reach those navigate handlers; this plan does not invent a worker presentation route.
  The CLI surface is covered by the existing `tests/unit/system/test_cli.py` (`from
  factory.system.cli import main`, through the deprecated shim).
- `coherence.presentation.cli` (`python -m factory.presentation`, also shim-forwarded) is a
  **separate module** with its own `present` command and its own `main()`. This is the module the
  pi extension's `eng_present` tool actually invokes: `pi-ext/factory-watch/src/system-cli.ts`
  `buildPresentationCommand` runs `python -m factory.presentation`, not `factory.system`, and
  `loadSystemPresent` (the function backing `eng_present`) calls through it exclusively. The
  current call chain is `eng-context-tools.ts::engPresent.execute` -> `deps.present` ->
  `system-cli.ts::loadSystemPresent` -> `buildPresentationCommand` -> `factory.presentation`,
  then `eng-context-tool-format.ts::formatPresent`. A flag added only to
  `coherence.navigate.cli` therefore cannot reach live `eng_present`. **This plan adds
  `--why-required` to BOTH Python `present` commands and propagates it through that full
  TypeScript chain** (Task 2 and Task 4); the shared implementation remains
  `coherence.navigate.obligations.present_obligations`, so scope gating and policy-error handling
  are not duplicated.
- `coherence.goals.cli` (`python -m factory.goals`, shim-forwarded) is **also a separate module**
  with its own `show` command — and it too is real, live-invoked user-facing surface: the pi
  extension's `/goal` slash command (`pi-ext/factory-watch/src/index.ts`, `pi.registerCommand
  ("goal", ...)`) spawns `uv run python -m factory.goals <args> --json` directly, so `/goal show
  <id>` never goes through `coherence.navigate.cli`'s `goal show` at all. **Decision, made
  explicitly rather than left open (review finding #5's second half): this plan also adds
  `obligations_open`/`obligations_error` to `coherence.goals.cli`'s `show` command** (Task 5),
  reusing the same `coherence.navigate.obligations.obligations_open_count` helper Task 3 uses for
  `coherence.navigate.cli`'s `goal show`/`sim run` — real, low-cost, and closes the same gap for a
  verified real caller.
- `coherence.simulation.cli` (`python -m factory.simulation`) is the fourth separate module
  (`runs`/`sensitivity` subcommands — there is no singular `run` subcommand there at all, unlike
  `coherence.navigate.cli`'s `sim run`). **Decision: this plan does NOT touch it.** A repo-wide
  search of `pi-ext/factory-watch/src/` for `factory.simulation`/`coherence.simulation` found no
  call site — nothing in the extension invokes it, unlike `factory.goals` (`/goal`) and
  `factory.presentation` (`eng_present`). `coherence.navigate.cli`'s `sim run` (Task 3, reached via
  the docs-server worker) is judged sufficient, intentionally-scoped coverage for `run:` obligation
  data until a real caller of `coherence.simulation.cli` appears; extending an unreached module
  would be speculative, not corrective.

The composed obligation logic itself lives in one new module, `coherence.navigate.obligations`,
which wraps Increment 2B's `coherence.policy.compiler` the same way every other navigator view
wraps a lower-layer loader (compare `coherence.navigate.health` composing `coherence.trace`).
Every CLI call site above is a thin, additive extension of that module's four functions
(`effective_profile_view`, `why_required`, `obligations_open_count`, `present_obligations`) — no
existing field on any of the four modified commands is renamed or removed.

**Tech Stack:** Python 3.11+, `argparse`, dataclasses.

## Dependencies and schedule

This increment is ordered **after Increment 2B and Increment 3**:

- Increment 2B Task 6/7 must land first. It creates the `substrate.policy` `Obligation` contract,
  the `InvalidProfileError`/`ProfileConflictError`/`UncompiledPresetError` vocabulary, and
  `coherence.policy.compiler.resolve_profile`/`compile_obligations` with the `nodes=`/`edges=`
  passthrough consumed here. 3B is a view/adapter over that compiler; it does not recreate or
  widen the policy taxonomy. Increment 2C may consume the same compiler in parallel only after
  2B's policy task is complete; it is not a prerequisite for 3B's views.
- Increment 3 must land before Tasks 2–5. Those tasks extend its shipped navigator,
  presentation, goals, simulation, worker, and pi-extension entry points; the source names and
  compatibility claims below are against those Increment 3 surfaces, not hypothetical modules.
- Within this plan, land Task 1 before Tasks 2–5. Increment 4/5/6 consumers must continue to use
  2B's single compiler; later obligation kinds are appended there and are picked up by this plan's
  fixed ordering fallback without a second source of truth.

The public boundary is deliberate: direct `obligations` projection failures are structured
command/worker errors, while optional obligation enrichment on `present`, `goal show`, and
`sim run` degrades only that additive field. Neither path converts an invalid, conflicting, or
known-but-uncompiled profile into an empty successful obligation set.

**Run-scope boundary for this increment:** `load_nodes` currently exposes no `run` nodes, so 3B
does not claim a real `run:<id>` policy scope. `obligations_open_count(root, "run:<id>")` returns
`(0, "policy scope unsupported for 'run:<id>': load_nodes exposes no run nodes")`, and
`sim run` preserves its base result while explicitly degrading the additive obligation fields to
`obligations_open: 0` plus that `obligations_error`. **Open decision requiring approval:** whether a
later increment should add a trace-node/run-scope contract and then enable run-specific policy
resolution; doing so is outside 3B.

**Spec:** `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (§4
"Compiled Obligation" and the "why required" projection language, §10 disposition row for 3B).

## Global Constraints

- Every JSON field this plan adds to an existing command's result is additive; no existing key
  changes shape or is removed.
- `coherence.navigate` may import `coherence.policy` and `coherence.trace` (already-established
  layering: navigator composes lower coherence packages and substrate; it is never imported back
  by them).
- `coherence.goals.cli` importing `coherence.navigate.obligations` (Task 5) is layering-legal by
  existing precedent, not a new rule: `coherence.presentation.router` already imports
  `coherence.navigate.queries`, and `coherence.navigate.cli` already imports
  `coherence.goals.registry` — cross-package imports within `coherence` are already established in
  shipped code. `coherence.navigate.obligations` itself never imports `coherence.goals` or
  `coherence.presentation`, so there is no import cycle (verified against every module this plan
  touches).
- Python 3.11–3.12, Ruff line-length 100, Pyright standard mode (AGENTS.md).

---

## File Structure

**Create:**
- `src/coherence/navigate/obligations.py` — `effective_profile_view`, `why_required`,
  `obligations_open_count`, `present_obligations`
- `tests/unit/coherence/test_navigate_obligations.py` — matches this repo's REAL, verified
  convention for testing a `coherence.navigate.<module>` unit in isolation: flat files directly
  under `tests/unit/coherence/` (e.g. `tests/unit/coherence/test_navigate_bundles.py` tests
  `coherence.navigate.bundles`, `test_navigate_actions.py` tests navigate action helpers) — never
  `tests/unit/coherence/navigate/`, which does not exist anywhere in this repo. No new
  `__init__.py` needed: `tests/unit/coherence/__init__.py` already exists and already covers this
  directory.

**Modify:**
- `src/coherence/navigate/cli.py` — `cmd_obligations` (new, scope-guarded), `_render_obligations`
  (new); additive fields on `cmd_present`/`_render_present` and `cmd_goal_show`/`cmd_sim_run`
- `tests/unit/system/test_cli.py` — the REAL, existing file covering `cmd_present`/`cmd_goal_show`/
  `cmd_sim_run`/`main` for `coherence.navigate.cli` (imports `from factory.system.cli import
  main`, the deprecated-shim alias `coherence.navigate.cli` sits behind). This plan's Task 2/Task 3
  tests are appended here, matching the existing `test_present_routes_to_router`/
  `test_goal_show_and_list_subcommands`/`test_sim_latest_returns_most_recent_run_for_feature` style
  already in the file (verified by reading all ~860 lines). `tests/unit/coherence/navigate/
  test_cli_obligations.py`, named in an earlier draft of this plan, is NOT used: that directory
  does not exist and `tests/unit/coherence/test_cli.py` (which DOES exist) covers the top-level
  `coherence` group dispatcher (`coherence.cli.GROUPS`), a different module entirely — not this
  file's target.
- `src/coherence/presentation/cli.py` — `--why-required` on its own `present` command (new Task 4;
  this is the module the pi extension's `eng_present` tool actually reaches — see Architecture)
- `tests/unit/presentation/test_cli.py` — the REAL, existing file covering
  `coherence.presentation.cli`'s `present` command (imports `from factory.presentation.cli import
  main`; verified by reading the whole file, 67 lines). Task 4's tests are appended here.
- `src/coherence/goals/cli.py` — `obligations_open`/`obligations_error` on `show` (new Task 5;
  reached by the pi extension's `/goal show` slash command — see Architecture)
- `tests/unit/goals/test_cli.py` — the REAL, existing file covering `coherence.goals.cli`
  (imports `from factory.goals.cli import main`; verified). Task 5's test is appended here. This
  directory has no `__init__.py` today (verified — unlike `tests/unit/coherence/`,
  `tests/unit/system/` and `tests/unit/presentation/`, which do) and none is added: only an
  existing, already-collected file is extended, so the directory's existing collection mechanism
  is untouched.
- `pi-ext/factory-watch/src/system-cli.ts` — `PresentResult`'s additive obligation fields and
  `loadSystemPresent(..., whyRequired)` flag propagation to `factory.presentation`
- `pi-ext/factory-watch/src/eng-context-tools.ts` — optional `why_required` TypeBox parameter and
  the `eng_present` -> `loadSystemPresent` forwarding call
- `pi-ext/factory-watch/src/eng-context-tool-format.ts` — safe rendering of the optional
  obligation/error/note fields without re-deriving Python data
- `pi-ext/factory-watch/test/system-cli.test.ts` — command-argument propagation coverage
- `pi-ext/factory-watch/test/eng-context-tools.test.ts` — tool-schema and forwarding coverage
- `pi-ext/factory-watch/test/eng-context-tool-format.test.ts` — formatter boundary coverage for
  optional obligation/error/note fields (new test file)
- `pi-ext/factory-watch/test/system-worker.test.ts` — worker boundary coverage for additive
  obligation fields and the explicit degraded/unsupported `sim run` result

---

### Task 1: `effective_profile_view`, `why_required`, `obligations_open_count`, `present_obligations`

**Files:**
- Create: `src/coherence/navigate/obligations.py`
- Test: `tests/unit/coherence/test_navigate_obligations.py`

**Interfaces:**
- Consumes: `coherence.policy.compiler.{resolve_profile, compile_obligations}` (Increment 2B,
  including its `nodes=`/`edges=` trace-graph passthrough params — used here to load the trace
  graph once per call instead of once inside `resolve_profile` and again inside
  `compile_obligations`, review finding: avoid double-compiling), `substrate.policy.vocabulary.
  UncompiledPresetError`, `substrate.policy.obligation.Obligation`, `coherence.trace.model.
  {load_nodes, extract_edges}`.
- Produces:
  - `effective_profile_view(root: Path, scope_ref: str = "project") -> dict` — unchanged shape
    from the original draft, EXCEPT each obligation dict now also carries `scope_ref` and
    `source_policy` (review finding #4: the projection was dropping 2 of the `Obligation`
    contract's 8 fields).
  - `why_required(root: Path, obligation_id: str, scope_ref: str = "project", *, obligations:
    list[Obligation] | None = None) -> str | None` — the optional `obligations` kwarg lets a
    caller that already compiled the obligation set (Task 2/4's `present_obligations`) pass it in
    instead of triggering a second `compile_obligations` call; omitting it reproduces the original
    behavior exactly (compiles fresh), so Task 1's own unit tests below are unchanged by this
    addition.
  - `obligations_open_count(root: Path, scope_ref: str, *, exclude_kinds: tuple[str, ...] =
    ("ci_verification",)) -> tuple[int, str | None]` — `(count, error)`. Counts compiled
    obligations at `scope_ref` with `requiredness in ("blocking", "required")` and `state ==
    "open"`, EXCLUDING `ci_verification` by default (review finding #3: `compile_obligations`
    unconditionally prepends a blocking, open `ci_verification` obligation to EVERY scope
    including `goal:`/`run:` ones, so without this exclusion the count is structurally always
    `>= 1` for every goal/run in every repo — a no-op that asserts nothing goal/run-specific;
    `ci_verification` is a project-level concern). Before calling 2B, validate that a non-project
    scope is a declared trace node of the requested kind. An unknown kind or unknown id returns
    `(0, error)` and never reaches 2B's project-default fallback. `error` is the stable exception
    text for `InvalidProfileError`, `ProfileConflictError`, or `UncompiledPresetError`, or for
    that missing scope; the count is `0` in every error case, but callers can distinguish
    "genuinely nothing open" from "policy/scope could not be resolved" (review finding #2).
    In particular, `run:<id>` returns the stable unsupported-scope error
    `policy scope unsupported for 'run:<id>': load_nodes exposes no run nodes`; it must not
    inherit project obligations while the trace loader has no run nodes.
    These policy-resolution errors are caught here because `goal show`/`sim run` preserve their
    base payload and degrade only the additive obligation fields.
  - `present_obligations(root: Path, scope_ref: str) -> dict` — the shared implementation behind
    BOTH `present --why-required` call sites (Task 2, Task 4). Returns `{"obligations": [...]}`
    with each blocking/required obligation's dict carrying a `"why"` key from `why_required`
    (review finding #1: `--why-required` must actually call `why_required`, not just attach
    `effective_profile_view`'s dicts unexplained); `{"obligations": None, "obligations_note": "no
    policy scope for this artifact kind"}` for any `scope_ref` whose kind is not one of `sr`,
    `task`, `feat`, `goal` (review finding #7: these are the only kinds `coherence.trace.model.
    load_nodes` actually loads as resolvable trace nodes among `router.py`'s `_BROWSER_KINDS` —
    `bundle`/`adr`/`metric` are browser-navigable but never appear as trace nodes 2B's
    `resolve_profile` can look up by id, and `file:`/a raw path/`RUN-*`/`catchup:` are not
    trace-node scopes at all; gating on this fixed allowlist also structurally fixes the Windows
    drive-letter collision, since `"C:\src\x.py".partition(":")[0] == "C"`, not a recognized
    kind, so it is correctly treated as "no policy scope" rather than misparsed); or
    `{"obligations": [], "obligations_error": "..."}` when
    `InvalidProfileError`, `ProfileConflictError`, or `UncompiledPresetError` is raised (review
    finding #2, same discipline as `obligations_open_count`). Unknown ids of an otherwise
    allowed kind take the same fail-closed no-scope result; they never compile project policy.
    `effective_profile_view` and the direct `obligations` command do not catch these policy
    errors: their existing CLI/worker boundary reports a structured non-zero error, as required
    for a primary projection rather than an optional enrichment.

- [ ] **Step 1: Write the failing tests.**

```python
import pytest
from pathlib import Path

from coherence.navigate.obligations import (
    effective_profile_view,
    obligations_open_count,
    present_obligations,
    why_required,
)

pytestmark = pytest.mark.unit


def _seed_gates(root: Path) -> None:
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n", encoding="utf-8",
    )


def _seed_sr(root: Path, sr_id: str = "SR-001") -> None:
    (root / "requirements").mkdir(exist_ok=True)
    (root / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n---\n", encoding="utf-8",
    )


def _seed_goal(root: Path, goal_id: str = "GOAL-001") -> None:
    (root / "goals").mkdir(exist_ok=True)
    (root / "goals" / f"{goal_id}.md").write_text(
        f"---\nid: {goal_id}\ntitle: t\nstate: PROPOSED\nfeature: []\n"
        "requirements: []\nmetric: null\ntarget: '>= 0.90'\n---\n",
        encoding="utf-8",
    )


# -- effective_profile_view --------------------------------------------------


def test_effective_profile_view_project_scope(tmp_path):
    _seed_gates(tmp_path)
    view = effective_profile_view(tmp_path, "project")
    assert view["scope_ref"] == "project"
    assert view["profile"] == "prototype"
    kinds = [o["kind"] for o in view["obligations"]]
    assert "ci_verification" in kinds
    ci = next(o for o in view["obligations"] if o["kind"] == "ci_verification")
    assert ci["requiredness"] == "blocking"
    # The full 8-field Obligation contract must survive the projection
    # (review finding #4 -- scope_ref and source_policy were being dropped).
    assert ci["scope_ref"] == "project"
    assert ci["source_policy"] == "prototype"
    assert set(ci.keys()) == {
        "id", "scope_ref", "kind", "requiredness", "reason", "source_policy", "state",
        "resolve_cmd",
    }


# -- why_required -------------------------------------------------------------


def test_why_required_explains_a_known_obligation(tmp_path):
    _seed_gates(tmp_path)
    view = effective_profile_view(tmp_path, "project")
    ob_id = view["obligations"][0]["id"]
    explanation = why_required(tmp_path, ob_id, "project")
    assert explanation is not None
    assert "prototype" in explanation


def test_why_required_unknown_id_returns_none(tmp_path):
    _seed_gates(tmp_path)
    assert why_required(tmp_path, "ob:does-not-exist", "project") is None


def test_why_required_accepts_precompiled_obligations(tmp_path):
    """The `obligations=` passthrough must answer identically to a fresh
    compile, so a caller that already has the list avoids a second
    compile_obligations() call."""
    from coherence.policy.compiler import compile_obligations

    _seed_gates(tmp_path)
    compiled = compile_obligations(tmp_path, "project")
    fresh = why_required(tmp_path, compiled[0].id, "project")
    passed_through = why_required(tmp_path, compiled[0].id, "project", obligations=compiled)
    assert fresh == passed_through


# -- obligations_open_count ----------------------------------------------------


def test_obligations_open_count_excludes_ci_verification_for_known_goal_scope(tmp_path):
    """ci_verification is compiled for EVERY scope including goal:/run: ones
    (2B D18) -- it must not make obligations_open_count structurally >= 1 for
    every goal/run in every repo (review finding #3)."""
    _seed_gates(tmp_path)
    _seed_goal(tmp_path)
    count, error = obligations_open_count(tmp_path, "goal:GOAL-001")
    assert count == 0
    assert error is None


def test_obligations_open_count_unknown_goal_fails_closed(tmp_path):
    _seed_gates(tmp_path)
    count, error = obligations_open_count(tmp_path, "goal:GOAL-DOES-NOT-EXIST")
    assert count == 0
    assert error == "no declared policy scope for 'goal:GOAL-DOES-NOT-EXIST'"


def test_obligations_open_count_marks_run_scope_unsupported(tmp_path):
    """The current trace loader has no run nodes; do not claim run policy
    resolution by falling back to the project profile."""
    _seed_gates(tmp_path)
    count, error = obligations_open_count(tmp_path, "run:RUN-3")
    assert count == 0
    assert error == (
        "policy scope unsupported for 'run:RUN-3': load_nodes exposes no run nodes"
    )


def test_obligations_open_count_surfaces_uncompiled_preset_error(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    count, error = obligations_open_count(tmp_path, "project")
    assert count == 0
    assert error is not None
    assert "exploration" in error


# -- present_obligations --------------------------------------------------------


def test_present_obligations_attaches_why_for_relevant_obligations(tmp_path):
    """Blocking finding #1: --why-required must actually call why_required,
    not just attach effective_profile_view's dicts unexplained."""
    _seed_gates(tmp_path)
    _seed_sr(tmp_path)
    result = present_obligations(tmp_path, "sr:SR-001")
    assert result["obligations"] is not None
    ci = next(o for o in result["obligations"] if o["kind"] == "ci_verification")
    assert ci["why"] is not None
    assert "prototype" in ci["why"]


def test_present_obligations_none_for_non_scope_artifact_kind(tmp_path):
    """file:/a raw path/RUN-*/catchup: never resolve to a real trace-node
    policy scope -- must not silently mislabel project-default obligations
    as if they were that artifact's own (review finding #7)."""
    result = present_obligations(tmp_path, "file:.factory/factory.yaml")
    assert result == {"obligations": None, "obligations_note": "no policy scope for this artifact kind"}


def test_present_obligations_none_for_unknown_goal(tmp_path):
    result = present_obligations(tmp_path, "goal:GOAL-DOES-NOT-EXIST")
    assert result == {"obligations": None, "obligations_note": "no declared policy scope"}


def test_present_obligations_rejects_windows_path_looking_like_a_scope(tmp_path):
    """A Windows absolute path contains ':' (C:\\...) and must not be
    misparsed as scope kind 'C' (review finding #7a)."""
    result = present_obligations(tmp_path, "C:\\src\\x.py")
    assert result == {"obligations": None, "obligations_note": "no policy scope for this artifact kind"}


def test_present_obligations_surfaces_uncompiled_preset_error(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    _seed_sr(tmp_path)
    result = present_obligations(tmp_path, "sr:SR-001")
    assert result["obligations"] == []
    assert result["obligations_error"] is not None


@pytest.mark.parametrize("error_type", [
    "InvalidProfileError",
    "ProfileConflictError",
    "UncompiledPresetError",
])
def test_present_obligations_degrades_all_policy_resolution_errors(tmp_path, monkeypatch, error_type):
    """Optional enrichment reports every 2B policy-resolution failure in its
    additive error field; none is converted into a successful empty view."""
    from coherence.navigate import obligations as module
    from substrate.policy import vocabulary

    _seed_sr(tmp_path)
    error = getattr(vocabulary, error_type)("policy cannot be resolved")
    monkeypatch.setattr(module, "_compile", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    result = module.present_obligations(tmp_path, "sr:SR-001")
    assert result == {"obligations": [], "obligations_error": "policy cannot be resolved"}


def test_effective_profile_view_has_fixed_future_safe_order(tmp_path, monkeypatch):
    from coherence.navigate import obligations as module
    from substrate.policy.obligation import Obligation

    _seed_gates(tmp_path)
    values = [
        Obligation("ob:z", "project", "human_review", "required", "z", "prototype", "open", None),
        Obligation("ob:a", "project", "ci_verification", "blocking", "a", "prototype", "open", None),
        Obligation("ob:b", "project", "task_justification", "advisory", "b", "prototype", "open", None),
    ]
    monkeypatch.setattr(module, "compile_obligations", lambda *_args, **_kwargs: values)
    view = module.effective_profile_view(tmp_path, "project")
    assert [ob["kind"] for ob in view["obligations"]] == [
        "ci_verification", "task_justification", "human_review"
    ]


def test_effective_profile_view_orders_unknown_kinds_after_known_deterministically(tmp_path, monkeypatch):
    """Unknown future kinds use the fallback rank, then kind/scope/id, so
    adding a new compiler kind cannot disturb the established order."""
    from coherence.navigate import obligations as module
    from substrate.policy.obligation import Obligation

    _seed_gates(tmp_path)
    values = [
        Obligation("ob:z2", "task:T-2", "z_future", "required", "z2", "prototype", "open", None),
        Obligation("ob:a", "task:T-1", "a_future", "required", "a", "prototype", "open", None),
        Obligation("ob:z1", "task:T-1", "z_future", "required", "z1", "prototype", "open", None),
        Obligation("ob:human", "project", "human_review", "required", "h", "prototype", "open", None),
        Obligation("ob:ci", "project", "ci_verification", "blocking", "c", "prototype", "open", None),
    ]
    monkeypatch.setattr(module, "compile_obligations", lambda *_args, **_kwargs: values)
    view = module.effective_profile_view(tmp_path, "project")
    assert [
        (ob["kind"], ob["scope_ref"], ob["id"])
        for ob in view["obligations"]
    ] == [
        ("ci_verification", "project", "ob:ci"),
        ("human_review", "project", "ob:human"),
        ("a_future", "task:T-1", "ob:a"),
        ("z_future", "task:T-1", "ob:z1"),
        ("z_future", "task:T-2", "ob:z2"),
    ]
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/test_navigate_obligations.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'coherence.navigate.obligations'`).

- [ ] **Step 3: Implement.**

```python
"""Obligation-aware navigator view: effective profile and compiled obligations
for a scope, plus a plain-words explanation for any one obligation. Composes
`coherence.policy.compiler` only for the actual profile/obligation resolution
-- it never recomputes that logic itself. It also loads the trace graph
(`coherence.trace.model`) once per call and passes it through to
`resolve_profile`/`compile_obligations` via their `nodes=`/`edges=` params,
since both would otherwise reload the same graph independently (each
non-project scope call would load twice inside `effective_profile_view`
alone, and callers like `cmd_goal_show`/`cmd_sim_run` are hit on every
docs-server page load through `coherence.navigate.worker`).
"""
from __future__ import annotations

from pathlib import Path

from coherence.policy.compiler import compile_obligations, resolve_profile
from coherence.trace import model as trace_model
from coherence.navigate.queries import ScopeKindError
from substrate.policy.obligation import Obligation
from substrate.policy.vocabulary import (
    InvalidProfileError,
    ProfileConflictError,
    UncompiledPresetError,
)

#: Artifact kinds that resolve to a real trace-node policy scope. Narrower
#: than router.py's `_BROWSER_KINDS` (bundle/adr/metric are browser-navigable
#: but `coherence.trace.model.load_nodes` never loads them as lookup-by-id
#: trace nodes, so 2B's `resolve_profile` can never resolve them to anything
#: but the project default) -- see Task 1 docstring on `present_obligations`.
_WHY_REQUIRED_KINDS = ("sr", "task", "feat", "goal")

# 2B's compiler currently compiles a project-level obligation for any string
# that reaches it, then falls back to the project profile when no node exists.
# This adapter must validate the scope before calling it, so unknown goal ids
# and unsupported kinds cannot inherit project obligations. `run:` is kept
# separate because load_nodes currently exposes no run nodes; 3B reports it as
# explicitly unsupported rather than treating it as a declared scope.
_POLICY_SCOPE_KINDS = ("sr", "task", "feat", "goal")
_UNSUPPORTED_POLICY_SCOPE_KINDS = ("run",)
_NO_DECLARED_SCOPE = "no declared policy scope"

#: `ci_verification` is compiled unconditionally for every scope (2B D18);
#: excluding it here is what makes `obligations_open_count` mean something
#: scope-specific rather than a structural always->=1 (review finding #3).
_PROJECT_LEVEL_KINDS = ("ci_verification",)

_OPEN_SEVERITIES = ("blocking", "required")

# The compiler's list order is an implementation detail. Keep the view order
# fixed as later increments append verification_result/human_review, and sort
# unknown future kinds deterministically after the known kinds.
_OBLIGATION_KIND_ORDER = (
    "ci_verification",
    "task_justification",
    "verification_result",
    "human_review",
)


def _obligation_dict(o: Obligation) -> dict:
    return {
        "id": o.id,
        "scope_ref": o.scope_ref,
        "kind": o.kind,
        "requiredness": o.requiredness,
        "reason": o.reason,
        "source_policy": o.source_policy,
        "state": o.state,
        "resolve_cmd": o.resolve_cmd,
    }


def _obligation_sort_key(o: Obligation) -> tuple[int, str, str, str]:
    rank = _OBLIGATION_KIND_ORDER.index(o.kind) if o.kind in _OBLIGATION_KIND_ORDER else len(_OBLIGATION_KIND_ORDER)
    return rank, o.kind, o.scope_ref, o.id


def _declared_policy_scope(root: Path, scope_ref: str) -> bool:
    kind, separator, identifier = scope_ref.partition(":")
    if not separator or not identifier or kind not in _POLICY_SCOPE_KINDS:
        return False
    nodes = trace_model.load_nodes(root)
    return any(node.kind == kind and node.id == identifier for node in nodes)


def _require_declared_policy_scope(root: Path, scope_ref: str) -> None:
    if scope_ref == "project":
        return
    kind = scope_ref.partition(":")[0]
    if kind in _UNSUPPORTED_POLICY_SCOPE_KINDS:
        raise ScopeKindError(
            f"policy scope unsupported for {scope_ref!r}: load_nodes exposes no run nodes"
        )
    if not _declared_policy_scope(root, scope_ref):
        raise ScopeKindError(f"{_NO_DECLARED_SCOPE} for {scope_ref!r}")


def _compile(root: Path, scope_ref: str) -> list[Obligation]:
    _require_declared_policy_scope(root, scope_ref)
    nodes = None
    edges = None
    if scope_ref != "project":
        nodes = trace_model.load_nodes(root)
        edges = trace_model.extract_edges(root, nodes)
    # resolve_profile is still called once more inside compile_obligations
    # (2B's own internal contract) -- passing nodes/edges through means that
    # second call reuses the graph already loaded here rather than reloading
    # it, which is the actual redundant cost this avoids.
    return sorted(
        compile_obligations(root, scope_ref, nodes=nodes, edges=edges),
        key=_obligation_sort_key,
    )


def effective_profile_view(root: Path, scope_ref: str = "project") -> dict:
    _require_declared_policy_scope(root, scope_ref)
    nodes = None
    edges = None
    if scope_ref != "project":
        nodes = trace_model.load_nodes(root)
        edges = trace_model.extract_edges(root, nodes)
    profile = resolve_profile(root, scope_ref, nodes=nodes, edges=edges)
    obligations = sorted(
        compile_obligations(root, scope_ref, nodes=nodes, edges=edges),
        key=_obligation_sort_key,
    )
    return {
        "scope_ref": scope_ref,
        "profile": profile,
        "obligations": [_obligation_dict(o) for o in obligations],
    }


def why_required(
    root: Path,
    obligation_id: str,
    scope_ref: str = "project",
    *,
    obligations: list[Obligation] | None = None,
) -> str | None:
    compiled = obligations if obligations is not None else _compile(root, scope_ref)
    for obligation in compiled:
        if obligation.id == obligation_id:
            return (
                f"{obligation.reason} "
                f"(source_policy={obligation.source_policy}, requiredness={obligation.requiredness})"
            )
    return None


def obligations_open_count(
    root: Path,
    scope_ref: str,
    *,
    exclude_kinds: tuple[str, ...] = _PROJECT_LEVEL_KINDS,
) -> tuple[int, str | None]:
    """Count open, required-or-blocking obligations meaningfully scoped to
    `scope_ref`. Returns `(count, error)`; `error` is set (count is 0) only
    when the scope's profile could not be resolved at all -- see module
    docstring / Task 1 Interfaces for why this is not folded into `count`.
    """
    try:
        obligations = _compile(root, scope_ref)
    except (ScopeKindError, InvalidProfileError, ProfileConflictError, UncompiledPresetError) as exc:
        return 0, str(exc)
    count = sum(
        1
        for o in obligations
        if o.kind not in exclude_kinds and o.requiredness in _OPEN_SEVERITIES and o.state == "open"
    )
    return count, None


def present_obligations(root: Path, scope_ref: str) -> dict:
    """Obligations + why-required explanations for a `present --why-required`
    call. Shared by `coherence.navigate.cli.cmd_present` and
    `coherence.presentation.cli.main` (Tasks 2 and 4) -- one implementation,
    two thin call sites.
    """
    kind = scope_ref.partition(":")[0]
    if kind not in _WHY_REQUIRED_KINDS:
        return {"obligations": None, "obligations_note": "no policy scope for this artifact kind"}
    if not _declared_policy_scope(root, scope_ref):
        return {"obligations": None, "obligations_note": _NO_DECLARED_SCOPE}
    try:
        compiled = _compile(root, scope_ref)
    except (InvalidProfileError, ProfileConflictError, UncompiledPresetError) as exc:
        return {"obligations": [], "obligations_error": str(exc)}
    obligations = [_obligation_dict(o) for o in compiled]
    for ob, o in zip(obligations, compiled):
        if o.requiredness in _OPEN_SEVERITIES:
            ob["why"] = why_required(root, o.id, scope_ref, obligations=compiled)
    return {"obligations": obligations}
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/test_navigate_obligations.py -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/coherence/navigate/obligations.py tests/unit/coherence/test_navigate_obligations.py
git commit -m "feat(navigate): effective-profile, why-required, obligations-open, present-obligations views"
```

### Task 2: Wire `coherence navigate obligations`, `present --why-required`, and fix `--scope`

**Files:**
- Modify: `src/coherence/navigate/cli.py`
- Test: `tests/unit/system/test_cli.py` (the REAL existing file — see File Structure)

**Interfaces:**
- Consumes: `coherence.navigate.obligations.{effective_profile_view, present_obligations}` (Task 1).
- Produces: `cmd_obligations(repo_root, scope_raw) -> dict` (new; `--scope` now goes through the
  same `_guard_scope`/`parse_scope_ref` contract every other `--scope`-taking subcommand in this
  file already uses, special-casing `"project"` explicitly first — review finding #6). A stale
  snapshot returns the existing stale envelope without trying to render obligations; a missing
  scope raises the existing structured `ScopeNotFoundError`; neither reaches the 2B compiler.
  `_render_obligations` must accept that stale envelope and any malformed obligation payload
  without `KeyError`/`TypeError`, rendering a stable `stale` or `unavailable (malformed payload)`
  marker instead. `cmd_present` gains an additive `obligations`/`obligations_note`/
  `obligations_error` key set when `--why-required` is passed (new optional CLI flag, default off
  — omitting it reproduces today's exact `present` output byte-for-byte).

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/system/test_cli.py`, following
  the file's existing fixtures/style (`write_sr` from `._fixtures`, `_write_feature_repo` already
  defined in the file).

```python
def _seed_gates(root: Path) -> None:
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n", encoding="utf-8",
    )


def test_obligations_project_scope_renders_and_json(tmp_path, capsys):
    _seed_gates(tmp_path)
    rc = main(["obligations", "--scope", "project", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["scope_ref"] == "project"
    assert payload["profile"] == "prototype"
    ci = next(o for o in payload["obligations"] if o["kind"] == "ci_verification")
    assert ci["scope_ref"] == "project"
    assert ci["source_policy"] == "prototype"


def test_obligations_rejects_garbage_scope_with_structured_error(tmp_path, capsys):
    """review finding #6: --scope must not silently accept an arbitrary
    string and return project-default obligations mislabeled with it."""
    _seed_gates(tmp_path)
    rc = main(["obligations", "--scope", "garbage", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "invalid scope ref" in err


def test_obligations_rejects_unknown_declared_kind_id_with_structured_error(tmp_path, capsys):
    """A supported scope kind with an undeclared id must fail closed at the
    CLI boundary instead of inheriting project-default obligations."""
    _seed_gates(tmp_path)
    rc = main([
        "obligations", "--scope", "goal:GOAL-DOES-NOT-EXIST",
        "--repo-root", str(tmp_path), "--json",
    ])
    err = capsys.readouterr().err
    assert rc == 1
    assert "not declared" in err
    assert "ScopeNotFoundError" in err


def test_obligations_accepts_a_real_trace_scope(tmp_path, capsys):
    _seed_gates(tmp_path)
    write_sr(tmp_path / "requirements", "SR-001")
    rc = main(["obligations", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["scope_ref"] == "sr:SR-001"


def test_present_why_required_calls_why_required_for_relevant_obligation(tmp_path, capsys):
    """Blocking finding #1: not just that an 'obligations' key exists, but
    that why_required actually ran for the relevant obligation(s)."""
    _seed_gates(tmp_path)
    write_sr(tmp_path / "requirements", "SR-001")
    rc = main([
        "present", "sr:SR-001", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations"] is not None
    ci = next(o for o in payload["obligations"] if o["kind"] == "ci_verification")
    assert ci["why"] is not None
    assert "prototype" in ci["why"]


def test_present_why_required_is_additive_and_off_by_default(tmp_path, capsys):
    _seed_gates(tmp_path)
    rc = main(["present", "feat:FEAT-NAV-017", "--repo-root", str(tmp_path), "--json"])
    baseline = json.loads(capsys.readouterr().out)
    assert "obligations" not in baseline

    rc = main([
        "present", "feat:FEAT-NAV-017", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    with_why = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert baseline.keys() <= with_why.keys()
    assert with_why["obligations"] is not None


def test_present_why_required_skips_non_scope_artifact(tmp_path, capsys):
    """review finding #7: a raw file path must not fall through to
    mislabeled project-default obligations."""
    _seed_gates(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("# x\n", encoding="utf-8")
    rc = main([
        "present", "src/a.py", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations"] is None
    assert payload["obligations_note"] == "no policy scope for this artifact kind"


def test_obligations_renderer_handles_stale_scope_result():
    from factory.system.cli import _render_obligations

    rendered = _render_obligations({
        "scope": {"kind": "sr", "ref": "sr:SR-001"},
        "stale": True,
        "freshness": "stale",
        "snapshot": {"ref": "sr:SR-001"},
        "resolver": "coherence navigate snapshot refresh --ref sr:SR-001",
        "message": "navigation input is not current",
    })
    assert "stale: true" in rendered
    assert "navigation input is not current" in rendered


def test_obligations_renderer_handles_malformed_payload_without_crashing():
    from factory.system.cli import _render_obligations

    rendered = _render_obligations({
        "scope_ref": "project",
        "profile": "prototype",
        "obligations": [{"kind": "ci_verification"}, "not-an-obligation"],
    })
    assert "malformed obligation[0]" in rendered
    assert "malformed obligation[1]" in rendered
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/system/test_cli.py -k "obligations or why_required" -v`
Expected: FAIL (`obligations` subcommand does not exist; `cmd_present` has no `why_required` kwarg).

- [ ] **Step 3: Implement `cmd_obligations`, scope-guarded.**

Add to `src/coherence/navigate/cli.py`, near the other `cmd_*` functions (alongside `cmd_health`):

```python
def cmd_obligations(repo_root: Path, scope_raw: str) -> dict:
    """Effective profile and compiled obligations for a scope (Inc 3B).

    `scope_raw == "project"` is the one legitimate obligations scope that is
    not a trace-graph artifact kind (`queries._SCOPE_KINDS` has no "project"
    entry) -- handled explicitly, first. Everything else routes through the
    same `_guard_scope`/`parse_scope_ref` contract every other `--scope`-
    taking subcommand in this file already uses, so `--scope garbage` raises
    a structured `ScopeKindError` instead of silently returning
    project-default obligations mislabeled with the garbage string (review
    finding #6).
    """
    from coherence.navigate.obligations import effective_profile_view

    if scope_raw == "project":
        return effective_profile_view(repo_root, "project")
    scope, snapshot = _guard_scope(repo_root, scope_raw)
    if snapshot.freshness == "stale":
        return _stale_scope_result(scope, snapshot)
    if snapshot.freshness == "missing":
        from coherence.navigate.queries import ScopeNotFoundError

        raise ScopeNotFoundError(f"scope {scope.ref!r} is not declared")
    return effective_profile_view(repo_root, scope.ref)


def _render_obligations(result: dict) -> str:
    if not isinstance(result, dict):
        return "obligations: unavailable (malformed payload)"
    if result.get("stale"):
        scope = result.get("scope", {}).get("ref", "unknown")
        lines = [f"scope: {scope}", "  stale: true"]
        if result.get("freshness"):
            lines.append(f"  freshness: {result['freshness']}")
        if result.get("message"):
            lines.append(f"  message: {result['message']}")
        if result.get("resolver"):
            lines.append(f"  resolver: {result['resolver']}")
        return "\n".join(lines)
    obligations = result.get("obligations")
    if not isinstance(obligations, list):
        return "obligations: unavailable (malformed payload)"
    if "scope_ref" not in result or "profile" not in result:
        return "obligations: unavailable (malformed payload)"
    lines = [f"scope: {result['scope_ref']}", f"  profile: {result['profile']}"]
    if result.get("obligations_note"):
        lines.append(f"  obligations: {result['obligations_note']}")
    if result.get("obligations_error"):
        lines.append(f"  obligations: unresolved ({result['obligations_error']})")
    for index, ob in enumerate(obligations):
        if not isinstance(ob, dict) or not all(key in ob for key in ("kind", "requiredness", "reason")):
            lines.append(f"  ! malformed obligation[{index}]")
            continue
        # not_applicable obligations render distinctly, not identically to an
        # applicable one (review minor finding).
        marker = " [not applicable]" if ob["requiredness"] == "not_applicable" else ""
        lines.append(f"  [{ob['kind']}] {ob['requiredness']}{marker}: {ob['reason']}")
        if "scope_ref" in ob and "source_policy" in ob:
            lines.append(f"    scope_ref: {ob['scope_ref']}  source_policy: {ob['source_policy']}")
        if ob.get("resolve_cmd"):
            lines.append(f"    resolve: {ob['resolve_cmd']}")
        if ob.get("why"):
            lines.append(f"    why: {ob['why']}")
    if not obligations:
        lines.append("  no compiled obligations")
    return "\n".join(lines)
```

Register the subcommand in `main`:

```python
p_obligations = sub.add_parser("obligations", parents=[common])
p_obligations.add_argument("--scope", default="project")
```

and dispatch it in the `try:` block:

```python
elif args.cmd == "obligations":
    result = cmd_obligations(args.repo_root, args.scope)
    rendered = _render_obligations(result)
```

`cmd_obligations` can raise `ScopeKindError` (a `ScopeError`) for an invalid `--scope`; `main`'s
existing `except ScopeError as exc: _print_error(exc); return 1` handler already covers it — no
new exception handling needed in `main`.

- [ ] **Step 4: Extend `cmd_present` additively, using the shared `present_obligations` helper.**

```python
def cmd_present(
    repo_root: Path, artifact: str, focus: str | None, level: str | None = None,
    *, why_required: bool = False,
) -> dict:
    level_obj = parse_level(level) if level is not None else None
    result = present(repo_root, artifact, focus, level=level_obj)
    # "snapshot" only appears in the router's result when resolve_intent hit
    # its OWN stale-navigation-input early return (router.py's
    # ResolvedIntent.snapshot_freshness is set only on that path) -- obligation
    # data must never be glued onto that refusal (review minor finding).
    if why_required and "snapshot" not in result:
        from coherence.navigate.obligations import present_obligations

        result = {**result, **present_obligations(repo_root, artifact)}
    return result
```

Add the CLI flag in `main`:

```python
p_present.add_argument("--why-required", action="store_true", dest="why_required")
```

and pass it through the dispatch call:

```python
elif args.cmd == "present":
    result = cmd_present(
        args.repo_root, args.artifact, args.focus, args.level, why_required=args.why_required
    )
    rendered = _render_present(result)
```

Extend `_render_present` to show obligation data when present, without changing any existing line:

```python
def _render_present(result: dict) -> str:
    lines = [
        f"intent: present({result['artifact']}{', focus=' + result['focus'] if result['focus'] else ''})",
        f"  level: {result['level']}",
        f"  adapter: {result['adapter']}",
    ]
    if result.get("target"):
        lines.append(f"  target: {result['target']}")
    lines.append(f"  resolution: {result['resolution']}")
    if result.get("note"):
        lines.append(f"  note: {result['note']}")
    if result.get("obligations_note"):
        lines.append(f"  obligations: {result['obligations_note']}")
    elif result.get("obligations_error"):
        lines.append(f"  obligations: unresolved ({result['obligations_error']})")
    elif result.get("obligations") is not None:
        lines.append(f"  obligations ({len(result['obligations'])}):")
        for ob in result["obligations"]:
            lines.append(f"    [{ob['kind']}] {ob['requiredness']}: {ob['reason']}")
            if ob.get("why"):
                lines.append(f"      why: {ob['why']}")
    return "\n".join(lines)
```

- [ ] **Step 5: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/system/test_cli.py -k "obligations or why_required" -v`
Expected: PASS.

- [ ] **Step 6: Run the full system CLI test suite for regressions.**

Run: `rtk proxy uv run python -m pytest tests/unit/system -q`
Expected: PASS — every existing `present`/`goal`/`sim`/`health` test still passes with its
original assertions (this task adds keys, never removes or renames one).

- [ ] **Step 7: Commit.**

```bash
git add src/coherence/navigate/cli.py tests/unit/system/test_cli.py
git commit -m "feat(navigate): obligations subcommand (scope-guarded); present --why-required"
```

### Task 3: Obligation summary on `goal show` and `sim run`

Extends `coherence.navigate.cli`'s `goal`/`sim` subcommands (dispatched from `main()` in the same
file — reached by the docs-server via `coherence.navigate.worker`'s `goal_show`/`sim_run`
handlers, and by `tests/unit/system/test_cli.py`) with an additive `obligations_open` count and an
`obligations_error` field, so a reviewer looking at one goal or one simulation run can see whether
any open blocking/required obligation for that scope still needs attention, without a second
lookup, and can tell a genuine "nothing open" from an unresolved profile.

**Files:**
- Modify: `src/coherence/navigate/cli.py`
- Test: extend `tests/unit/system/test_cli.py`
- Boundary test: extend `pi-ext/factory-watch/test/system-worker.test.ts`

**Interfaces:**
- Consumes: `coherence.navigate.obligations.obligations_open_count` (Task 1).
- Produces: `cmd_goal_show` result gains `obligations_open: int` and `obligations_error: str |
  None` for `goal:<id>`; `cmd_sim_run` result gains the same for `run:<run_id>`.
- For `sim run`, the current `run:<id>` scope is explicitly unsupported because `load_nodes`
  exposes no run nodes: the additive result is `obligations_open: 0` with a non-null
  `obligations_error` describing that unsupported boundary. This is degraded enrichment, not a
  successful run-scope policy resolution.
- `obligations_open` counts `blocking` OR `required` open obligations (not `blocking` alone —
  review minor finding: `required` is still a real gap per the guide's dimension definitions),
  excluding `ci_verification` (review finding #3: `ci_verification` is compiled unconditionally
  for every scope, so counting it here would make this field always `>= 1` regardless of the
  goal/run's own state, asserting nothing goal/run-specific). Neither `goal:` nor `run:` scopes
  compile any OTHER obligation kind today (2B compiles `task_justification` only for `task:`
  scopes) — so `obligations_open` will correctly read `0` for essentially every goal/run until
  Increment 4/6 land `verification_result`/`human_review`, which is honest, not a bug: the field's
  name is kept as `obligations_open` (not renamed) because its meaning — "open,
  required-or-blocking obligations meaningfully scoped here" — is unchanged; only its filter
  became correct. The current 2B compiler intentionally has no goal/run-specific kind, so the
  real seeded fixtures assert the honest `0`; separate positive boundary tests inject a compiled
  future obligation and assert `goal show` propagates a non-zero count. `sim run` has no positive
  obligation test in 3B because its run scope is explicitly unsupported at the current
  `load_nodes` boundary; a positive run assertion requires the approval-dependent contract above.
  This keeps the fixture honest about 2B and the current trace loader.

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/system/test_cli.py`.

```python
def test_goal_show_reports_open_blocking_obligations(tmp_path, capsys):
    _seed_gates(tmp_path)
    _write_goal_file(tmp_path)
    rc = main(["goal", "show", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    # ci_verification is excluded (review finding #3): a goal scope compiles
    # no other obligation kind today, so this is honestly 0, not a
    # structural >= 1.
    assert payload["obligations_open"] == 0
    assert payload["obligations_error"] is None


def test_goal_show_surfaces_uncompiled_preset_error(tmp_path, capsys):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    _write_goal_file(tmp_path)
    rc = main(["goal", "show", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations_open"] == 0
    assert payload["obligations_error"] is not None
    assert "exploration" in payload["obligations_error"]


def test_sim_run_reports_unsupported_run_scope(tmp_path, capsys):
    _seed_gates(tmp_path)
    _seed_sim_runs(tmp_path)
    rc = main(["sim", "run", "RUN-3", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations_open"] == 0
    assert payload["obligations_error"] == (
        "policy scope unsupported for 'run:RUN-3': load_nodes exposes no run nodes"
    )


def test_goal_show_propagates_a_positive_open_obligation(monkeypatch, tmp_path, capsys):
    """Positive consumer coverage: 2B has no goal-specific kind yet, so
    inject the future compiler result at this boundary and prove the view does
    not hard-code the honest-current zero."""
    _seed_gates(tmp_path)
    _write_goal_file(tmp_path)
    from coherence.navigate import obligations as obligations_module

    monkeypatch.setattr(obligations_module, "obligations_open_count", lambda *_args, **_kwargs: (2, None))
    rc = main(["goal", "show", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations_open"] == 2
    assert payload["obligations_error"] is None
```

Append to `pi-ext/factory-watch/test/system-worker.test.ts`:

```typescript
test("worker preserves additive goal_show obligation fields", async () => {
  const result = systemWorkerRequest("/repo", {
    cmd: "goal_show",
    params: { goal_id: "GOAL-CLI-001" },
  });
  const child = lastChild();
  const value = {
    id: "GOAL-CLI-001",
    obligations_open: 2,
    obligations_error: null,
  };
  child.emitLine(JSON.stringify({ id: 1, ok: true, value }));
  await expect(result).resolves.toEqual({ ok: true, value });
  expect(JSON.parse(requestLine(child))).toEqual({
    id: 1,
    cmd: "goal_show",
    params: { goal_id: "GOAL-CLI-001" },
  });
});

test("worker preserves sim_run additive fields and unsupported run-scope error", async () => {
  const result = systemWorkerRequest("/repo", {
    cmd: "sim_run",
    params: { run_id: "RUN-3" },
  });
  const child = lastChild();
  const value = {
    run: "RUN-3",
    result: "passed",
    obligations_open: 0,
    obligations_error: "policy scope unsupported for 'run:RUN-3': load_nodes exposes no run nodes",
  };
  child.emitLine(JSON.stringify({ id: 1, ok: true, value }));
  await expect(result).resolves.toEqual({ ok: true, value });
  expect(JSON.parse(requestLine(child))).toEqual({
    id: 1,
    cmd: "sim_run",
    params: { run_id: "RUN-3" },
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/system/test_cli.py -k "obligations_open or uncompiled_preset or unsupported_run_scope" -v`
Expected: FAIL (`KeyError: 'obligations_open'`).

- [ ] **Step 3: Implement.**

```python
def cmd_goal_show(repo_root: Path, goal_id: str) -> dict:
    from coherence.navigate.obligations import obligations_open_count

    result = query_goal(repo_root, goal_id)
    count, error = obligations_open_count(repo_root, f"goal:{goal_id}")
    result["obligations_open"] = count
    result["obligations_error"] = error
    return result


def cmd_sim_run(repo_root: Path, run_id: str) -> dict:
    from coherence.navigate.obligations import obligations_open_count

    result = query_simulation_run(repo_root, run_id)
    count, error = obligations_open_count(repo_root, f"run:{run_id}")
    result["obligations_open"] = count
    result["obligations_error"] = error
    return result
```

(`obligations_open_count`'s `UncompiledPresetError` handling and `ci_verification` exclusion are
Task 1's — this task's own responsibility is limited to wiring the two call sites additively.)

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/system/test_cli.py -k "obligations_open or uncompiled_preset or unsupported_run_scope" -v`
Expected: PASS.

- [ ] **Step 5: Run the full system CLI suite for regressions.**

Run: `rtk proxy uv run python -m pytest tests/unit/system -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/coherence/navigate/cli.py tests/unit/system/test_cli.py
git commit -m "feat(navigate): obligations_open/obligations_error on goal show and sim run"
```

### Task 4: `--why-required` on `coherence.presentation.cli`'s `present` (the pi-ext-facing module)

Closes review finding #5's first half: `coherence.presentation.cli` is a SEPARATE module from
`coherence.navigate.cli` (see Architecture), and it is the one `pi-ext/factory-watch/src/
system-cli.ts`'s `buildPresentationCommand`/`loadSystemPresent` actually invoke on behalf of the
pi extension's `eng_present` tool. Task 2's `--why-required` flag on `coherence.navigate.cli`'s
`present` never reaches that live tool at all. This task adds the identical flag to this module's
own `present` command, reusing Task 1's `present_obligations` — no duplicated scope-kind gating,
`UncompiledPresetError` handling, or `why_required` wiring; this is a second thin call site over
the same function Task 2 already uses.

**Files:**
- Modify: `src/coherence/presentation/cli.py`
- Test: `tests/unit/presentation/test_cli.py` (the REAL, existing file covering this module — see
  File Structure)
- Test: create `pi-ext/factory-watch/test/eng-context-tool-format.test.ts` for formatter boundary
  behavior
- Modify: `pi-ext/factory-watch/src/system-cli.ts`, `pi-ext/factory-watch/src/eng-context-tools.ts`,
  `pi-ext/factory-watch/src/eng-context-tool-format.ts`
- Test: `pi-ext/factory-watch/test/system-cli.test.ts`,
  `pi-ext/factory-watch/test/eng-context-tools.test.ts`

**Interfaces:**
- Consumes: `coherence.navigate.obligations.present_obligations` (Task 1).
- Produces: `coherence.presentation.cli.main`'s `present` subcommand gains the same `--why-required`
  flag and the same additive `obligations`/`obligations_note`/`obligations_error` keys Task 2 adds
  to `coherence.navigate.cli`'s `present`. This module has no `cmd_present`-style function to
  extend separately — `main` calls `present(...)` from the router directly (see the file as read
  in full above) — so the wiring lives inline in `main`.
- Produces: `loadSystemPresent(cwd, artifact, focus?, whyRequired?)` appends `--why-required`
  only when requested, and `eng_present` exposes an optional `why_required: boolean` parameter and
  forwards it unchanged. `PresentResult` models the additive obligation fields as optional because
  the flag is off by default. `formatPresent` renders `obligations_note`/`obligations_error` and
  each safe obligation explanation; TypeScript never recomputes policy or changes Python's order.

- [ ] **Step 1: Write the failing test.** Append to `tests/unit/presentation/test_cli.py`.

```python
def test_present_cli_why_required_calls_why_required(tmp_path, capsys):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n", encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n---\n", encoding="utf-8",
    )
    rc = main([
        "present", "sr:SR-001", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations"] is not None
    ci = next(o for o in payload["obligations"] if o["kind"] == "ci_verification")
    assert ci["why"] is not None


def test_present_cli_why_required_off_by_default(tmp_path, capsys):
    rc = main(["present", "feat:FEAT-NAV-017", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "obligations" not in payload
```

Extend the existing import list in `pi-ext/factory-watch/test/system-cli.test.ts` with
`loadSystemPresent`, then append:

```typescript
test("loadSystemPresent propagates --why-required to factory.presentation", () => {
  spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
  loadSystemPresent("/repo", "sr:SR-001", undefined, true);
  expect(spawnSync).toHaveBeenCalledWith(
    "uv",
    ["run", "python", "-m", "factory.presentation", "present", "sr:SR-001", "--why-required", "--json"],
    expect.objectContaining({ cwd: "/repo" }),
  );
});
```

Append to `pi-ext/factory-watch/test/eng-context-tools.test.ts`:

```typescript
test("eng_present forwards optional why_required to its loader", async () => {
  let received: boolean | undefined;
  const tool = buildEngContextTools(deps({
    present: (_cwd, _artifact, _focus, whyRequired) => {
      received = whyRequired;
      return { ok: true as const, value: present };
    },
  })).find((candidate) => candidate.name === "eng_present");
  if (!tool) throw new Error("eng_present not found");
  await run(tool, { artifact: "sr:SR-001", why_required: true });
  expect(received).toBe(true);
});
```

Create `pi-ext/factory-watch/test/eng-context-tool-format.test.ts` with these concrete formatter
boundary cases. The fixture keeps the existing `PresentResult` fields populated and varies only
the additive obligation fields; the tests prove that TypeScript renders Python's data without
recomputing or reordering it:

```typescript
import { expect, test } from "vitest";
import { formatPresent } from "../src/eng-context-tool-format.js";
import type { PresentResult } from "../src/system-cli.js";

function basePresent(): PresentResult {
  return {
    artifact: "sr:SR-001",
    focus: null,
    level: "INSPECT",
    intent: { artifact: "sr:SR-001", focus: null },
    resolution: "resolved",
    adapter: null,
    target: null,
    note: "",
  };
}

test("formats a no-policy-scope note", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: null,
    obligations_note: "no policy scope for this artifact kind",
  });
  expect(rendered).toContain("obligations: no policy scope for this artifact kind");
});

test("formats an unresolved obligation error", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [],
    obligations_error: "profile cannot be resolved",
  });
  expect(rendered).toContain("obligations: unresolved (profile cannot be resolved)");
});

test("formats explanations in the received obligation order", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [
      {
        id: "ob:human",
        scope_ref: "sr:SR-001",
        kind: "human_review",
        requiredness: "required",
        reason: "review the result",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: null,
        why: "the profile requires a human review",
      },
      {
        id: "ob:ci",
        scope_ref: "project",
        kind: "ci_verification",
        requiredness: "blocking",
        reason: "run CI",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: null,
        why: null,
      },
    ],
  });
  expect(rendered.indexOf("[human_review] required")).toBeLessThan(
    rendered.indexOf("[ci_verification] blocking"),
  );
  expect(rendered).toContain("why: the profile requires a human review");
});

test("marks malformed optional obligation payloads without throwing", () => {
  const malformedArray = { ...basePresent(), obligations: "not-an-array" } as unknown as PresentResult;
  expect(() => formatPresent(malformedArray)).not.toThrow();
  expect(formatPresent(malformedArray)).toContain("obligations: unavailable (malformed payload)");

  const malformedEntry = {
    ...basePresent(),
    obligations: [{ kind: "ci_verification" }],
  } as unknown as PresentResult;
  expect(() => formatPresent(malformedEntry)).not.toThrow();
  expect(formatPresent(malformedEntry)).toContain("obligations: unavailable (malformed payload)");
});
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/presentation/test_cli.py -k why_required -v`
Expected: FAIL (`--why-required` is not a recognized argument).

- [ ] **Step 3: Implement.**

In `src/coherence/presentation/cli.py`, add the flag next to `--level`:

```python
    p_present.add_argument("--why-required", action="store_true", dest="why_required")
```

and extend the dispatch:

```python
    try:
        if args.cmd == "present":
            level = parse_level(args.level) if args.level is not None else None
            result = present(args.repo_root, args.artifact, args.focus, level=level)
            if args.why_required and "snapshot" not in result:
                from coherence.navigate.obligations import present_obligations

                result = {**result, **present_obligations(args.repo_root, args.artifact)}
        else:  # pragma: no cover - argparse enforces subcommand
            parser.error(f"unknown command: {args.cmd}")
            return 1
    except (FileNotFoundError, ValueError) as exc:
        _print_error(exc)
        return 1
```

The human-readable (non-`--json`) branch already prints only named keys (`level`/`adapter`/
`target`/`resolution`/`note`); leave it unchanged (additive-only, matching Task 2's precedent —
`--json` output is the primary consumer, since that is what `loadSystemPresent` parses).

In `pi-ext/factory-watch/src/system-cli.ts`, extend the existing `PresentResult` without changing
the base fields:

```typescript
export interface PresentObligation {
  id: string;
  scope_ref: string;
  kind: string;
  requiredness: string;
  reason: string;
  source_policy: string;
  state: string;
  resolve_cmd: string | null;
  why?: string | null;
}

export interface PresentResult {
  // existing fields...
  obligations?: PresentObligation[] | null;
  obligations_note?: string;
  obligations_error?: string;
}

export function loadSystemPresent(
  cwd: string,
  artifact: string,
  focus?: string,
  whyRequired = false,
): CliResult<PresentResult> {
  const args = ["present", artifact];
  if (focus) args.push("--focus", focus);
  if (whyRequired) args.push("--why-required");
  args.push("--json");
  const cmd = buildPresentationCommand(args);
  return runJsonCli<PresentResult>(cwd, cmd.bin, cmd.args);
}
```

In `pi-ext/factory-watch/src/eng-context-tools.ts`, add
`why_required: Type.Optional(Type.Boolean({ description: "Include compiled obligation explanations" }))`
to `eng_present`'s parameters and call
`deps.present(ctx.cwd, params.artifact, params.focus ?? undefined, params.why_required ?? false)`.
The existing `Dependencies.present` type then enforces the fourth argument at this call site.

In `pi-ext/factory-watch/src/eng-context-tool-format.ts`, extend `formatPresent` after the existing
`note` line: print `obligations: <note>` for `obligations_note`, print
`obligations: unresolved (<error>)` for `obligations_error`, and otherwise iterate the optional
array in its received order, printing each kind/requiredness and `why` when present. If the value
is not an array or an entry is not an object with `kind`, `requiredness`, and `reason`, print a
stable `obligations: unavailable (malformed payload)` marker and continue; never throw while
formatting an optional enrichment.

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/presentation/test_cli.py -v`
Expected: PASS, including every pre-existing test in the file.

Run: `rtk proxy npm test --prefix pi-ext/factory-watch -- system-cli.test.ts eng-context-tools.test.ts eng-context-tool-format.test.ts`
Expected: PASS, including command propagation, optional-schema, and the concrete note/error/order/malformed-payload formatter cases above.

- [ ] **Step 5: Commit.**

```bash
git add src/coherence/presentation/cli.py tests/unit/presentation/test_cli.py \
        pi-ext/factory-watch/src/system-cli.ts pi-ext/factory-watch/src/eng-context-tools.ts \
        pi-ext/factory-watch/src/eng-context-tool-format.ts \
        pi-ext/factory-watch/test/system-cli.test.ts pi-ext/factory-watch/test/eng-context-tools.test.ts
git commit -m "feat(presentation): present --why-required (the pi-ext eng_present entry point)"
```

### Task 5: `obligations_open` on `coherence.goals.cli`'s `show` (the `/goal show` entry point)

Closes review finding #5's second half, as a real decision rather than an open question:
`coherence.goals.cli` (`python -m factory.goals`) is a separate module from
`coherence.navigate.cli`, and the pi extension's `/goal` slash command
(`pi-ext/factory-watch/src/index.ts`) spawns `python -m factory.goals <args> --json` directly —
`/goal show <id>` never reaches `coherence.navigate.cli`'s `goal show` (Task 3) at all. This task
gives `coherence.goals.cli`'s own `show` the same additive `obligations_open`/`obligations_error`
fields, reusing Task 1's `obligations_open_count` (no duplicated filter logic).
`coherence.simulation.cli` is deliberately NOT touched — see Architecture for why (no verified
caller reaches it from the pi extension, unlike `factory.goals` and `factory.presentation`).

**Files:**
- Modify: `src/coherence/goals/cli.py`
- Test: `tests/unit/goals/test_cli.py` (the REAL, existing file covering this module)

**Interfaces:**
- Consumes: `coherence.navigate.obligations.obligations_open_count` (Task 1).
- Produces: `coherence.goals.cli.main`'s `show` subcommand's JSON payload gains
  `obligations_open: int` and `obligations_error: str | None`, additive to its existing shape.

- [ ] **Step 1: Write the failing test.** Append to `tests/unit/goals/test_cli.py`.

```python
def test_show_reports_obligations_open(tmp_path, capsys):
    _run(tmp_path, "create", "--id", "GOAL-NAV-003", "--title", "t", "--feature", "FEAT-NAV-017",
         "--requirements", "SR-032", "--metric", "reacquisition_rate", "--source-experiment",
         "SIM-047", "--target", ">= 0.90")
    capsys.readouterr()  # drain create's payload
    assert _run(tmp_path, "show", "GOAL-NAV-003") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["obligations_open"] == 0
    assert payload["obligations_error"] is None
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `rtk proxy uv run python -m pytest tests/unit/goals/test_cli.py -k obligations_open -v`
Expected: FAIL (`KeyError: 'obligations_open'`).

- [ ] **Step 3: Implement.**

In `src/coherence/goals/cli.py`, extend the `show` branch of `main`:

```python
    if command == "show":
        goal = _load_one(root, args.goal_id)
        from coherence.navigate.obligations import obligations_open_count

        obligations_open, obligations_error = obligations_open_count(root, f"goal:{goal.id}")
        _emit(
            {
                "id": goal.id,
                "title": goal.title,
                "state": goal.state,
                "version": goal.version,
                "feature": goal.feature,
                "requirements": goal.requirements,
                "metric": goal.metric,
                "target": goal.target,
                "evidence": goal.evidence,
                "history": goal.history,
                "scope_errors": goal.scope_errors,
                "obligations_open": obligations_open,
                "obligations_error": obligations_error,
            },
            args.json,
        )
        return 0
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/goals/test_cli.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Commit.**

```bash
git add src/coherence/goals/cli.py tests/unit/goals/test_cli.py
git commit -m "feat(goals): obligations_open on show (the /goal show entry point)"
```

---

## Increment 3B Acceptance

- The formatter test file `pi-ext/factory-watch/test/eng-context-tool-format.test.ts` covers safe
  rendering of additive obligation fields, notes, and errors without re-deriving policy data.
- The worker boundary test file `pi-ext/factory-watch/test/system-worker.test.ts` verifies that
  additive obligation fields cross the worker boundary and that `sim run` reports the explicit
  degraded/unsupported run-scope result when `load_nodes` has no run nodes.
- `sim run` must not report a successful run-scope policy resolution in this increment. Extending
  `load_nodes`/the policy contract to expose run nodes remains an approval-dependent open decision.

- `coherence navigate obligations --scope project` (and any `sr:`/`feat:`/`task:`/`goal:` scope)
  renders the effective profile and every compiled obligation, each with its full 8-field
  `Obligation` contract (including `scope_ref` and `source_policy`) and a plain-words reason;
  obligations use the fixed kind order `ci_verification`, `task_justification`,
  `verification_result`, `human_review`, then unknown kinds by `(kind, scope_ref, id)`;
  `--scope garbage` and an unknown declared-kind id fail with a structured `ScopeKindError`,
  never a silent project-default fallback (Tasks 1, 2).
- `coherence navigate present <artifact> --why-required` AND `coherence presentation present
  <artifact> --why-required` (the module the pi extension's `eng_present` tool actually invokes)
  both add an `obligations` field carrying a `why_required`-derived `"why"` explanation for each
  blocking/required obligation, without changing any existing field's meaning or presence; an
  artifact whose kind is not `sr:`/`task:`/`feat:`/`goal:` gets `obligations: None` with a note,
  never mislabeled project-default obligations; an unresolvable profile surfaces
  `obligations_error`, never a silent empty list. The TypeScript `eng_present` schema, loader, and
  formatter propagate/render the flag and additive fields; a stale or malformed optional payload
  renders a stable marker rather than throwing (Tasks 2, 4).
- `coherence navigate goal show <id>`, `coherence navigate sim run <id>`, AND `python -m
  factory.goals show <id>` (the pi extension's `/goal show` entry point) report
  `obligations_open`/`obligations_error`, additive to their existing shape, correctly excluding
  the project-level `ci_verification` obligation so the count is scope-specific rather than a
  structural `>= 1`; seeded current-2B tests prove zero and positive boundary tests prove a
  future non-zero obligation propagates (Tasks 3, 5).
- `InvalidProfileError`, `ProfileConflictError`, and `UncompiledPresetError` are structured
  non-zero errors for the primary `obligations` projection, but become `obligations_error` with
  count/list neutral values for optional `present`/`goal show`/`sim run` enrichment; no path
  reports a policy error as a successful empty result.
- Every Increment 3 test that exercised `present`/`goal show`/`sim run`/`goals show` before this
  plan still passes unchanged.
- `coherence.simulation.cli` is deliberately not extended in this increment (Architecture; no
  verified pi-extension caller reaches it today).
## Browser/UI contract reconciliation

This increment also covers the browser-facing transport and rendering contracts. The worker surface is intentionally limited: `src/coherence/navigate/worker.py` exposes `goal_show` and `sim_run`; it has no `present` handler, and this plan must not add one.

**Files:**
- Modify: `src/coherence/navigate/worker.py` only as needed to preserve the JSON-lines response contract for `goal_show` and `sim_run`.
- Test: `tests/coherence/navigate/test_worker.py` for the Python/JSON serializer boundary and additive obligation/profile fields.
- Modify: `pi-ext/factory-watch/src/docs-server.ts` for browser endpoint transport behavior.
- Test: `pi-ext/factory-watch/test/docs-server.test.ts` for `goal_show`, `sim_run`, and stable unsupported `run:<id>` degradation.
- Modify: `pi-ext/factory-watch/src/eng-context-tools.ts` and `pi-ext/factory-watch/src/system-cli.ts` for the existing `eng_present` → `loadSystemPresent` → `factory.presentation` path.
- Test: `pi-ext/factory-watch/test/system-context-tools.test.ts` for `why_required` propagation and `pi-ext/factory-watch/test/system-renderers.test.ts` for ordered presentation formatting.
- Test: `pi-ext/factory-watch/test/system-page.test.ts`, `pi-ext/factory-watch/test/system-page-additions.test.ts`, and `pi-ext/factory-watch/test/system-feature-view.test.ts` for browser/UI rendering of the transported payload.

### Task: Test the browser transport before changing implementation

- [ ] Add worker-level JSON-lines fixtures that assert `goal_show` and `sim_run` retain their existing fields while adding obligation/profile fields. Assert that the worker still has no `present` action.
- [ ] Add docs-server tests that exercise both browser endpoints through the Python worker boundary. Assert additive fields survive serialization and parsing, and that an unsupported `run:<id>` request returns the same stable degraded response on repeated calls rather than throwing or fabricating a presentation response.
- [ ] Include stale, malformed, and error payload fixtures at the transport boundary. Assert each is represented as a deterministic degraded payload that the TypeScript side can render without guessing missing fields.

### Task: Verify the factory-watch presentation path and renderer contract

- [ ] Add an `eng_present` test proving `why_required` is carried through `pi-ext/factory-watch/src/eng-context-tools.ts`, into `loadSystemPresent` in `pi-ext/factory-watch/src/system-cli.ts`, and ultimately to `factory.presentation`.
- [ ] Add formatter tests for stable item order, visible `why_required`, omission of `resume_cmd` when absent, and visible `blocking_obligation_resolve_cmd` when present.
- [ ] Add view tests covering fresh, stale, malformed, and error payloads. Assert that obligation/profile data remains additive, stale/error state is visible, malformed data is safely degraded, and no view expects a worker-side `present` handler.

### Acceptance criteria

- Browser tests cover the Python/JSON serializer boundary and both existing worker actions, including additive obligation/profile fields.
- Unsupported `run:<id>` degradation is stable, deterministic, and tested without introducing a `present` worker action.
- The `eng_present` → `loadSystemPresent` → `factory.presentation` path preserves `why_required`.
- TypeScript formatter/view tests prove order, `why_required`, absent `resume_cmd`, displayed `blocking_obligation_resolve_cmd`, and stale/malformed/error rendering behavior.
- Existing decisions about run-scope, reviewer naming, taxonomy, and CI remain unresolved; this browser/UI reconciliation does not select values for them.
