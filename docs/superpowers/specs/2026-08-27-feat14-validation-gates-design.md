# FEAT-14 — Validation Gates (VALIDATION-GATES)

_Status: **design dossier** (2026-08-27). Owner: Python factory orchestrator + coherence layer. This is the **gate-taxonomy contract** that makes "depending on workflow execution, various gates are required" expressible as a named, composable contract. Planning/design only.

_Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (FEAT-14 proposal; locked decisions D-B, D-D). Companion: FEAT-13 (GOVERNED-EXECUTION-DRIVER) uses these gates; FEAT-15 (POLISH-FLOW) surfaces the human-visualization gate.

---

## 1. Purpose

Today the factory orchestrator runs a **fixed node pipeline** (context-gather → dev → validation → review → session-review) and invokes gates via `ConfigGateRunner` with hard-coded keys (`unit`, `lint`, `typecheck`, `sim`, etc.). Gates exist and run, but they are **not a first-class, nameable, composable taxonomy**: there is no contract that says "this workflow requires `unit` + `agentic_review` + `sim_regression`; that workflow requires `human_review` + `sim_human_visualization`". The *which gates run when* logic lives implicitly in the runner, not in a declared, inspectable contract.

This FEAT makes the **gate taxonomy a named contract** so that:
- A **workflow** (FEAT-16 MODULAR-WORKFLOWS) declares its required gates by `kind` in `factory.yaml`
- The **governed execution driver** (FEAT-13) can inspect `gate.kind.requiredness` and `gate.kind.resolve_cmd` to decide ordering, parallelism, and blocking
- **Human-visualization/exploratory** (the polish playground) becomes a first-class gate `sim_human_visualization` — per the polish spec: "a HUMAN must confirm a requirement genuinely works"
- Reuse is maximized: `ConfigGateRunner`, `run_review`, `HumanReviewGate`, `sim` gate, `playground`, `devserver` — no new enforcement logic

User-facing problem solved: **Teams can declare, compose, and inspect validation requirements per workflow without forking the orchestrator.**

---

## 2. Built-already vs genuinely-new

### Built-already (cite file paths + symbols)
| Capability | Location | Notes |
|------------|----------|-------|
| `ConfigGateRunner` + `GateRunner` protocol + `GateRun` | `src/factory/orchestrator/backends.py:42-120` | Undeclared gate skips and passes (`GATE_NOT_APPLICABLE=-1`); `pytest` exit 5 normalized |
| Node pipeline (fixed order) | `src/factory/orchestrator/runner.py:180-350` | `run_context_gatherer`, `run_dev`, `run_validation`, `run_review`, `run_session_review` |
| `HumanReviewGate` + `GrillGate` | `src/factory/orchestrator/runner.py:220-280` | Blocks until decision file written; profile-disablable |
| `run_review` (agentic code review) | `src/factory/orchestrator/nodes.py:140-200` | Dispatches `AgentRole.REVIEW`; returns `NodeOutcome` |
| `sim` gate (automated regression) | `src/factory/orchestrator/backends.py:120-160` | Runs via `ConfigGateRunner`; `harnesses` in `factory.yaml` |
| Polish playground + `devserver` (human-visualization) | `src/factory/polish/playground.py`, `devserver.py`, `orchestrator.py` | "Two faces: automated harness / exploratory playground"; already implemented (18 files) |
| `FactoryConfig` parsing `gates`, `harnesses`, `playgrounds` | `src/factory/config.py:60-180` | Reads `factory.yaml`; `GateConfig`, `HarnessConfig`, `PlaygroundConfig` |
| Configurable gates spec (Approved) | `docs/superpowers/specs/2026-08-05-project-configurable-gates-design.md` | Per-project gate registry; undeclared → skip |

### Genuinely-new (the delta)
| Delta | Why it's new |
|-------|--------------|
| **Gate taxonomy enum** (`kind ∈ {unit, agentic_review, human_review, sim_regression, sim_human_visualization, integration, full}`) | No enum exists; keys are strings scattered in code |
| **Gate contract per kind**: `requiredness` (required/optional/advisory), `resolve_cmd` (how to run), `node` (which pipeline node runs it), `parallelizable` (bool) | Currently implicit in runner logic |
| **Workflow → gate binding** in `factory.yaml` (FEAT-16 consumes this) | Today gates are global; workflows need per-workflow selection |
| **Human-visualization as first-class gate** (`sim_human_visualization`) | Exists as playground but not in taxonomy; polish spec mandates it |
| **Gate registry API** (`coherence gates list --json`, `coherence gates describe <kind>`) | No CLI to inspect the taxonomy |

---

## 3. Proposed design

### 3.1 Gate taxonomy enum + contract (new types)

**File:** `src/coherence/gate/taxonomy.py` (new)

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class GateKind(str, Enum):
    UNIT = "unit"
    AGENTIC_REVIEW = "agentic_review"
    HUMAN_REVIEW = "human_review"
    SIM_REGRESSION = "sim_regression"
    SIM_HUMAN_VISUALIZATION = "sim_human_visualization"
    INTEGRATION = "integration"
    FULL = "full"  # composite: all above

class Requiredness(str, Enum):
    REQUIRED = "required"      # blocks pipeline if fails
    OPTIONAL = "optional"      # runs but non-blocking
    ADVISORY = "advisory"      # runs, reports only

@dataclass(frozen=True)
class GateContract:
    kind: GateKind
    requiredness: Requiredness
    resolve_cmd: str           # e.g. "pytest -x", "coherence run-review", "coherence playground"
    node: str                  # "validation", "review", "session_review", "polish"
    parallelizable: bool = False
    depends_on: tuple[GateKind, ...] = ()
    description: str = ""
```

### 3.2 Built-in registry (default contracts)

**File:** `src/coherence/gate/registry.py` (new) — consumes `FactoryConfig.gates` from `factory.yaml`

```python
DEFAULT_CONTRACTS: dict[GateKind, GateContract] = {
    GateKind.UNIT: GateContract(
        kind=GateKind.UNIT,
        requiredness=Requiredness.REQUIRED,
        resolve_cmd="pytest -x -q",
        node="validation",
        parallelizable=True,
        description="Fast unit test suite; runs in validation node"
    ),
    GateKind.AGENTIC_REVIEW: GateContract(
        kind=GateKind.AGENTIC_REVIEW,
        requiredness=Requiredness.REQUIRED,
        resolve_cmd="coherence run-review --role validation",
        node="review",
        parallelizable=True,  # FEAT-13 swarms this
        description="Agentic code review (spec-compliance + code-quality)"
    ),
    GateKind.HUMAN_REVIEW: GateContract(
        kind=GateKind.HUMAN_REVIEW,
        requiredness=Requiredness.REQUIRED,
        resolve_cmd="coherence human-review --await",
        node="session_review",
        parallelizable=False,
        depends_on=(GateKind.AGENTIC_REVIEW,),
        description="Human review gate; blocks until decision file written"
    ),
    GateKind.SIM_REGRESSION: GateContract(
        kind=GateKind.SIM_REGRESSION,
        requiredness=Requiredness.REQUIRED,
        resolve_cmd="coherence sim --harness regression",
        node="validation",
        parallelizable=False,
        description="Automated simulation regression (sim_live)"
    ),
    GateKind.SIM_HUMAN_VISUALIZATION: GateContract(
        kind=GateKind.SIM_HUMAN_VISUALIZATION,
        requiredness=Requiredness.REQUIRED,
        resolve_cmd="coherence playground --devserver --requirement <id>",
        node="polish",  # new node for FEAT-15
        parallelizable=False,
        depends_on=(GateKind.SIM_REGRESSION,),
        description="Human exploratory playground; human must confirm requirement genuinely works"
    ),
    GateKind.INTEGRATION: GateContract(
        kind=GateKind.INTEGRATION,
        requiredness=Requiredness.OPTIONAL,
        resolve_cmd="pytest -x -q -m integration",
        node="validation",
        parallelizable=True,
        description="Integration tests; optional by default"
    ),
    GateKind.FULL: GateContract(
        kind=GateKind.FULL,
        requiredness=Requiredness.REQUIRED,
        resolve_cmd="coherence run-all-gates",
        node="session_review",
        parallelizable=False,
        depends_on=(GateKind.UNIT, GateKind.AGENTIC_REVIEW, GateKind.HUMAN_REVIEW,
                    GateKind.SIM_REGRESSION, GateKind.SIM_HUMAN_VISUALIZATION),
        description="Composite gate; runs all required gates in dependency order"
    ),
}
```

### 3.3 `factory.yaml` schema extension (backward-compatible)

```yaml
# factory.yaml
gates:
  # Declare which gates this project uses (subset of taxonomy)
  - kind: unit
    requiredness: required
  - kind: agentic_review
    requiredness: required
  - kind: human_review
    requiredness: required
  - kind: sim_regression
    requiredness: required
  - kind: sim_human_visualization
    requiredness: required
    # playground config lives under playgrounds:
playgrounds:
  - name: default
    devserver: true
    requirement_selector: "interactive"  # or list of requirement IDs
harnesses:
  - name: regression
    command: "python -m pytest tests/sim -x"
```

**Parsing:** `src/factory/config.py` already parses `gates`, `harnesses`, `playgrounds` into `FactoryConfig`. Extend `GateConfig` with `kind: GateKind` (enum) and validate against taxonomy.

### 3.4 Runner integration (reuse, not rewrite)

**File:** `src/factory/orchestrator/backends.py` — `ConfigGateRunner.run_detail(gate_key)`

- Map `gate_key` → `GateKind` → `GateContract` from registry
- Execute `resolve_cmd` via existing subprocess logic (already handles `pytest` exit 5, `GATE_NOT_APPLICABLE`)
- Return `GateRun` with `kind`, `passed`, `output`, `duration_ms`
- **No new enforcement** — the existing `GateRunner` protocol is unchanged

**File:** `src/factory/orchestrator/nodes.py` — `run_validation`, `run_review`, `run_session_review`

- Each node queries the workflow's declared gates (via `FactoryConfig`) filtered by `contract.node == this_node`
- Runs them via `ConfigGateRunner` (parallel where `parallelizable=True`)
- `HumanReviewGate` already exists for `human_review` kind; `sim_human_visualization` routes to polish playground

### 3.5 CLI for taxonomy inspection (new)

**File:** `src/coherence/cli/gates.py` (new) — adds to `coherence` CLI group

```bash
coherence gates list --json          # all kinds with contracts
coherence gates describe unit        # single kind detail
coherence gates validate             # validates factory.yaml gates against taxonomy
```

### 3.6 FEAT-13 / FEAT-15 / FEAT-16 consumption

| Feature | How it uses the taxonomy |
|---------|--------------------------|
| FEAT-13 GOVERNED-EXECUTION-DRIVER | `WorktreeDriver` reads workflow's declared gates → runs in dependency order → blocks on `required` |
| FEAT-15 POLISH-FLOW | Adds `polish` node; `sim_human_visualization` gate runs there; `playground` + `devserver` reused |
| FEAT-16 MODULAR-WORKFLOWS | `Workflow` definition in `factory.yaml` includes `gates: [unit, agentic_review, ...]` per workflow |

---

## 4. Scope — one tracer-bullet task list (G-/D-/T-style)

| Task | Description | Verify / Acceptance |
|------|-------------|---------------------|
| **G-01** Define taxonomy enum + contracts | Create `src/coherence/gate/taxonomy.py` + `registry.py` with `DEFAULT_CONTRACTS` | `python -c "from coherence.gate.taxonomy import GateKind; print(GateKind.SIM_HUMAN_VISUALIZATION)"` works; all 7 kinds present |
| **G-02** Extend `FactoryConfig` gate parsing | `src/factory/config.py`: `GateConfig.kind: GateKind`; validate against taxonomy; merge with `DEFAULT_CONTRACTS` | `coherence gates validate` passes on a sample `factory.yaml` with all 7 kinds; unknown kind → clear error |
| **G-03** Wire `ConfigGateRunner` to contracts | `src/factory/orchestrator/backends.py`: `run_detail` resolves `kind` → `GateContract` → `resolve_cmd` | `ConfigGateRunner().run_detail("unit")` runs `pytest`; `run_detail("sim_human_visualization")` invokes playground CLI |
| **G-04** Node-level gate filtering | `src/factory/orchestrator/nodes.py`: each node runs only gates with `contract.node == node_name` | `run_validation` runs unit + sim_regression; `run_review` runs agentic_review; `run_session_review` runs human_review |
| **G-05** CLI taxonomy surface | `src/coherence/cli/gates.py`: `list`, `describe`, `validate` commands | `coherence gates list --json` outputs all 7 contracts with fields; `describe sim_human_visualization` shows playground cmd |
| **G-06** FEAT-13 integration smoke test | Run `coherence run-governed` (FEAT-13) on a task that declares all 7 gates in `factory.yaml` | All gates execute in dependency order; `sim_human_visualization` launches playground; human review blocks until decision |
| **G-07** Polish-node gate + FEAT-15 de-coupling | Add `sim_human_visualization` gate so it runs where the taxonomy routes it; **de-couple from FEAT-15 shipping** — by default it runs in the `session_review` node with a playground decision-file; FEAT-15 (its own slice) may then move it to a dedicated `polish` node | The gate works standalone (blocks until human confirm) WITHOUT FEAT-15 present; FEAT-15's polish-node move is a follow-on, not a hard dependency |
| **G-08** Migrate legacy string gate keys | `src/factory/config.py` + a one-time migration: map existing `factory.yaml` string keys (`unit`, `sim`, …) → `GateKind` enum; support both during transition; the existing single `sim` gate maps to `SIM_REGRESSION` (its harness) **and** its human/visualization counterpart handled by `sim_human_visualization` specifically | `coherence gates validate` passes on a pre-existing project's `factory.yaml` (no new key required); a legacy `sim` harness still runs as `sim_regression`; unknown keys → clear migration error |
| **G-09** Parallel gate batch + dependency order | `src/factory/orchestrator/backends.py` (or a thin runner): batched execution of `parallelizable=True` gates with `depends_on` DAG topological sort; keep single-gate path byte-compatible | Given `depends_on=(SIM_REGRESSION,)` on `SIM_HUMAN_VISUALIZATION`, the runner runs `sim_regression` then batches it; parallel flags run concurrently; ordering respected |
| **G-10** Shared cross-FEAT contract (FEAT-16/14) | Define the shared `Workflow.gates: list[GateKind]` in the shared taxonomy location (`coherence.gate.taxonomy`) as the single source of truth, so FEAT-16's `Workflow` never drifts to string keys | A FEAT-16 `Workflow` importing `GateKind` type-checks; a string-keyed workflow is rejected at load |

---

## 5. Files likely to change + Risks/open questions

### Files likely to change (planned)
| File | Change type |
|------|-------------|
| `src/coherence/gate/taxonomy.py` | New |
| `src/coherence/gate/registry.py` | New |
| `src/coherence/cli/gates.py` | New |
| `src/factory/config.py` | Modify: `GateConfig.kind: GateKind`; validation |
| `src/factory/orchestrator/backends.py` | Modify: `ConfigGateRunner.run_detail` uses registry |
| `src/factory/orchestrator/nodes.py` | Modify: node-level gate filtering by `contract.node` |
| `src/factory/orchestrator/runner.py` | Modify: pass workflow's gate config to nodes |
| `docs/superpowers/specs/2026-08-05-project-configurable-gates-design.md` | Update: reference taxonomy enum + contracts |

### Risks & open questions
1. **`sim_human_visualization` blocking semantics** — playground is interactive; the gate must block until human writes a decision file (like `HumanReviewGate`). Reuse `HumanReviewGate` pattern with a playground-specific decision file.
2. **Parallelism vs dependency order** — `parallelizable=True` gates can run concurrently; `depends_on` creates a DAG. The runner must topologically sort. Confirm `ConfigGateRunner` can batch parallel gates.
3. **Backward compatibility** — existing `factory.yaml` with string gate keys must still work. Migration: map legacy keys → `GateKind` in config parsing.
4. **FEAT-16 workflow gate binding** — the `Workflow` type (FEAT-16) must reference `GateKind` enum, not strings. Ensure the enum is in a shared location (`coherence.gate.taxonomy`) both factory and coherence import.
5. **Human-review profile disable (D-C)** — `HumanReviewGate` already supports profile-disabled. `sim_human_visualization` should respect the same profile setting.

---

## 6. Feature completion / acceptance (NOT a task DoD)

> Note on levels: "Definition of done" is **task-scoped** here — `dod_met` is a field on
> `TaskResult` (`src/factory/orchestrator/types.py`), the gate a *task* passes. A feature is an
> aggregate: it is **done** only when the tasks satisfying its SRs each pass their own DoD and the
> feature's SR/invariants are satisfied + gated. The acceptance criteria below are that feature-level
> aggregate, not a single DoD.

### Feature acceptance criteria
- `src/coherence/gate/taxonomy.py` + `registry.py` + `cli/gates.py` exist and pass unit tests (all 7 kinds + G-08 migration + G-09 parallel batch + G-10 shared contract)
- `coherence gates list --json` outputs all 7 kinds with complete contracts
- `ConfigGateRunner` executes each `resolve_cmd` via the registry (unit, agentic_review, human_review, sim_regression, sim_human_visualization, integration, full) — and **legacy `factory.yaml` string keys migrate** (G-08)
- Nodes run only their assigned gates; `sim_human_visualization` works standalone (blocks until human confirm in `session_review` by default — **not gated on FEAT-15**) and is later relocated to a `polish` node by FEAT-15
- Parallel gates batch + `depends_on` order respected (G-09); FEAT-16 `Workflow.gates` imports `GateKind` (G-10)
- A `factory.yaml` declaring all 7 gates runs end-to-end via `coherence run-governed` (FEAT-13) with correct blocking/parallelism

### Verdict: **YES, this should be a FEAT**

The taxonomy is **not** just documentation — it is a **runtime contract** that FEAT-13, FEAT-15, and FEAT-16 all consume. Without it:
- FEAT-13 cannot express "this workflow requires these gates in this order"
- FEAT-15 cannot promote playground to a first-class required gate
- FEAT-16 cannot declare per-workflow gate selection in `factory.yaml`
- The "configurable gates" spec (2026-08-05) remains a partial implementation (global gates only)

The delta is small (enum + registry + CLI + wiring) but **unlocks composition** across three locked FEATs. It reuses every existing component (`ConfigGateRunner`, `run_review`, `HumanReviewGate`, `sim`, `playground`, `devserver`) — no new enforcement logic. This is exactly a tracer-bullet vertical slice: substrate (enum) → coherence (registry/CLI) → factory (config/runner/nodes) → hosts (FEAT-13/15/16 consume it).

---

**Written to:** `C:/coding/pi-agent-factory/docs/superpowers/specs/2026-08-27-feat14-validation-gates-design.md`  
**Line count:** 203