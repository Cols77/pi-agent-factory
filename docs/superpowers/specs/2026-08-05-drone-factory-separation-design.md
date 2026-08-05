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

**Move (drone, 20):** T-029, T-030, T-031, T-032, T-033, T-034, T-035, T-036,
T-037, T-038, T-039, T-041, T-042, T-043, T-044, T-045, T-046, T-047, T-048, T-050.

**Rulings on the four whose deliverables straddle the boundary:**

| task | title | ruling | why |
|---|---|---|---|
| T-049 | Scenario YAML Files | **drone** | delivers `scenarios/*.yaml`; the automated test missed it only because its body cites no backticked path |
| T-051 | Pytest Marker Update and Smoke Test | **drone** | its subject is the sim suite; the `sim` marker follows the sim tests |
| T-040 | Factory Gate & Project Config | **factory** | delivers `pyproject.toml` markers and `scripts/gates/`; it configured the factory to run drone tests, which is factory machinery |
| T-052 | Update Factory Gate Scripts | **factory** | same — gate scripts are factory infrastructure |

T-040 and T-052 stay behind while their `source_plan` moves, which leaves them
declaring a plan that no longer exists in the factory. That is a real gap, and
`factory trace` will report it as `task_plan_missing` rather than hiding it. It is
resolved in §6, not papered over.

### 3.4 Dependencies

Move `pygame>=2.6.1` and `matplotlib>=3.11.1` from the factory's `pyproject.toml`
to the drone's. Neither is used by `src/factory/`; both exist solely for the sim
testbench and its plotter.

### 3.5 Gates and markers — reconstruct, do not move

Once `tests/sim/` leaves, the factory's `sim` pytest marker and
`scripts/gates/sim_smoke.py` describe tests it no longer has, while the drone repo
needs equivalents it does not have.

- **Factory:** drop the `sim` marker and `sim_smoke.py`, and remove the sim gate
  from any pipeline that references it.
- **Drone:** gains its own `sim` marker and smoke gate, written to fit that repo.

This is the one part of the split that is not a file move, and it is where the
factory's own test suite is most likely to break. It is called out separately for
that reason.

---

## 4. What each repository looks like afterwards

**Factory** — `src/factory/` only; 25 tasks, all factory work; 20 specs and 27
plans of factory design; no `pygame`/`matplotlib`; its own gates unchanged except
for the removed sim gate.

**Drone** — `src/drone/` and `src/sim/`; `tests/sim/`; `scenarios/`; 22 tasks;
2 product specs and 2 plans; `requirements/SR-001.md` finally sitting beside the
code it constrains.

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

- **T-040 and T-052** keep a `source_plan` whose file has moved. Rather than
  rewrite their frontmatter to a path in another repository — which no tool in
  either repo can resolve — they are re-pointed at the factory plan that actually
  governs the gate work they did, or, if none fits, their `source_plan` is dropped
  and the resulting `task_no_plan` gap is closed through `/trace-fix` like any
  other. Deciding which is a judgement call for the human at execution time.
- **`SR-001`'s `upstream: [BR-002]`** remains dangling. Out of scope here; it is a
  real gap and `factory trace` will keep reporting it.

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
- Drone: its test suite runs, and `uv run python -m factory.trace status
  --project-root <drone>` reports a graph containing the moved tasks, the moved
  plans, and `SR-001`.
- A grep for `src/sim`, `src/drone`, `scenarios/` across the factory returns only
  historical references inside `docs/` and `kb/`, never live code or config.
