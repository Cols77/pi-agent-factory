# Engineering Context — High-Level Product Requirements

**Status:** Program-level requirements
**Applies to:** Engineering Context / V-Cycle / Goal-Driven Validation v2
**Date:** 2026-08-12
**Authority:** These requirements constrain the Engineering Context program and its increments.
Implementation plans MAY refine them but MUST NOT silently weaken or contradict them.

---

## 1. Product north star

`pi-agent-factory` is not primarily an autonomous code-generation system.

Coding models and coding agents are expected to improve independently and remain replaceable.
The factory's durable value is the engineering control layer surrounding those agents:

- preserving system intent;
- maintaining traceability between requirements, implementation and evidence;
- validating system behaviour rather than merely code correctness;
- exposing measurable engineering goals;
- automatically surfacing the evidence required to understand system state;
- preserving the developer's mental model as implementation velocity increases;
- retaining durable engineering memory from decisions, failures and evidence;
- continuously maintaining the freshness and authority of engineering artifacts as the repository evolves.

The target user experience is an **engineering cockpit for agentic development**:
a human engineer must be able to recover what the system is supposed to do, what changed,
why it changed, whether it works, what evidence proves that claim, and which parts of the
engineering representation have become obsolete.

This is particularly important for robotics, perception, embedded systems, autonomous systems,
simulation-heavy systems and other domains where successful compilation and unit tests are
insufficient evidence of correct system behaviour.

---

## 2. HLR-01 — Deterministic engineering orchestration

The factory SHALL own the deterministic execution structure around coding agents.

Coding agents MAY reason, propose implementations and perform bounded engineering work inside
explicit workflow nodes, but routing, scope, required gates, completion conditions, state
transitions and evidence ownership SHALL remain deterministic wherever practical.

The coding model SHALL remain replaceable.

### Required properties

- Explicit workflow state.
- Durable task/run state.
- Deterministic scope enforcement.
- Explicit validation and review gates.
- Failure and stop reasons remain visible.
- No agent may silently skip a required system gate.

---

## 3. HLR-02 — End-to-end engineering traceability

Significant system behaviour SHALL be traceable through the engineering lifecycle.

At minimum, where the corresponding artifacts exist, the system SHALL support navigation across:

```text
business intent
    ↓
system requirement
    ↓
feature / architecture / design decision
    ↓
implementation
    ↓
validation definition
    ↓
experiment / simulation run
    ↓
metric
    ↓
evidence
    ↓
current validation state
```

Traceability SHALL be based on explicit declared relations.
The factory MUST NOT invent semantic trace edges from LLM inference and present them as authoritative.

Missing links SHALL be surfaced as engineering gaps rather than hidden.

---

## 4. HLR-03 — System acceptance must be evidence-backed

A system requirement SHALL NOT be considered satisfied merely because:

- code compiles;
- unit tests pass;
- an implementation agent says the task is complete;
- an LLM judges the implementation plausible.

Where system behaviour is measurable, acceptance SHALL be connected to executable validation evidence.

Validation MAY include:

- deterministic tests;
- simulation;
- scenario-based acceptance;
- metric thresholds;
- repeated stochastic trials;
- hardware or physical-system observations;
- approved human evidence.

The evidence contract SHALL record enough provenance to determine what repository and validation state
the evidence actually proves.

---

## 5. HLR-04 — Agents must not self-certify success

The agent that implements a change SHALL NOT be the sole authority that defines, executes and certifies
the evidence proving its own correctness.

Acceptance evidence SHALL be owned by deterministic checks, separately-owned validation contracts,
trusted connectors, approved human review, or equivalent independent mechanisms.

The system SHALL distinguish:

```text
implementation claim
≠
acceptance evidence
≠
current validated state
```

An agent may report observations but SHALL NOT transform self-attestation into authoritative evidence.

---

## 6. HLR-05 — Preserve the developer's mental model

The factory SHALL actively reduce the cognitive cost of recovering system understanding after rapid
agentic development.

The developer SHALL be able to recover, for a feature or system slice:

- current intent;
- relevant requirements;
- major architecture/design decisions;
- implementation status;
- recent meaningful changes;
- validation state;
- goals and metrics;
- current failures or risks;
- relevant simulation/experiment evidence;
- unresolved questions;
- stale or invalidated engineering knowledge.

The system SHOULD prefer retrieval assistance, diagrams, contextual explanation and targeted
comprehension intervention over generic summaries or surveillance-style scoring.

---

## 7. HLR-06 — Relevant engineering evidence must surface proactively

The developer SHALL NOT be required to manually discover and correlate every validation artifact.

When the workflow reaches a meaningful engineering state, the factory SHOULD proactively surface the
most relevant existing artifact or view.

Examples:

- after a feature validation run, surface the relevant experiment result;
- when inspecting a requirement, surface its implementation and latest evidence;
- after a regression, surface the metric delta and relevant run;
- during `/catchup`, surface changed requirements, stale evidence and relevant diagrams;
- when a human asks about system behaviour, navigate to the corresponding engineering context.

Artifact surfacing SHALL reuse canonical information and deterministic trace relationships.

---

## 8. HLR-07 — Human observations must become reproducible engineering work

Human-observed system behaviour SHALL be easy to turn into traceable engineering input.

For supported environments such as simulation or playground execution, the system SHOULD make it
possible to capture:

- scenario;
- relevant system state;
- inputs;
- outputs;
- logs/telemetry;
- visual state where available;
- natural-language observation;
- associated feature/requirement when known.

The resulting finding SHALL be reusable by planning, implementation and validation workflows.

A human observation is not automatically a proven defect; it becomes an engineering finding that
can be investigated and converted into reproducible evidence.

---

## 9. HLR-08 — Metric-directed `/goal` engineering

The factory SHALL support engineering work directed toward measurable system outcomes.

A `/goal` is distinct from a requirement acceptance condition.

A requirement may say:

```text
reacquisition_rate >= 0.90
```

A goal workflow means:

```text
actively modify the system and run experiments
until reacquisition_rate >= 0.90
or an explicit budget / stopping condition is reached
```

A goal contract SHOULD support:

- target metric;
- target threshold or objective;
- measurement population;
- guardrails;
- baseline;
- confidence requirements where applicable;
- experiment budget;
- stopping rule;
- metric version;
- goal version.

Every attempted improvement SHOULD remain traceable to:

```text
goal
→ implementation/configuration change
→ experiment
→ metric result
→ decision
```

Goal status SHALL be evidence-backed and SHALL support regression after previously reaching the target.

---

## 10. HLR-09 — Automatic artifact freshness and change propagation

The factory SHALL guarantee that engineering artifacts do not silently remain authoritative after
the repository state they depend on has changed.

Freshness is a cross-cutting engineering property, not a special case limited to validation evidence.

### 10.1 Required freshness states

Where applicable, derived or dependent artifacts SHALL expose an explicit state such as:

```text
FRESH
STALE
REFRESHING
REFRESH_REQUIRED
BLOCKED
SUPERSEDED
UNKNOWN
```

Exact internal vocabulary MAY differ, but the following invariant is mandatory:

> An artifact with unresolved dependency divergence MUST NOT be silently presented as current.

Missing provenance SHALL degrade authority. It SHALL NOT imply freshness.

### 10.2 Staleness is dependency-graph based

The freshness mechanism SHALL operate on explicit artifact dependencies rather than hard-coded
"requirement changed" rules.

Possible invalidation sources include:

#### Intent and contract changes

- business requirement;
- system requirement;
- goal;
- metric definition;
- acceptance threshold;
- ADR / design decision.

#### Implementation changes

- source code;
- configuration;
- interface;
- dependency;
- algorithm;
- model;
- prompt/policy where behaviour depends on it.

#### Validation changes

- scenario;
- fixture;
- dataset;
- ground truth;
- simulation model;
- harness;
- scorer;
- metric extractor;
- trial population;
- statistical policy.

#### Evidence changes

- newer contradicting experiment;
- regression;
- newly observed failure;
- hardware/physical-system evidence.

#### Engineering knowledge changes

- superseded ADR;
- corrected root cause;
- rejected hypothesis;
- updated feature membership or trace relation.

#### Generator changes

- explainer generator;
- diagram generator;
- documentation schema;
- ontology/query logic used to derive a projection.

### 10.3 Transitive change propagation

If artifact `A` changes and `B` depends on `A`, then `B` SHALL be re-evaluated.

If `C` depends on `B`, the impact SHALL propagate transitively unless an explicit freshness boundary
states otherwise.

Example:

```text
SR-017
  ↓
navigation implementation
  ↓
EXP-004 validation
  ↓
DIAG-009
  ↓
visual explainer
```

Changing `SR-017` may therefore invalidate the implementation claim, evidence, diagram and explainer.

### 10.4 Artifact authority classes

Automatic freshness restoration SHALL depend on artifact authority.

#### Class A — Authoritative engineering contracts

Examples:

- BRs;
- SRs;
- accepted ADRs;
- goal definitions;
- metric definitions;
- acceptance thresholds.

These SHALL NOT be silently rewritten because a downstream artifact changed.

A contract change MAY invalidate downstream artifacts.

Changing authoritative intent requires the appropriate author/review workflow.

#### Class B — Implementation

Examples:

- source code;
- configuration;
- scenarios with behavioural semantics;
- model/policy implementation.

Implementation MAY become semantically stale after upstream contract changes.

The factory SHALL route required semantic repair through the controlled engineering workflow
(e.g. task → DEV → validation → review), rather than treating implementation as a generated projection.

Autonomous execution MAY occur where policy permits, but the engineering change remains explicit,
traceable and reviewable.

#### Class C — Validation evidence

Examples:

- test runs;
- simulation runs;
- traces;
- metrics;
- screenshots;
- validation reports.

Evidence SHALL become stale when any relevant dependency used to establish the claim changes.

Historical evidence SHALL be retained, but stale historical evidence SHALL NOT prove current state.

Where execution is safe, deterministic and within configured resource policy, the factory SHOULD
automatically rerun validation.

Otherwise it SHALL mark `REFRESH_REQUIRED` and expose the unresolved state.

#### Class D — Generated engineering knowledge

Examples:

- V-cycle diagrams;
- architecture diagrams;
- visual explainers;
- feature dossiers;
- requirement summaries;
- goal charts;
- experiment summaries;
- generated engineering documentation.

These artifacts are primary candidates for automatic regeneration.

When their declared dependencies diverge, the system SHOULD:

```text
mark stale
→ regenerate automatically where safe
→ verify generated provenance/fingerprints
→ publish as current
```

Generated artifacts SHALL NOT remain indefinitely stale merely because regeneration requires a
manual command when the factory already knows how to regenerate them safely.

#### Class E — Derived projections and indexes

Examples:

- SCC browser projections;
- trace indexes;
- reverse-edge indexes;
- feature health summaries;
- `/catchup` derived views.

These SHALL be recomputable from canonical artifacts.

A persisted projection/index SHALL be rebuildable and MUST NOT become a second source of truth.

### 10.5 Provenance contract

Dependent/generated artifacts SHALL declare or deterministically expose the dependencies needed to
evaluate their freshness.

Conceptually:

```yaml
derived_from:
  - ref: sr:SR-017
    fingerprint: sha256:...
  - ref: adr:ADR-004
    fingerprint: sha256:...
  - ref: code:src/navigation/preemption.py
    fingerprint: sha256:...
  - ref: metric:METRIC-003
    fingerprint: sha256:...

generated_by:
  kind: visual-explainer
  version: ...
  generator_fingerprint: ...

generated_at_commit: abc123...
```

The implementation SHALL reuse existing factory fingerprint and trace primitives where possible.
The exact persisted schema SHALL be defined by the relevant increment design.

### 10.6 Refresh policy

Freshness detection and freshness restoration are separate concerns.

The system SHALL implement a deterministic policy that resolves each stale artifact to one of:

```text
RECOMPUTE
REGENERATE
RERUN_VALIDATION
ROUTE_TO_DEV
REQUEST_HUMAN_ACTION
SUPERSEDE
```

LLM judgment SHALL NOT decide whether an artifact is stale.

Agents MAY perform the semantic work required by `REGENERATE` or `ROUTE_TO_DEV`, but dependency
resolution and resulting freshness state SHALL remain deterministic.

### 10.7 Freshness closure

The system SHALL expose whether an impacted engineering slice has reached **freshness closure**.

A feature reaches freshness closure when every impacted reachable artifact is:

- fresh;
- explicitly superseded; or
- explicitly unresolved with a visible reason and required action.

There SHALL be no hidden stale descendants.

Example:

```text
Change:
  SR-017 modified

Affected:
  code:navigation/preemption.py      REFRESH_REQUIRED
  evidence:EXP-004                   STALE
  diag:DIAG-NAV-009                  REFRESHING
  explainer:nav-preemption           REFRESHING

Automatic actions:
  ✓ regenerated diagram
  ✓ regenerated explainer
  ⟳ routed implementation repair to DEV

Freshness closure:
  NOT REACHED
```

After implementation and validation:

```text
Implementation updated
Validation rerun
Goal re-evaluated
Generated knowledge refreshed

Freshness closure:
  REACHED
```

### 10.8 `/catchup` integration

`/catchup` SHALL report not only what changed, but what the changes invalidated and what the factory
did about those invalidations.

Example:

```text
Since your last review:

Requirements
  SR-017 changed

Implementation
  navigation preemption updated

Automatically invalidated
  2 validation runs
  1 diagram
  2 visual explainers

Automatically refreshed
  diagram
  explainers
  validation evidence

Remaining stale
  none

Metric
  reacquisition_rate 0.93 → 0.96

Freshness closure
  REACHED
```

### 10.9 Historical truth must be preserved

Automatic refresh SHALL NOT erase history.

The factory SHALL distinguish:

```text
current engineering truth
from
historical engineering record
```

Old evidence remains attributable to the commit/configuration it evaluated.
Old generated knowledge MAY remain in history while ceasing to be the current projection.
Failure records, rejected hypotheses and superseded decisions remain durable engineering memory.

---

## 11. HLR-10 — Durable project memory must store engineering knowledge, not chat history

The factory SHALL preserve engineering knowledge that materially improves future decisions.

Memory SHOULD include:

- requirements and their evolution;
- accepted decisions and rationale;
- evidence;
- failure records;
- root causes;
- rejected hypotheses;
- experiment outcomes;
- important implementation lessons;
- operational/project knowledge that is likely to recur.

Conversation transcripts SHALL NOT become the canonical memory model.

Every durable memory item SHOULD retain provenance to the engineering state that produced it.

The current system SHALL be distinguishable from historical knowledge.

---

## 12. Program-level invariants

The following invariants apply to every Engineering Context increment.

1. No stale artifact is silently presented as current.
2. No stale validation evidence may establish current requirement satisfaction.
3. Missing evidence is reported as missing, not inferred.
4. Missing provenance is not interpreted as freshness.
5. An implementation agent cannot self-certify acceptance.
6. Authoritative upstream contracts are not silently rewritten by downstream automation.
7. Safe generated projections should be automatically restored when their dependencies change.
8. Historical evidence and decisions are preserved when current projections are refreshed.
9. Trace relationships presented as authoritative are explicitly declared or deterministically derived
   from an authoritative contract.
10. Human-visible and agent-visible views must agree on canonical engineering state.
11. LLM narrative never overrides deterministic state.
12. Derived indexes/projections are rebuildable.
13. Current unresolved staleness remains visible until freshness closure is reached or the artifact is
    explicitly superseded.
14. Coding models and coding-agent implementations remain replaceable components behind the engineering
    control plane.

---

## 13. Thin-slice acceptance for the program

The Physical Agentic AI Drone remains the reference vertical slice.

A navigation pre-emption feature SHALL demonstrate the following end-to-end behaviour.

### Scenario A — Requirement changes

Initial state:

```text
SR
→ implementation
→ validation
→ metric
→ evidence
→ diagram
→ explainer

all FRESH
```

Modify the semantics of the SR.

Expected:

1. The changed SR remains authoritative.
2. Dependent implementation is identified as requiring engineering review/repair.
3. Existing validation evidence becomes stale.
4. Dependent diagrams and explainers become stale.
5. Feature/system health shows degraded freshness.
6. Safe generated artifacts are automatically regenerated where possible.
7. Semantic implementation repair is routed through DEV.
8. Relevant validation is rerun after implementation repair.
9. Goals/metrics are re-evaluated.
10. Freshness is reconciled transitively.
11. `/catchup` reports what changed, what was invalidated, what was repaired and what remains unresolved.
12. Historical pre-change evidence remains accessible but no longer proves the current requirement.
13. The feature eventually reaches freshness closure or remains explicitly unresolved.

### Scenario B — Implementation changes without requirement changes

Modify only code implementing the feature.

Expected:

1. The SR remains authoritative and fresh.
2. Relevant evidence becomes stale.
3. Generated knowledge that explains the changed implementation becomes stale.
4. Appropriate validation reruns.
5. Generated explainers/diagrams are refreshed.
6. Requirement/goal status is re-evaluated.
7. Freshness closure is reported.

This second scenario is mandatory to prove that freshness is dependency-driven rather than hard-coded
around requirement edits.

---

## 14. Final product criterion

As coding agents autonomously modify the repository, the factory SHALL continuously preserve a
coherent, traceable and current engineering representation of the system.

Changes SHALL automatically invalidate dependent claims and artifacts, restore freshness wherever
safely possible, route semantic repairs through controlled engineering workflows, re-establish
executable evidence, preserve historical truth, and expose remaining unresolved state.

The human engineer should not have to manually reconstruct which parts of the project's understanding
became obsolete.
