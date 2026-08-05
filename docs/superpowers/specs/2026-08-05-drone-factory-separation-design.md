# Design: Separating the Drone Product from the Factory

**Date:** 2026-08-05
**Status:** Draft — manifest requires human approval before execution
**Author:** Colin AUBE (with Claude)

---

## 1. Problem

`pi-agent-factory` contains two systems: the factory itself, and the shark-drone
product the factory exists to build. `cool_physical_ai_project` — the drone's own
repository — is a near-empty shell holding the one artifact that should sit beside
that code, its single requirement.

Measured on `main` at `74cd75f`:

| | in `pi-agent-factory` | in `cool_physical_ai_project` |
|---|---|---|
| drone/sim code | `src/drone` 16 · `src/sim` 13 · `tests/sim` 12 · `scenarios` 5 = **46 files** | `src/drone/fake_flight_controller.py` — 1 stub |
| tasks | **22 of 45** deliver drone paths | 1 example |
| product specs / plans | 2 specs, 2 plans | none |
| requirements | none | `SR-001` |
| `.pi/skills`, `.factory/` | populated | **empty / absent** |
| sim dependencies | `pygame`, `matplotlib` in `pyproject.toml` | absent |

The two repositories share a root commit (`a813ec0`): the factory was extracted
*from* the drone project, and the drone implementation written afterwards landed
in the factory rather than back in the product repo.

### 1.1 Why this blocks traceability work

The next planned workstream is a "doctor" pass that infers system requirements
from planning artifacts, per behaviour, sourced from specs. Run against the
factory today it would write **drone requirements into the factory's requirements
register** and link factory-repo tasks to them — baking the conflation into the
artifact that is meant to be the source of truth. Unpicking that later means
rewriting SR ids, `satisfies:` edges and checksums across two repositories.

It also explains three symptoms previously treated as unrelated:
`cool_physical_ai_project/.pi/` being empty, its missing `.factory/factory.yaml`,
and `factory requirements new`'s template hardcoding `sim-testbench`,
`preemption_success_rate` and `shark_detected` — that template was written for a
drone living inside the factory's own tree.

### 1.2 Goals

- The factory repository contains only the factory.
- The drone repository contains the drone implementation, its product specs and
  plans, and its task ledger.
- Both repositories pass their own gates afterwards.
- The move is inspectable and abortable at every step.

### 1.3 Non-Goals

- **Not the doctor.** Inferring requirements is the next spec; this one only makes
  it safe to run.
- **Not a history rewrite.** See §5.
- **Not a refactor.** Code moves as-is. Import paths change only where a move
  forces it.
- **Not making the drone repo a fully wired factory target.** Giving it
  `.pi/skills/`, `.factory/factory.yaml` and harnesses is follow-on work (§7).

---

## 2. The boundary rule

An artifact belongs to the **drone** when it describes or implements the drone
product's behaviour. It belongs to the **factory** when it describes or implements
the machinery that builds products.

Applied mechanically where possible — a task is drone work when its deliverables
are under `src/drone/`, `src/sim/`, `tests/sim/` or `scenarios/` — and by explicit
ruling where that test is inconclusive (§3.3). Keyword matching was rejected: 17
of 22 specs mention "sim", almost all because of the factory's *sim gate*, not the
drone.

---

## 3. Manifest

### 3.1 Code and assets — move wholesale

| path | files |
|---|---|
| `src/drone/` | 16 |
| `src/sim/` | 13 |
| `tests/sim/` | 12 |
| `scenarios/` | 5 |
| `tests/agent/` | 3 — every `agent`-marked test imports only `drone.*` |
| `tests/integration/test_mission_loop.py` | 1 — the only `integration`-marked test, imports only `drone.*` |

`tests/e2e/` stays: it imports only `factory.orchestrator.*`.

`cool_physical_ai_project/src/drone/fake_flight_controller.py` already exists and
is superseded by the incoming `src/drone/`; the incoming copy wins, and any
divergence is resolved in favour of the factory's version, which is the one under
active development.

### 3.2 Planning artifacts — move

| kind | file |
|---|---|
| spec | `docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md` |
| spec | `docs/superpowers/specs/2026-07-30-sim-testbench-design.md` |
| plan | `docs/superpowers/plans/2026-07-21-mission-agent-navigation.md` |
| plan | `docs/superpowers/plans/2026-07-30-sim-testbench.md` |

Every other spec and plan is factory design work and stays. The two moving plans
are the only ones that generated drone tasks.

### 3.3 Tasks — move, with four explicit rulings

**Move (drone, 20 unambiguous):** T-029, T-030, T-031, T-032, T-033, T-034, T-035,
T-036, T-037, T-038, T-039, T-041, T-042, T-043, T-044, T-045, T-046, T-047,
T-048, T-050 — plus the four below, giving **24 in total**.

**Rulings on the four whose deliverables straddle the boundary:**

| task | title | ruling | why |
|---|---|---|---|
| T-049 | Scenario YAML Files | **drone** | delivers `scenarios/*.yaml`; the automated test missed it only because its body cites no backticked path |
| T-051 | Pytest Marker Update and Smoke Test | **drone** | its subject is the sim suite; the `sim` marker follows the sim tests |
| T-040 | Factory Gate & Project Config | **drone** | its deliverable is the *sim* marker and the sim gate wiring; the generic pipeline it also touched is base machinery that stays (§3.5) |
| T-052 | Update Factory Gate Scripts | **drone** | same — the sim gate is the drone's plug, not the factory's base |

All four move. Where a task's deliverable spans both sides — T-040 configured the
`agent` marker as well as `sim` — the task follows its **drone-specific** half,
and the generic half stays in the factory as base machinery. The task record moves
with the product it describes; the factory keeps the mechanism.

### 3.4 Dependencies

Move `pygame>=2.6.1` and `matplotlib>=3.11.1` from the factory's `pyproject.toml`
to the drone's. Neither is used by `src/factory/`; both exist solely for the sim
testbench and its plotter.

### 3.5 The plug-in contract — the factory is the base, the drone is a plug

The governing rule: **the factory provides mechanism, a project provides its own
plugs.** That is already this repo's stated direction —
`2026-07-31-polish-workflow-and-validation-node-design.md` §3 says the validation
node "never mentions drones" and that a repo declares what it has in a per-project
registry under `.factory/`, with "the drone repo registers `sim-testbench`".

**Gates never received that treatment.** `SubprocessGateRunner._SCRIPTS`
(`src/factory/orchestrator/backends.py`) hardcodes:

```python
"sim": "scripts/gates/sim_smoke.py",
```

That is a drone-specific gate baked into the factory's base, and the split
exposes it as a hard coupling rather than a cosmetic one:

- `run_validation` calls `gates.run("sim")` unconditionally (`nodes.py`).
- `SubprocessGateRunner.run` resolves `self._SCRIPTS[name]` to a path and shells it.

The failure is quieter than a crash, which makes it worse. Delete
`scripts/gates/sim_smoke.py` and the path still resolves; the subprocess merely
fails to open, returns non-zero, and `run_validation` reports **"sim tests
failed"** — blaming drone tests that no longer exist, on every task. Keeping the
file is no better: `pytest -m sim` with no sim tests exits 5, also non-zero.

**And it is not only the sim gate.** Every test carrying the `agent` marker and
every test carrying the `integration` marker is a drone test:

| gate | selects | all drone? | after the split |
|---|---|---|---|
| `sim` | `pytest -m sim` | yes | script gone / selects nothing |
| `agent` | `pytest -m agent` | **yes** — 3 files, all `tests/agent/` | selects nothing → exit 5 |
| `integration` | `pytest tests/integration/` | **yes** — 1 file | empty directory → exit 5 |

So three of the factory's gates are currently *defined by the drone's tests*.
`all.py` runs `AGENT_CMD`, so it would fail; `run_validation` runs the integration
gate, so every task would fail. This is the coupling in its fullest form, and it
is why "the factory is the base" has to be made true in code, not just asserted.

The rule that resolves all three uniformly: **"nothing to run" is not-applicable,
never failure.** Concretely, a missing gate script and pytest's exit code 5 (no
tests collected) both mean the project does not provide that gate. A gate that
runs and fails still fails.

The gate mechanism must therefore learn the contract as part of this split:

- **Factory (base):** keeps `SubprocessGateRunner`, `_proc.py`, and the
  lint/typecheck/unit gates. Gate resolution becomes **project-relative** in both
  code paths that run gates — `SubprocessGateRunner` (used by `factory-run`) and
  `scripts/gates/_proc.run_and_propagate` (used by `all.py`). A gate the project
  does not provide is reported as *not applicable* and skipped; never a crash,
  and never a silent pass disguised as green. The factory drops the `sim` and
  `agent` markers and `sim_smoke.py`, because it has neither suite.
- **Drone (plug):** already carries `scripts/gates/sim_smoke.py`, `SIM_CMD` and a
  `sim` marker, and gains the `agent` and `integration` suites with the code they
  test. When the factory later runs against the drone repo, those gates are
  discovered there.

This is the only part of the split that changes factory behaviour rather than
moving files, and it is where the factory's own suite is most likely to break.
It is a **prerequisite**, not follow-on: without it the factory cannot run at all
once the sim gate leaves.

The fuller registry (`.factory/registry.py` declaring `HARNESSES`/`PLAYGROUNDS`)
is **specified but not implemented** — there is no `polish/registry.py`, and
`nodes.py:350` only names `.factory/factory.yaml` inside an error string. This
split needs only the gate half of that contract; the rest stays deferred (§7).

---

## 4. What each repository looks like afterwards

**Factory (the base)** — `src/factory/` only; 21 tasks, all factory work; 20 specs
and 27 plans of factory design; no `pygame`/`matplotlib`; lint/typecheck/unit/agent
gates intact, sim gate gone, and gate resolution now project-relative so a repo
that provides no such gate is handled rather than crashing.

**Drone (a plug)** — `src/drone/` and `src/sim/`; `tests/sim/`; `scenarios/`;
24 tasks; 2 product specs and 2 plans; its own `sim` marker and
`scripts/gates/sim_smoke.py`; and `requirements/SR-001.md` finally sitting beside
the code it constrains.

Nothing in the factory names the drone afterwards. Nothing in the drone
reimplements the factory.

---

## 5. Procedure

Two commits, one per repository, each naming the other's SHA:

1. Verify both repositories are clean and green.
2. Copy the §3 paths into `cool_physical_ai_project`, preserving relative layout.
3. Commit there: *"feat: import drone implementation from pi-agent-factory@74cd75f"*.
4. `git rm -r` the same paths in `pi-agent-factory`, apply §3.4 and §3.5.
5. Commit here, citing the drone repo's new SHA.
6. Verify both repositories green (§8).

History is **not** rewritten. Per-file history stays fully readable in the
factory, which is where that code was actually written; the drone repo records a
single honest import commit pointing at it. Nothing is rewritten, so the operation
can be inspected and abandoned at any point before step 5.

---

## 6. Handling the artifacts left pointing across the boundary

With all 24 tasks moving alongside both their plans, no task is left declaring a
`source_plan` in another repository — the boundary now falls between repos, not
through the ledger. Two loose ends remain and are reported honestly rather than
hidden:

- **`SR-001`'s `upstream: [BR-002]`** stays dangling; no `BR-*.md` exists anywhere.
  `factory trace` will keep reporting it as `dangling_upstream`.
- **The drone repo's 24 tasks satisfy no requirement**, so `factory trace status`
  against it will read close to 0% on `task->SR`. That is the true state and the
  reason the doctor pass exists.

---

## 7. Follow-on work, explicitly deferred

- Making the drone repo a first-class factory target: vendoring `.pi/skills/`,
  authoring `.factory/factory.yaml` with real harnesses, wiring validation.
- Fixing `factory requirements new`'s drone-specific binding template (§1.1).
- The doctor pass itself.

---

## 8. Verification

The split is done when **both** repositories pass their own gates from a clean
tree:

- Factory: `uv run pytest -m unit`, `uv run ruff check .`, `uv run pyright`, and
  the extension's `npm test` / `npm run typecheck` — with no reference remaining
  to `src/sim`, `src/drone`, `tests/sim` or `scenarios`.
- Factory: `factory-run` still completes against the factory itself with the sim
  gate absent — the §3.5 change proven, not assumed, since an unhandled gate
  lookup would raise `KeyError` at the validation node.
- Drone: its test suite runs, and `uv run python -m factory.trace status
  --project-root <drone>` reports a graph containing the moved tasks, the moved
  plans, and `SR-001`.
- A grep for `src/sim`, `src/drone`, `scenarios/` across the factory returns only
  historical references inside `docs/` and `kb/`, never live code or config.
