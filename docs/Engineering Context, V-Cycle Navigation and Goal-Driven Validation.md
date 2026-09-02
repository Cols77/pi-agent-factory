# Engineering Context, V-Cycle Navigation and Goal-Driven Validation
## MVP System Specification for the Pi Coding-Agent Factory

**Status:** Draft  
**Target project:** Physical Agentic AI Drone / Pi Coding-Agent Factory  
**Primary objective:** Allow a developer to keep pace with autonomous coding agents by making project intent, V-cycle traceability, implementation state, verification evidence, and measurable goals immediately recoverable and navigable.

---

# 1. Problem Statement

Agentic coding can modify a software system faster than a human developer can continuously maintain an accurate mental model of:

- why a feature exists;
- which requirements define it;
- which architectural decisions constrain it;
- where it is implemented;
- how it is validated;
- what simulations demonstrate its behaviour;
- which metrics define success;
- whether the intended goal has actually been reached;
- what changed since the developer last inspected the feature.

The system shall therefore optimize for **rapid context reconstruction**, rather than traditional project-management workflows.

A developer working inside the Pi coding agent should be able to ask:

- “Why does this code behave this way?”
- “Which requirement does this implement?”
- “How was this feature validated?”
- “Show me the latest failing simulation.”
- “What changed since I last looked at this?”
- “Did we reach the reacquisition-rate target?”
- “Show me where this sits in the V-cycle.”

The coding agent shall answer these questions using structured project artifacts and, when useful, automatically present the relevant human-facing view.

---

# 2. Core Design Principle

The system shall model development around a **feature-centric vertical slice through the V-cycle**.

A feature may connect:

```text
User / System Need
        ↓
System Requirement
        ↓
Subsystem Requirement
        ↓
Architecture / ADR
        ↓
Detailed Design
        ↓
Implementation
        ↓
Unit Verification
        ↓
Integration Verification
        ↓
Simulation Verification
        ↓
System Validation
        ↓
Evidence / Metrics
```

The central engineering question is not:

> “Where is the document?”

It is:

> “What is the complete current engineering state of this feature?”

---

# 3. System Objectives

The system SHALL:

1. Maintain typed traceability across the V-cycle.
2. Allow a developer to reconstruct feature context within approximately two minutes.
3. Allow coding agents to query engineering context deterministically.
4. Allow human developers to visually navigate the same engineering graph.
5. Associate requirements with measurable validation goals.
6. Automatically detect when such goals are reached or regressed.
7. Associate simulation runs with requirements, features, commits and metrics.
8. Present relevant artifacts automatically when developer attention is useful.
9. Avoid requiring manual synchronization between requirements, tasks, code and verification evidence.
10. Treat UI representations as derived views rather than canonical project state.

---

# 4. Architectural Overview

```text
                    ┌─────────────────────────┐
                    │      DEVELOPER          │
                    │                         │
                    │   Pi Coding Agent       │
                    │      = cockpit          │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Engineering Context MCP │
                    │                         │
                    │ - artifact graph        │
                    │ - V-cycle traceability  │
                    │ - goal registry         │
                    │ - evidence registry     │
                    │ - change impact         │
                    │ - context reconstruction│
                    └────────────┬────────────┘
                                 │
                       presentation intent
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  Presentation Router    │
                    └──────┬────────┬─────────┘
                           │        │
              ┌────────────┘        └────────────┐
              ▼                                  ▼
        ┌───────────┐                       ┌──────────┐
        │ Obsidian  │                       │Simulation│
        │           │                       │ Viewer   │
        │ V-cycle   │                       │          │
        │ concepts  │                       │ video    │
        │ features  │                       │ telemetry│
        │ ADRs      │                       │ events   │
        └─────┬─────┘                       └────┬─────┘
              │                                  │
              └──────────────┬───────────────────┘
                             ▼
                      Canonical Artifacts
                             │
                    Git repository + CI
```

---

# 5. Canonical Data Model

The canonical engineering state SHALL live in Git-tracked artifacts wherever practical.

A derived local index MAY use SQLite.

The database SHALL be rebuildable from canonical project artifacts.

Deleting the local index SHALL NOT cause loss of engineering information.

## 5.1 Artifact Types

The MVP shall support at least:

```text
Feature
Requirement
ArchitectureComponent
ArchitectureDecision
Design
Task
CodeComponent
TestSpecification
SimulationExperiment
SimulationRun
Metric
Goal
Evidence
ResearchFinding
```

## 5.2 Required Relationships

Examples:

```text
Feature
  contains / relates_to
Requirement

Requirement
  parent_of / child_of
Requirement

Requirement
  satisfied_by
Design

Design
  implemented_by
CodeComponent

Requirement
  verified_by
TestSpecification

TestSpecification
  executed_as
SimulationRun

SimulationRun
  produces
Evidence

Goal
  evaluates
Metric

Goal
  demonstrates
Requirement

ArchitectureDecision
  constrains
Design

Task
  implements
Feature

Commit / PR
  modifies
CodeComponent
```

Relationships SHALL be typed.

Free-form backlinks MAY complement these relationships but SHALL NOT replace them.

---

# 6. Artifact IDs

Every significant engineering artifact SHALL have a stable ID.

Examples:

```text
FEAT-NAV-017
SYS-REQ-004
NAV-REQ-021
ADR-012
DES-NAV-008
TEST-NAV-032
SIM-047
RUN-20260811-1421
MET-NAV-004
GOAL-NAV-003
```

IDs SHALL remain stable when files are renamed or reorganized.

---

# 7. Feature Dossier

The system SHALL generate a human-readable **Feature Dossier** for each feature.

Example:

```text
FEAT-NAV-017
Target Reacquisition

STATUS
⚠ Implemented — simulation target not yet achieved

PURPOSE
Maintain a plausible shark hypothesis across temporary
visual loss and attempt reacquisition before resuming patrol.

REQUIREMENTS
SYS-SAFE-004
NAV-REQ-021
PER-REQ-013

DESIGN
ADR-012
DES-NAV-008

IMPLEMENTATION
src/navigation/reacquisition.py
src/memory/target_memory.py

VALIDATION

Unit
✓ TEST-MEM-021

Integration
✓ TEST-NAV-032

Simulation
⚠ SIM-047
  Current reacquisition rate: 87%
  Goal: >= 90%

System
○ Not yet executed

ACTIVE GOALS
GOAL-NAV-003
Reacquisition rate >= 90%
Current: 87%

LATEST FAILURE
RUN-20260811-1421

OPEN QUESTIONS
- Multi-target identity ambiguity
- Confidence-decay constant remains empirical

RECENT CHANGES
PR #207
PR #214
```

The feature dossier SHALL be generated from canonical artifacts and indexed state rather than manually duplicated.

---

# 8. Obsidian V-Cycle Extension

## 8.1 Decision

An Obsidian extension SHOULD be implemented.

Its purpose SHALL NOT be to create another requirements-management backend.

Its purpose SHALL be:

> **visual navigation of the Engineering Context graph from a human perspective.**

The Engineering Context layer SHALL remain authoritative.

---

# 9. Obsidian Plugin Responsibilities

The plugin SHALL provide four primary views.

## 9.1 V-Cycle View

The plugin shall display the selected feature or requirement across the V-cycle.

Conceptually:

```text
          DEFINITION                      VERIFICATION

    System Requirement ◄──────────────► System Validation
            │                                  ▲
            ▼                                  │
   Subsystem Requirement ◄────────────► Simulation Tests
            │                                  ▲
            ▼                                  │
    Architecture/Design ◄─────────────► Integration Tests
            │                                  ▲
            ▼                                  │
      Detailed Design ◄───────────────► Unit Tests
            │                                  ▲
            └──────────── CODE ────────────────┘
```

Each displayed node SHALL:

- show its ID;
- show a short title;
- show current status;
- be clickable;
- show missing links distinctly;
- show failed verification distinctly;
- show stale verification distinctly.

Selecting a node SHALL navigate to the corresponding artifact.

---

## 9.2 Feature View

The Feature View SHALL visualize the Feature Dossier.

It should provide rapid access to:

- intent;
- requirements;
- design;
- code;
- current tasks;
- tests;
- simulations;
- goals;
- recent changes;
- unresolved questions.

---

## 9.3 Goal View

The Goal View SHALL show measurable engineering objectives.

Example:

```text
GOAL-NAV-003

Requirement:
NAV-REQ-021

Metric:
target_reacquisition_rate

Target:
>= 0.90

Current:
0.87

State:
IN_PROGRESS

Evidence:
SIM-047
RUN-20260811-1421

History:

commit A     0.71
commit B     0.82
commit C     0.87
```

---

## 9.4 Context Delta View

The plugin SHOULD eventually support:

```text
"What changed since I last reviewed this feature?"
```

It shall compare the current engineering state with a developer checkpoint.

Example output:

```text
Since your last review:

2 implementation PRs merged
1 requirement modified
1 architecture decision added
2 simulation scenarios added

Metric changes:

reacquisition_rate
82% → 91%

false_reacquisition_rate
2% → 4%   ⚠ regression

New unresolved item:
multi-target identity ambiguity
```

This is post-MVP unless implementation cost is low.

---

# 10. Obsidian Plugin Data Access

The Obsidian plugin SHOULD NOT independently reconstruct the entire project graph.

Preferred architecture:

```text
Obsidian Plugin
      │
      ▼
Engineering Context API / local service
      │
      ▼
Derived Graph
      │
      ▼
Git-tracked engineering artifacts
```

This prevents the coding agent and Obsidian from implementing separate interpretations of the project.

---

# 11. Pi Factory `/goal` Command

A first-class `/goal` command SHALL be added to the Pi Factory.

Purpose:

> Bind a measurable target to a requirement or feature and allow the factory to automatically determine when the intended engineering outcome has been reached.

---

# 12. `/goal` UX

The developer should be able to write:

```text
/goal NAV-REQ-021 reacquisition_rate >= 0.90
```

or:

```text
/goal FEAT-NAV-017
"Reacquire the shark in at least 90% of temporary-loss scenarios"
metric=reacquisition_rate
target=">=0.90"
experiment=SIM-047
```

The agent MAY infer missing configuration when unambiguous.

It SHALL persist the resulting goal as an engineering artifact.

Example:

```yaml
id: GOAL-NAV-003
type: goal

feature:
  - FEAT-NAV-017

requirements:
  - NAV-REQ-021

metric:
  name: target_reacquisition_rate
  source: SIM-047

target:
  operator: ">="
  value: 0.90

state: active

created_from:
  task: TASK-142
```

---

# 13. Goal Lifecycle

Goals SHALL implement the following state model:

```text
DECLARED
    │
    ▼
ACTIVE
    │
    ├──────────────► BLOCKED
    │
    ▼
EVALUATING
    │
    ├──────────────► NOT_REACHED
    │
    ▼
REACHED
    │
    └──────────────► REGRESSED
```

## State Definitions

### DECLARED
Goal exists but required metric/evidence pipeline is not fully configured.

### ACTIVE
Goal is properly configured and can be evaluated.

### EVALUATING
Relevant experiment or test is executing.

### NOT_REACHED
Valid evidence was produced but target was not met.

### REACHED
Target condition was satisfied by valid evidence.

### REGRESSED
Goal had previously been reached but newer valid evidence no longer meets the target.

### BLOCKED
Goal cannot currently be evaluated.

Examples:

- missing simulator;
- missing dataset;
- invalid metric;
- unavailable test fixture.

---

# 14. Goal Evaluation

A goal SHALL NOT be marked `REACHED` solely because an LLM claims the implementation is correct.

It SHALL require structured evidence.

Example:

```text
GOAL-NAV-003
    │
    ▼
SIM-047
    │
    ▼
RUN-20260811-1702
    │
    ▼
metrics.json
    │
    ▼
target_reacquisition_rate = 0.93
    │
    ▼
0.93 >= 0.90
    │
    ▼
GOAL REACHED
```

Evaluation SHOULD be deterministic whenever possible.

LLM-as-Judge MAY be used for explicitly semantic metrics but SHALL produce an inspectable evaluation artifact.

---

# 15. Goal Evidence

When a goal becomes `REACHED`, the system SHALL record:

```text
Goal
Metric
Measured value
Threshold
Experiment
Run
Commit
Timestamp
Evidence location
```

Example:

```yaml
goal: GOAL-NAV-003

status: reached

result:
  value: 0.93
  target: ">=0.90"

evidence:
  experiment: SIM-047
  run: RUN-20260811-1702
  commit: f92b004
  metrics: artifacts/RUN-20260811-1702/metrics.json
  recording: artifacts/RUN-20260811-1702/run.mcap
```

---

# 16. Automatic Goal Notification

When a goal transitions to `REACHED`, the Pi Factory SHALL notify the developer.

Example:

```text
✓ GOAL REACHED

GOAL-NAV-003
Target reacquisition rate >= 90%

Current result:
93%

Validated by:
SIM-047
RUN-20260811-1702
commit f92b004

Previous best:
87%

Opening validation evidence...
```

Depending on policy, the system MAY automatically present the relevant simulation run.

---

# 17. Goal Regression Detection

Goals SHALL continue to be evaluated after being reached when affected code changes.

Example:

```text
GOAL-NAV-003

Previously:
93% ✓

Current:
84% ✗

State:
REGRESSED

Likely affected by:
PR #231

Opening regression simulation...
```

A reached goal is therefore not synonymous with permanent completion.

---

# 18. Goal-to-Requirement Relationship

Goals SHALL complement requirements rather than replace them.

Example:

Requirement:

```text
NAV-REQ-021

The system shall attempt to reacquire a recently lost
high-confidence target before resuming the patrol mission.
```

Goal:

```text
GOAL-NAV-003

At least 90% of targets hidden for <= 5 seconds shall be
successfully reacquired within 10 seconds.
```

This distinction is important:

```text
Requirement = intended behaviour

Goal = measurable evidence threshold
```

A requirement MAY have multiple goals.

---

# 19. Metric Model

Metrics SHALL be reusable artifacts where useful.

Example:

```yaml
id: MET-NAV-004
type: metric

name: target_reacquisition_rate

definition:
  numerator: successful_reacquisitions
  denominator: valid_reacquisition_scenarios

unit: ratio

producer:
  experiment: SIM-047
```

Potential drone-system metrics include:

```text
target detection precision
target detection recall
false shark alarm rate

reacquisition rate
time to reacquisition

mission coverage
energy per mission

LLM decision latency
navigation decision correctness

collision rate
minimum obstacle clearance

tracking identity switches
false navigation preemptions
```

---

# 20. Simulation Run Format

Every meaningful simulation execution SHOULD produce a run bundle.

Example:

```text
RUN-20260811-1702/
│
├── manifest.json
├── metrics.json
├── events.json
├── run.mcap
├── preview.mp4
├── agent_trace.jsonl
└── report.md
```

The manifest SHALL identify:

```json
{
  "run": "RUN-20260811-1702",
  "experiment": "SIM-047",
  "feature": "FEAT-NAV-017",
  "requirements": [
    "NAV-REQ-021"
  ],
  "goals": [
    "GOAL-NAV-003"
  ],
  "commit": "f92b004",
  "result": "passed"
}
```

---

# 21. Simulation Presentation

The system SHOULD support two forms of simulation inspection.

## Human inspection

A simulation viewer should expose:

```text
camera / video
detections
tracks
drone pose
trajectory
navigation state
memory state
agent decisions
events
metrics
```

## Agent inspection

The Engineering Context layer SHOULD expose structured operations such as:

```text
get_simulation_run(run_id)

get_simulation_events(run_id)

inspect_simulation_event(
    run_id,
    event
)

get_metric_history(metric_id)

get_goal_evidence(goal_id)
```

The agent SHOULD inspect structured telemetry before attempting expensive visual reasoning over arbitrary video.

---

# 22. Presentation Router

A small Presentation Router SHALL mediate requests to human-facing tools.

The agent SHALL issue semantic presentation intents rather than raw operating-system commands.

Examples:

```text
present(
    artifact="NAV-REQ-021"
)
```

→ Obsidian V-cycle view.

```text
present(
    artifact="FEAT-NAV-017"
)
```

→ Obsidian Feature Dossier.

```text
present(
    artifact="src/navigation/reacquisition.py",
    line=184
)
```

→ IDE.

```text
present(
    artifact="RUN-20260811-1702",
    focus="target_reacquired"
)
```

→ Simulation viewer at relevant event.

---

# 23. Presentation Policy

Three presentation levels SHALL exist.

## INSPECT

Agent retrieves information internally.

No application focus change.

Used by default.

## PRESENT

Agent opens one relevant human interface.

Used when:

- developer asks “show me”;
- developer asks “where is…”;
- visual evidence materially improves understanding;
- an important validation failure occurs.

## REVIEW

Agent establishes a review context spanning multiple artifacts.

Example:

```text
Feature dossier
+
latest simulation
+
affected implementation
```

Used only for explicit feature/task review checkpoints.

---

# 24. Avoiding UI Noise

The system SHALL NOT automatically open applications for every test or artifact lookup.

Examples:

Unit test passes:

```text
✓ 42/42 tests passed
```

No external UI.

Simulation validation fails:

```text
⚠ Goal not reached.
Reacquisition rate 87%, expected >=90%.

Opening most informative failing scenario.
```

Simulation viewer opens.

User asks:

```text
Why did we choose exponential confidence decay?
```

Agent answers briefly.

If additional exploration is beneficial:

```text
Opening ADR-012 in the feature context.
```

Obsidian opens.

---

# 25. Engineering Context MCP

The MVP Engineering Context server SHALL expose operations similar to:

```text
get_artifact(id)

get_feature_context(feature_id)

get_vcycle(feature_or_requirement_id)

trace_requirement(requirement_id)

get_requirement_implementation(requirement_id)

get_verification_status(requirement_id)

get_recent_feature_changes(feature_id)

get_change_impact(commit_or_diff)

get_latest_simulation(feature_id)

get_latest_failure(feature_id)

get_goal(goal_id)

get_goals(feature_or_requirement_id)

evaluate_goal(goal_id)

get_goal_history(goal_id)

get_goal_evidence(goal_id)

present(artifact, focus?)
```

---

# 26. Pi Factory Task Workflow

A feature task SHOULD eventually run approximately as follows:

```text
/task FEAT-NAV-017
```

Agent:

```text
1. reconstruct feature context

2. inspect requirements

3. inspect active goals

4. determine affected design/code

5. implement task

6. run unit verification

7. run integration verification

8. identify required simulation experiments

9. run simulation

10. collect evidence

11. evaluate goals

12. update engineering graph

13. report outcome

14. present simulation if:
    - validation failed;
    - goal was newly reached;
    - developer requested review.
```

---

# 27. Example End-to-End Workflow

Developer:

```text
/goal NAV-REQ-021 reacquisition_rate >= 0.90
```

Factory:

```text
Created GOAL-NAV-003.

Metric:
target_reacquisition_rate

Experiment:
SIM-047

Current baseline:
0.71
```

Developer:

```text
Implement improved target reacquisition.
```

Agent:

```text
...implementation...

Unit tests:
42/42 ✓

Integration:
8/8 ✓

Running SIM-047...
```

Result:

```text
SIM-047
10 scenarios

8 reacquired
2 failed

Metric:
0.80

GOAL-NAV-003
NOT REACHED

Target:
>=0.90

Current:
0.80

Opening representative failure.
```

Simulation viewer opens.

After iteration:

```text
SIM-047

19/20 successful

Metric:
0.95
```

Factory:

```text
✓ GOAL REACHED

GOAL-NAV-003
Target reacquisition rate >= 90%

Measured:
95%

Evidence:
RUN-20260811-1824

Commit:
e402af1

Opening successful validation run.
```

Obsidian now shows:

```text
FEAT-NAV-017

Implementation ✓
Unit verification ✓
Integration verification ✓
Simulation validation ✓

GOAL-NAV-003 ✓ 95%

Requirement NAV-REQ-021
VALIDATED
```

---

# 28. Requirement Validation Status

Requirement status SHOULD distinguish implementation and evidence.

Suggested states:

```text
DEFINED
DESIGNED
IMPLEMENTED
VERIFICATION_PENDING
PARTIALLY_VERIFIED
VALIDATED
REGRESSED
```

A requirement SHALL NOT become `VALIDATED` merely because implementation exists.

Its required validation goals and verification criteria SHALL be satisfied.

---

# 29. Derived V-Cycle Health

The system SHOULD detect inconsistencies such as:

```text
requirement without test

requirement without implementation

implementation without traceable requirement

goal without metric source

metric without experiment

simulation without commit

changed implementation with stale evidence

validated requirement whose goal regressed

feature with failing verification

requirement changed after latest validation
```

These SHALL be exposed through both the agent and Obsidian.

---

# 30. Stale Evidence

Verification evidence SHALL be associated with a code revision.

If code affecting a requirement changes after validation, its evidence MAY become stale.

Example:

```text
NAV-REQ-021

Implementation:
commit C

Latest validation:
commit A

Affected code changed:
A → C

Status:
VERIFICATION_STALE
```

The impact-analysis engine SHALL decide whether a new validation run is required.

---

# 31. Human Mental-State Checkpoints

Post-MVP, the system SHOULD track the last revision at which the developer reviewed a feature.

Example:

```yaml
developer_checkpoint:
  feature: FEAT-NAV-017
  commit: a48c21f
```

Then:

```text
/catchup FEAT-NAV-017
```

can produce:

```text
Since your last review:

2 PRs merged
1 requirement modified
1 goal reached
1 new simulation scenario

Behaviour change:
Search duration now depends on target confidence.

Validation:
87% → 95%

New concern:
False reacquisition increased 2% → 4%.
```

This directly addresses human mental-model drift caused by agentic coding velocity.

---

# 32. Repository Structure

Suggested layout:

```text
engineering/
│
├── features/
│   └── FEAT-NAV-017.md
│
├── requirements/
│   ├── system/
│   └── subsystem/
│
├── architecture/
│
├── decisions/
│
├── designs/
│
├── metrics/
│
├── goals/
│
├── verification/
│   ├── unit/
│   ├── integration/
│   ├── simulation/
│   └── system/
│
└── research/

src/

tests/

simulation/

artifacts/       # optional local/generated data

.pi/
├── engineering.db
└── config.yaml
```

Large simulation evidence SHOULD NOT necessarily be committed directly to Git.

The Git-tracked run manifest SHALL identify the external/local evidence location.

---

# 33. Internal Implementation

Suggested module structure:

```text
engineering_context/
│
├── schema/
│   ├── artifact.py
│   ├── feature.py
│   ├── requirement.py
│   ├── metric.py
│   ├── goal.py
│   ├── verification.py
│   └── evidence.py
│
├── index/
│   ├── markdown.py
│   ├── source.py
│   ├── git.py
│   └── github.py
│
├── graph/
│   ├── graph.py
│   ├── traversal.py
│   └── impact.py
│
├── goals/
│   ├── evaluator.py
│   ├── registry.py
│   └── lifecycle.py
│
├── simulation/
│   ├── registry.py
│   └── evidence.py
│
├── presentation/
│   ├── router.py
│   ├── obsidian.py
│   ├── ide.py
│   └── simulation.py
│
├── commands/
│   ├── goal.py
│   ├── catchup.py
│   └── review.py
│
└── mcp/
    └── server.py
```

SQLite is sufficient for MVP graph indexing.

A dedicated graph database SHALL NOT be required initially.

---

# 34. MVP Scope

The first usable version SHALL contain:

### Engineering graph

- typed artifacts;
- typed relationships;
- Markdown parser;
- SQLite derived index;
- feature-context query;
- V-cycle traversal.

### `/goal`

- create goal;
- bind requirement;
- bind metric;
- bind experiment;
- evaluate deterministic metric;
- persist evidence;
- state transitions;
- goal-reached notification;
- regression detection.

### Simulation integration

- experiment/run registry;
- metrics ingestion;
- evidence manifests;
- open relevant simulation recording.

### Presentation Router

- Obsidian artifact presentation;
- IDE code presentation;
- simulation presentation.

### Obsidian plugin

- Feature Dossier;
- V-cycle visualization;
- Goal status;
- navigation across linked artifacts.

---

# 35. Explicit Non-Goals for MVP

Do NOT initially build:

- a complete custom project-management frontend;
- a custom Markdown editor;
- a Kanban system;
- a custom graph database;
- an elaborate cloud backend;
- a replacement for GitHub;
- a replacement for the IDE;
- a replacement for the simulation visualization tool;
- generalized multi-user collaboration;
- automatic semantic inference of every possible artifact relationship;
- embeddings as the primary traceability mechanism.

The system should remain small enough that its value can be validated quickly.

---

# 36. Acceptance Criteria

## AC-01 Feature Reconstruction

Given:

```text
FEAT-NAV-017
```

the system SHALL return, in one operation:

- intent;
- related requirements;
- architecture/design;
- implementation files;
- verification status;
- active goals;
- latest simulation evidence;
- recent changes.

---

## AC-02 V-Cycle Navigation

From a requirement in Obsidian, the user SHALL be able to navigate interactively to:

- parent requirement;
- child requirements;
- design;
- implementation;
- tests;
- simulation evidence.

---

## AC-03 Goal Creation

Executing:

```text
/goal NAV-REQ-021 reacquisition_rate >= 0.90
```

SHALL create a persisted goal artifact associated with `NAV-REQ-021`.

---

## AC-04 Goal Evaluation

Given simulation evidence containing:

```text
reacquisition_rate = 0.93
```

and target:

```text
>= 0.90
```

the goal SHALL transition automatically to:

```text
REACHED
```

---

## AC-05 Goal Evidence

A reached goal SHALL retain:

- measured value;
- threshold;
- run ID;
- commit;
- experiment;
- evidence location.

---

## AC-06 Goal Notification

When a goal transitions from `NOT_REACHED` to `REACHED`, the coding agent SHALL explicitly notify the developer.

---

## AC-07 Goal Regression

If later valid evidence returns:

```text
reacquisition_rate = 0.82
```

the goal SHALL transition:

```text
REACHED → REGRESSED
```

and the developer SHALL be notified.

---

## AC-08 Automatic Simulation Presentation

When a task produces a significant simulation failure, the Pi Factory SHALL be capable of opening the corresponding simulation at or near the relevant failure event.

---

## AC-09 Contextual Obsidian Navigation

When the developer requests:

```text
"Show me where this requirement fits in the system."
```

the coding agent SHALL be capable of opening the corresponding Obsidian V-cycle view without requiring manual artifact search.

---

## AC-10 Rebuildability

Deleting the derived engineering database and rebuilding it from canonical project artifacts SHALL reconstruct the same traceability graph, excluding transient runtime state explicitly documented as noncanonical.

---

# 37. Recommended Implementation Order

## Phase 1 — Engineering ontology

Implement:

```text
Artifact
Feature
Requirement
Metric
Goal
Test
Run
Evidence
Edge
```

Then build Markdown → SQLite indexing.

Do not build UI yet.

---

## Phase 2 — `/goal`

Implement:

```text
/goal
goal persistence
goal evaluation
goal state machine
metrics ingestion
```

Demonstrate one drone requirement progressing:

```text
NOT_REACHED
    ↓
REACHED
    ↓
REGRESSED
```

---

## Phase 3 — Simulation evidence

Create deterministic run manifests.

Connect:

```text
requirement
→ goal
→ experiment
→ run
→ metric
→ evidence
```

---

## Phase 4 — Engineering Context MCP

Expose:

```text
get_feature_context
trace_requirement
get_goal
get_goal_evidence
get_latest_failure
present
```

Integrate these tools into Pi Factory.

---

## Phase 5 — Presentation Router

Implement adapters for:

```text
Obsidian
IDE
simulation viewer
```

Keep adapters independently replaceable.

---

## Phase 6 — Obsidian Plugin

Build only:

1. V-cycle view;
2. Feature dossier;
3. Goal status.

Do not reproduce generic Obsidian features.

---

## Phase 7 — Context Delta

Add:

```text
/catchup FEATURE
```

and human-review checkpoints once the basic feature graph has proven useful.

---

# 38. Architectural Principle to Preserve

The project should maintain the following separation:

```text
CANONICAL ENGINEERING STATE
           │
           ▼
    Engineering Graph
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
   AGENT       HUMAN
  queries      views
     │           │
   MCP        Obsidian
```

The human and the coding agent SHALL share the **same underlying engineering ontology**.

Obsidian SHALL NOT become an isolated human knowledge base.

The coding agent SHALL NOT maintain an isolated interpretation of system state.

Both SHALL navigate the same V-cycle.

---

# 39. Product Vision

The intended developer experience is:

```text
Developer writes intent.
        ↓
Agent implements.
        ↓
Factory validates.
        ↓
Simulation produces evidence.
        ↓
Goals evaluate automatically.
        ↓
Developer is notified only when something matters.
        ↓
Relevant visualization opens automatically.
        ↓
Developer can immediately navigate:
why → requirement → design → code → test → evidence.
```

The resulting system should allow agentic implementation speed to increase without proportionally increasing human loss of system understanding.

The engineering-context layer therefore acts as a bridge between:

```text
machine development velocity
            and
human system comprehension
```

That is the primary success criterion for the system.