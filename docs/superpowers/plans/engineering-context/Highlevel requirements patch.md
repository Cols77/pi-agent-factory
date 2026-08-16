Below is the patch I would give your coding agent. It is deliberately **documentation-only**, assumes **SP-B is currently in progress and must not be disturbed**, and treats the current `main` at `4c247e7` as the baseline. The existing roadmap already makes SP-B an upstream prerequisite of Inc 6, so this extends that architecture rather than changing SP-B underneath the active agent.

I recommend **four edits plus one new file**.

---

## 1. NEW FILE

`docs/superpowers/plans/engineering-context/00-high-level-requirements.md`

Copy the following whole file:

````markdown
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
````

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

````

---

# 2. UPDATE `00-program-architecture.md`

The current document already has the Engineering Cockpit gap matrix, D1–D8, diagrams, goals and durable memory, so I would **not rewrite it wholesale**. It already explicitly identifies the cockpit pillars and maps them into Inc 1–8. 

### A. Add after `## 1. Purpose`

```markdown
### 1a. Program requirements

This program is governed by
[`00-high-level-requirements.md`](./00-high-level-requirements.md).

The increment plans are implementation decompositions of those high-level requirements.
Where an increment plan and a program-level HLR conflict, the HLR is authoritative until the
conflict is explicitly resolved through a program decision.

In particular, the program now treats **artifact freshness as a maintained system property**, not
merely stale-state detection:

```text
detect change
→ determine impacted dependency closure
→ invalidate dependent authority
→ select refresh policy
→ recompute / regenerate / rerun / route semantic repair
→ reconcile
→ report freshness closure
````

This does **not** mean blindly auto-editing every stale artifact.

The refresh policy distinguishes:

- authoritative engineering contracts;
    
- implementation;
    
- validation evidence;
    
- generated engineering knowledge;
    
- derived projections/indexes.
    

Authoritative upstream intent is protected from silent mutation, while safely reproducible downstream  
artifacts SHOULD be restored automatically.

### Concurrency constraint — SCC SP-B

At the time this requirement update was authored, **SCC SP-B is already under active implementation**.

Therefore:

- SP-B remains an upstream frozen dependency for this change;
    
- this program update does not alter SP-B's implementation contract;
    
- no freshness work should modify SP-B-owned files while SP-B is in flight;
    
- later Engineering Context increments consume the landed SP-B browser substrate;
    
- any browser surfacing required by freshness is added after SP-B, through the already planned  
    Engineering Context UI integration.
    

This preserves the existing SCC → Engineering Context dependency boundary.

````

### B. Add one line to the gap matrix

Add this row to §3a:

```markdown
| Automatic artifact freshness / change propagation | **partial → first-class HLR** | Existing `factory.freshness`, evidence reconciliation and explainer freshness provide detection primitives. Extend Inc 7 from stale detection to graph-based invalidation, refresh policy, automatic safe regeneration/rerun and freshness closure. See HLR-09. |
````

### C. Add to `## 3. Genuinely new v2 surface`

Add this row:

```markdown
| **Artifact freshness graph + refresh reconciliation** | extend `factory.freshness` / trace dependency graph with impact resolution, refresh policy and closure | Inc 1 ontology + Inc 3 evidence + Inc 7 |
```

### D. Change Increment 7 description in §4

Replace:

```markdown
| **7** | Context delta + validation status | §37 Phase 7 | `/catchup`, human checkpoints, goal-aware `VALIDATED`/`VERIFICATION_STALE`/`REGRESSED`, change impact | pi-agent-factory |
```

with:

```markdown
| **7** | Context delta + freshness reconciliation | §37 Phase 7 + HLR-09 | `/catchup`, human checkpoints, goal-aware validation state, dependency-driven change impact, transitive staleness propagation, refresh policy, automatic safe regeneration/rerun, freshness closure | pi-agent-factory |
```

### E. Add a new locked decision D9

Where D1–D8 are documented, add:

````markdown
### D9 — Freshness is maintained, not merely detected

**Decision:** artifact freshness is a first-class system property governed by HLR-09.

The system SHALL distinguish:

```text
change detection
→ staleness propagation
→ refresh policy
→ remediation
→ reconciliation
→ freshness closure
````

Existing fingerprint/staleness mechanisms are reused as primitives.

The implementation SHALL NOT create per-artifact freshness silos where the existing trace/freshness  
graph can represent the dependency.

Refresh policy is authority-aware:

|Artifact class|Default response to invalidation|
|---|---|
|authoritative contract|preserve; require explicit author/review change|
|implementation|route semantic repair through engineering workflow|
|validation evidence|rerun automatically where safe/allowed, otherwise `REFRESH_REQUIRED`|
|generated engineering knowledge|regenerate automatically where safe|
|derived projection/index|recompute automatically|

A stale generated artifact MUST NOT remain indefinitely stale solely because regeneration was  
previously defined as manual/on-demand.

Historical artifacts remain retained with their original provenance.

**Concurrency:** D9 does not alter SCC SP-B. Freshness browser integration occurs only after the  
SP-B substrate has landed.

````

### F. Add to global reuse constraints

```markdown
- **Freshness:** extend `factory.freshness`, `factory.trace` and `factory.evidence.reconcile`;
  do not introduce a second artifact-specific checksum/freshness framework.
- **Dependency authority:** declared trace/provenance edges determine impact. LLM semantic inference
  may suggest missing links but cannot establish authoritative freshness dependencies by itself.
- **Automatic remediation is policy-controlled:** deterministic projection rebuilds and safe generated
  knowledge may refresh automatically; authoritative contracts and semantic implementation changes
  follow their existing engineering workflows.
````

---

# 3. UPDATE `00-execution-roadmap.md`

The existing roadmap says SP-B comes before Engineering Context Inc 6, and that Inc 7 depends on Inc 6. Keep that.

### Replace the Phase 4 lines

Current conceptual portion:

```text
PHASE 4  v2 Inc 6   Human Engineering Context UI ...
         v2 Inc 7   context delta + goal-aware validation status ...
```

Replace with:

```markdown
PHASE 4  v2 Inc 6   Human Engineering Context UI (5 tabs on landed SP-B browser)
                   + diagram rendering (D7) woven into dossier/V-cycle/ADR/goal tabs

         v2 Inc 7   context delta + freshness reconciliation
                   + goal-aware validation state
                   + dependency-driven impact propagation
                   + safe automatic evidence rerun / generated-artifact regeneration
                   + freshness closure
                   + comprehension hooks (D8)
```

### Update the Inc 7 dependency table row

Replace:

```markdown
| Inc 7 (context delta) | Inc 2/3, Inc 6 | + "Catch me up" view + comprehension hooks (D8) |
```

with:

```markdown
| Inc 7 (context delta + freshness) | Inc 1–3, Inc 6 | consumes ontology, evidence and landed SP-B/Inc-6 human surfaces; adds freshness reconciliation without changing SP-B |
```

### Add D9 to the decision table

```markdown
| D9 | freshness = detect + propagate + policy-controlled repair + reconcile + closure; safe generated artifacts do not remain manually stale | §7 + HLR-09 + Inc 7 |
```

### Add this concurrency note

```markdown
## Active SP-B implementation boundary

SCC SP-B is currently under implementation by another coding-agent workflow.

Until SP-B lands:

- do not edit SP-B-owned browser implementation as part of HLR-09 work;
- do not amend SP-B acceptance criteria to absorb Engineering Context freshness;
- HLR-09 implementation may prepare Python/domain primitives only where they do not conflict with
  SP-B work;
- browser-facing freshness controls/status are integrated through Inc 6/7 after SP-B lands.

SP-B remains a substrate dependency, not part of the freshness implementation scope.
```

---

# 4. UPDATE `increment-07-context-delta-validation.md`

This is the **most important modification**.

The current Inc 7 already reuses `factory.freshness` and `factory.evidence.reconcile`, but its added explainer requirement explicitly says:

> mark stale automatically, but regeneration is explicit/on-demand and “never auto-run.”

That is the piece that needs superseding.

I would rename the title to:

```markdown
# Increment 7 — Context Delta + Freshness Reconciliation (Implementation Plan)
```

Then replace the opening `## Goal` with:

```markdown
## Goal

Close the human mental-model gap while making **artifact freshness a maintained engineering property**.

Increment 7 SHALL deliver:

1. deterministic `/catchup <feature>` — what changed since the developer's last checkpoint;
2. goal-aware requirement status;
3. dependency-driven change-impact resolution;
4. transitive invalidation of dependent engineering artifacts;
5. authority-aware refresh policy;
6. automatic restoration of safe derived/generated artifacts;
7. automatic validation rerun where allowed and practical;
8. routing of semantic implementation repairs through the existing DEV workflow;
9. deterministic freshness reconciliation;
10. feature-level **freshness closure** reporting.

This increment implements HLR-09 using the existing trace, fingerprint, evidence and system-query
substrates. It MUST NOT build an independent staleness framework.

### SP-B boundary

SCC SP-B is an active upstream implementation dependency.

This increment MUST NOT modify SP-B-owned implementation before SP-B lands.
Browser/UI work defined here is performed only on the landed SP-B + Inc 6 substrate.
The domain/freshness architecture is independent of SP-B implementation details.
```

Then add the following new sections **after Task 5b and before Optional Index**.

````markdown
## Task 5c: General artifact dependency provenance

### Goal

Generalise freshness from isolated code/evidence checks into explicit artifact dependencies that can
be traversed transitively.

Reuse:

- `factory.trace`;
- `factory.freshness`;
- existing artifact fingerprints;
- evidence reconciliation;
- feature/bundle scope.

Do not create a second graph.

### Required model

An artifact whose authority depends on another artifact must expose sufficient provenance to evaluate
that dependency.

Conceptual interface:

```python
@dataclass(frozen=True)
class ArtifactDependency:
    source_ref: str
    dependent_ref: str
    fingerprint: str | None
    dependency_kind: str

@dataclass(frozen=True)
class ArtifactFreshness:
    artifact_ref: str
    state: FreshnessState
    reasons: tuple[str, ...]
````

Exact model names are implementation choices.

### Dependency types

At minimum, the implementation must support dependencies involving:

- requirement → implementation;
    
- implementation → validation evidence;
    
- requirement → validation evidence;
    
- metric definition → evidence;
    
- validation/scenario/harness → evidence;
    
- requirement/implementation/ADR → generated explainer;
    
- feature/requirement/goal → diagram;
    
- canonical artifact → derived projection.
    

Only declared or deterministically authoritative relations may drive freshness.

### Failing tests

Cover:

1. SR changes → linked downstream artifact stale.
    
2. Implementation changes → SR stays fresh; evidence and implementation-dependent explainer stale.
    
3. Metric definition changes → old evidence stale.
    
4. Validation harness changes → old evidence stale.
    
5. Generator changes → generated artifact stale even if engineering inputs did not change.
    
6. Missing dependency fingerprint → state degrades/unknown; never assumed fresh.
    
7. Unrelated repository change → no false invalidation.
    
8. Dependency propagation does not rely on LLM inference.
    

---

## Task 5d: Transitive impact resolver

### Goal

Compute the affected dependency closure after a repository/canonical-artifact change.

Conceptual interface:

```python
@dataclass(frozen=True)
class Impact:
    changed: tuple[str, ...]
    directly_affected: tuple[str, ...]
    transitively_affected: tuple[str, ...]

def compute_impact(root: Path, changed_refs: Sequence[str]) -> Impact:
    ...
```

### Required behaviour

Given:

```text
SR-017
  ↓
code:navigation/preemption.py
  ↓
evidence:EXP-004
  ↓
diag:DIAG-NAV-009
  ↓
explainer:NAV-PREEMPTION
```

a change to `SR-017` must discover every reachable dependent artifact unless an explicit dependency  
boundary applies.

### Failing tests

- direct dependency;
    
- two-hop dependency;
    
- multi-hop dependency;
    
- fan-out;
    
- fan-in;
    
- cycle protection;
    
- deleted artifact;
    
- renamed artifact with changed identity;
    
- no impact across unrelated feature;
    
- deterministic ordering.
    

---

## Task 5e: Authority-aware refresh policy

### Goal

Separate "this is stale" from "what should the factory do about it."

Conceptual interface:

```python
class RefreshAction(Enum):
    RECOMPUTE = "recompute"
    REGENERATE = "regenerate"
    RERUN_VALIDATION = "rerun-validation"
    ROUTE_TO_DEV = "route-to-dev"
    REQUEST_HUMAN_ACTION = "request-human-action"
    SUPERSEDE = "supersede"

@dataclass(frozen=True)
class RefreshDecision:
    artifact_ref: str
    action: RefreshAction
    reason: str
```

### Default policy

|Artifact authority class|Default action|
|---|---|
|authoritative BR/SR/ADR/goal/metric contract|preserve; request explicit workflow if it itself must change|
|implementation|`ROUTE_TO_DEV` when semantically invalidated by upstream intent|
|validation evidence|`RERUN_VALIDATION` where executable/safe, else explicit refresh required|
|generated explainer/diagram/summary|`REGENERATE`|
|derived query/view/index|`RECOMPUTE`|

The policy must be deterministic.

An LLM may perform a regeneration or implementation task after the action is selected, but it must not  
decide whether the source artifact is stale.

### Resource/safety boundary

Automatic work may be suppressed by configured execution policy, cost budget, unavailable hardware,  
unsafe external effects or missing environment.

In such cases the state must remain explicit:

```text
REFRESH_REQUIRED
or
BLOCKED
```

Never silently `FRESH`.

---

## Task 5f: Automatic generated-artifact regeneration

### Goal

Safe generated engineering knowledge SHALL be refreshed automatically when its dependencies become  
stale and the generator is available.

Initial required types:

- traced visual explainers;
    
- canonical diagrams where a deterministic/registered authoring route exists;
    
- derived summaries/views.
    

### Important supersession

This task **supersedes** the earlier statement in this plan that explainer regeneration is always  
on-demand and "never auto-run."

New rule:

> Staleness detection is automatic. Safe regeneration is also automatic when the refresh policy  
> selects `REGENERATE` and the required generator is available.

Manual regeneration remains a fallback, not the default architecture.

### Explainer freshness

Explainer freshness must account for the dependencies it explains, including where applicable:

- linked SR content;
    
- linked implementation;
    
- linked ADR/design state;
    
- diagram asset;
    
- generator version/fingerprint.
    

It is insufficient for a code-dependent explainer to fingerprint only the SR text.

### Failing tests

1. linked SR changes → explainer stale → regeneration requested/executed;
    
2. linked code changes → explainer stale even when SR unchanged;
    
3. unrelated code change → explainer remains fresh;
    
4. regeneration success → new dependency fingerprints → fresh;
    
5. regeneration failure → stale/blocked remains visible;
    
6. generator fingerprint changes → explainer refreshed;
    
7. historical explainer provenance remains attributable to old state.
    

---

## Task 5g: Automatic evidence refresh

### Goal

Where validation is executable, bounded and safe, stale evidence should be regenerated automatically.

Examples:

- pytest-backed acceptance;
    
- simulation harness;
    
- deterministic metric extraction;
    
- configured bounded experiment.
    

### Required behaviour

```text
implementation changes
→ affected evidence stale
→ refresh policy = RERUN_VALIDATION
→ harness executes
→ evidence persisted with new provenance
→ goals/status re-evaluated
```

If validation requires unavailable hardware, expensive cloud resources, human action or unsafe  
physical execution:

```text
evidence = REFRESH_REQUIRED / BLOCKED
```

The requirement must NOT remain validated from old evidence.

### Acceptance

A stale evidence record remains in history but is excluded from current validation authority.

---

## Task 5h: Semantic implementation invalidation

### Goal

An upstream intent change may make implementation semantically stale even when the code itself did not  
change.

Example:

```text
SR-017 semantics changed
→ implementation previously satisfying old SR cannot be assumed current
```

The factory SHALL NOT automatically rewrite such implementation as though it were a generated document.

Instead:

```text
upstream semantic change
→ implementation impact detected
→ ROUTE_TO_DEV
→ controlled implementation workflow
→ validation
→ reconciliation
```

The resulting work item must retain the upstream cause.

This is distinct from evidence staleness and must remain visible until repaired or explicitly accepted.

---

## Task 5i: Freshness reconciliation

### Goal

After refresh actions execute, recompute the dependency graph and current authority.

Conceptual interface:

```python
@dataclass(frozen=True)
class FreshnessReconciliation:
    refreshed: tuple[str, ...]
    still_stale: tuple[str, ...]
    blocked: tuple[str, ...]
    superseded: tuple[str, ...]
    closure_reached: bool
```

The reconciler must not trust the fact that a refresh command ran.

It verifies current fingerprints/provenance after the action completes.

### Required invariant

```text
refresh action executed
≠
artifact is fresh
```

Freshness is established only after reconciliation against current dependencies.

---

## Task 5j: Feature freshness closure

### Goal

Expose whether the complete impacted feature slice is coherent again.

```python
def freshness_closure(root: Path, feature: str) -> FreshnessClosure:
    ...
```

A feature reaches closure if every impacted reachable artifact is:

- fresh;
    
- explicitly superseded; or
    
- intentionally unresolved with a visible reason/action.
    

The system must distinguish:

```text
closure_reached = True
```

from:

```text
closure_reached = False
remaining:
  code:...      ROUTE_TO_DEV
  evidence:...  BLOCKED: hardware unavailable
```

"Explicitly unresolved" does not mean healthy; it means there is no hidden stale state.

---

## Task 5k: `/catchup` freshness integration

Extend `ContextDelta` to expose engineering invalidation and repair, not only repository changes.

Conceptually add:

```python
invalidated: list[str]
auto_refreshed: list[str]
refresh_required: list[str]
blocked_refreshes: list[str]
freshness_closure_reached: bool
```

Example human output:

```text
Since your last review:

Requirements
  SR-017 changed

Implementation
  navigation/preemption.py updated

Automatically invalidated
  2 validation runs
  1 diagram
  2 visual explainers

Automatically refreshed
  validation runs
  diagram
  visual explainers

Remaining stale
  none

Metric
  reacquisition_rate 0.93 -> 0.96

Freshness closure
  REACHED
```

The state fields are deterministic.

Narrative explanation may be generated separately but may not contradict them.

---

## Task 5l: Change-impact integration with V-cycle health

Extend `vcycle_health` findings to include:

- stale implementation relative to changed upstream intent;
    
- stale validation;
    
- stale generated explainer;
    
- stale diagram;
    
- missing provenance;
    
- blocked refresh;
    
- failed regeneration;
    
- refresh loop detected;
    
- unresolved freshness closure.
    

The SCC/browser surface may render these findings only after SP-B + Inc 6 have landed.

The Python/domain representation does not depend on browser implementation details.

---

## Task 5m: Refresh loop protection

Automatic regeneration creates a new class of failure: refresh loops.

The system must detect and stop pathological chains such as:

```text
generator writes artifact
→ write appears as input change
→ generator runs again
→ ...
```

Required protections:

- dependency direction is explicit;
    
- generated output is not implicitly considered its own source;
    
- generator writes are attributable to refresh operations;
    
- repeated identical refresh attempts are bounded;
    
- reconciliation compares meaningful dependency fingerprints;
    
- blocked/failed refresh becomes visible rather than retrying forever.
    

Add deterministic tests for self-cycle and two-generator cycles.

---

## Task 5n: Historical preservation

Refreshing current engineering knowledge must not erase evidence of prior states.

At minimum:

- old validation retains original commit/configuration provenance;
    
- superseded generated artifacts remain attributable where history storage exists;
    
- `/catchup` may distinguish invalidated historical evidence from current evidence;
    
- failure records and rejected hypotheses remain immutable historical knowledge.
    

Inc 8 consumes this provenance for durable engineering memory.

---

## Task 5o: Thin-slice freshness acceptance — Physical Agentic AI Drone

Use one navigation/pre-emption feature as the reference test.

### Test A — requirement semantic change

Initial:

```text
requirement      FRESH
implementation   FRESH
validation       FRESH
diagram          FRESH
explainer        FRESH
feature closure  REACHED
```

Change requirement semantics.

Assert:

```text
requirement      FRESH
implementation   REFRESH_REQUIRED / ROUTE_TO_DEV
validation       STALE
diagram          STALE then regenerated
explainer        STALE then regenerated
feature closure  NOT REACHED
```

Complete DEV repair.

Assert:

```text
implementation   FRESH
validation       automatically rerun where configured
goal             re-evaluated
diagram          reconciled fresh
explainer        reconciled fresh
feature closure  REACHED
```

Historical pre-change evidence must still exist but must not validate current state.

### Test B — implementation-only change

Change the implementation without changing the SR.

Assert:

```text
requirement      remains FRESH
implementation   current
old validation   STALE
dependent explainer / diagram stale
validation reruns
generated knowledge refreshes
requirement/goal status re-evaluates
closure eventually REACHED
```

This test is mandatory: it proves invalidation is dependency-driven rather than special-cased around  
SR changes.

````

### Then replace the old explainer section

In current section:

```markdown
### B. Explainer as a traced, SR-linked artifact (additive)
````

replace the paragraph:

```markdown
- Explainer staleness couples **SR content AND the code behind it**: reuse ...
- Regeneration stays **on-demand** ...
```

with:

```markdown
- Explainer staleness couples the **declared engineering dependencies that make the explanation
  authoritative**, including SR content and the relevant implementation where applicable. Reuse
  `fingerprint_file` / `fingerprint_value` / `fingerprint_git_tree`; do not create a parallel checksum.
- Explainer invalidation participates in the general HLR-09 dependency graph.
- When refresh policy selects `REGENERATE`, regeneration is automatic where the registered generator
  is available and execution is safe. Manual regeneration is a fallback.
- Successful generation does not itself imply freshness; the regenerated artifact must be reconciled
  against current dependencies.
- Historical generated knowledge is retained where history/provenance storage supports it.
```

### Replace Increment 7 acceptance with

```markdown
## Acceptance for Increment 7

Increment 7 is complete only when all of the following hold:

- `/catchup FEAT-NAV-017` returns a deterministic, correct "since your last review" delta.
- Requirement state correctly reflects goal/evidence freshness.
- `vcycle_health` surfaces missing and inconsistent V-cycle relationships.
- Artifact dependencies can be traversed transitively for freshness impact.
- A requirement change invalidates all declared downstream dependent artifacts.
- An implementation-only change invalidates evidence/generated knowledge without invalidating the
  authoritative SR.
- Stale evidence cannot validate current implementation.
- Safe generated artifacts are automatically regenerated.
- Safe executable validation is automatically rerun when configured.
- Semantic implementation repair is routed through DEV rather than silently rewritten.
- Refresh success is verified by reconciliation, not assumed.
- Feature freshness closure is computed and exposed.
- Missing provenance is degraded/unknown/stale, never silently fresh.
- Refresh loops are bounded/detected.
- Historical evidence remains preserved.
- `/catchup` reports changed, invalidated, auto-refreshed, blocked and remaining stale artifacts.
- Optional comprehension intervention remains distinct from deterministic freshness state.
- SP-B implementation has not been modified by this increment before it lands.
- v1 suite remains green and all new behaviour is additive to existing public contracts unless an
  explicit compatibility decision says otherwise.
```

---

# 5. SMALL UPDATE TO INCREMENT 8

I would **not move freshness itself into Inc 8**. Inc 7 should own maintaining current truth; Inc 8 should own the durable historical memory generated by that process.

In your Increment 8 durable-memory plan, add:

````markdown
## Freshness/history integration

Increment 8 consumes the provenance and reconciliation model established by HLR-09 / Inc 7.

Durable memory must distinguish:

```text
current engineering truth
from
historical engineering truth
````

Examples:

- a validation run may be historically valid for commit A while stale for HEAD;
    
- an explainer may accurately describe the implementation at commit B while superseded by its current  
    regenerated version;
    
- an ADR may be superseded but remain essential rationale history;
    
- a rejected hypothesis remains valuable even though it is not current belief;
    
- a regression record remains immutable after the system recovers.
    

Memory SHOULD record meaningful freshness transitions where they carry engineering value:

```text
artifact X invalidated because dependency Y changed
artifact X regenerated as X'
validation E ceased proving SR-017 at commit C
goal G regressed and later recovered
```

The durable-memory layer SHALL NOT make stale artifacts current merely because they are retrievable.

Historical retrieval must surface temporal/provenance context.

````

---

## One extra change I strongly recommend

There is a subtle architectural issue in the current plan worth making explicit.

Your current D7 says committed HTML diagrams are canonical and “regenerate by re-running the authoring step.” 

I would slightly change the wording from **canonical artifact** to **canonical generated artifact**.

The actual engineering truth should remain:

```text
requirement + design + code + metrics + evidence
````

while the diagram is:

```text
a committed, reviewable projection of that truth
```

Otherwise you get an authority paradox:

```text
SR says A
code says A
trace graph says A
old canonical HTML says B
```

If HTML is genuinely canonical, the system cannot automatically replace it without conceptually rewriting a source of truth.

So in D7 I suggest replacing:

```markdown
canonical, committed, self-contained HTML artifacts
```

with:

```markdown
committed, reviewable, provenance-bearing generated engineering artifacts
```

and add:

```markdown
The diagram is authoritative as the current approved/generated visual representation, but it is not
an independent semantic source of truth. Its freshness derives from the canonical engineering
artifacts declared in its provenance.
```

That small distinction makes HLR-09 much cleaner.

The resulting architecture is then:

```text
                    AUTHORITATIVE INTENT
                  BR / SR / ADR / goals
                           │
                           ▼
                    IMPLEMENTATION
                           │
                           ▼
                 VALIDATION CONTRACT
                           │
                           ▼
                  EXECUTABLE EVIDENCE
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
             CURRENT STATE     DURABLE HISTORY
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
      SCC      diagrams   explainers
      views     charts     summaries
        \________ generated ________/
                    projections
```

That is the model I would have your coding agent implement. It preserves the original cockpit vision while making **repository evolution itself a first-class engineering event** rather than leaving the human to discover that half the project's documentation no longer describes the current system.