# Design: The Requirement Doctor

Date: 2026-08-06
Status: Approved (brainstorming) — ready for implementation planning
Builds on:
- `2026-08-05-drone-factory-separation-design.md` §7 — deferred the doctor pass
- `2026-08-05-project-configurable-gates-design.md` — the project-declares-its-own
  seam, applied here to metrics rather than gates
- `2026-08-03-review-plans-browser-and-trace-health-design.md` — the trace graph,
  gaps and health this extends

## 1. Problem

Requirements exist in the drone repository only as prose. Nothing turns them into
register entries, so nothing can validate them.

Measured state of `cool_physical_ai_project` on 2026-08-06:

| | count |
|---|---|
| tasks (`tasks/T-*.md`) | 25 |
| tasks declaring `satisfies:` | 0 |
| system requirements | 1 (`SR-001`) |
| product specs / plans | 2 / 2 |
| `.factory/factory.yaml` | absent |

`factory trace status` therefore reads near 0% on the `task->SR` slot class, and
`SR-001`'s `upstream: [BR-002]` dangles because no `BR-*.md` exists anywhere.
The separation design named this the true state and the reason the doctor exists.

### 1.1 Two blockers found while designing

**The factory ships drone vocabulary.** `sim_harness.py:12` declares

```python
_TRIAL_SCORERS = {"preemption_success_rate": trial_preempted}
```

as a module-level constant, and `validation/metrics/preemption.py` hardcodes
`"shark"`, `"patrol"`, `active_directive.kind` and `detections[].label`. Any
requirement binding to any other metric raises `UnknownMetricError` permanently,
and no amount of work in the drone repository can change that. A doctor that
mints requirements would mint unmeasurable ones by construction.

**A requirement cannot exist without a binding.** `register.py:9` requires
`binding`, and `_parse_binding` requires `harness`, `experiment`, `metric` and
`assert`. An SR whose measurement is undecided cannot be written down at all —
so the register cannot represent the most common state of a real requirement:
agreed in substance, not yet agreed in measurement.

## 2. Decisions locked during brainstorming

1. **The agent proposes, the human dispositions.** No requirement enters the
   register without an explicit human accept.
2. **The register gains a proposed state, and it is derived, not declared.** An
   SR with no `binding:` is proposed; an SR with one is active. There is no
   `status:` field, so the recorded state cannot disagree with the content.
3. **Candidates are ephemeral.** Nothing is written until accept, mirroring how
   `next_gap` returns a `Proposal` and only `trace link` writes.
4. **The CLI owns only what is mechanical and fails silently.** Everything that
   shapes what the agent can perceive or express belongs to the agent. See §2.1.
5. **Completion is the agent's judgement.** "Have we captured every behaviour in
   this spec" is not computable over prose, and a checklist proxy dressed as a
   fact is worse than an honest judgement.
6. **Metric-implementation tasks: the CLI reports, the agent authors.** Whether a
   metric name is present in the declared scorers module is a set lookup. The
   task's title, dod and body are authored work.
7. **No keyword extraction.** Nothing parses for `shall`, EARS shapes, or
   heading structure to decide what a requirement is.
8. **`source:` is provenance, never a completion checklist.** See §2.2.

### 2.1 The split, and why this one is not scripting-for-its-own-sake

An earlier draft of this design had the CLI enumerate spec sections by heading and
hand the agent one section at a time. That was wrong, and it violated a principle
this codebase had already written down. `propose.py:97-100`:

> Ranking only ORDERS the list. It is never truncated: a lexical heuristic must
> not get to decide which links are reachable, or a correct match phrased in
> different vocabulary becomes unpickable.

Section-by-heading enumeration is that same heuristic applied to a wider input,
and it fails the same way: one heading can hold three claims, or half of one.

The line that survives is narrower — the CLI owns work that is **mechanical and
fails silently**:

| CLI | Agent |
|---|---|
| Report the register: every SR, its statement, source and state | Which claims in the prose are requirements |
| Assign the next SR id | How many requirements are in a passage |
| Construct and write frontmatter | Whether an existing SR already covers this ground |
| Report whether a metric is in the declared scorers module | When the pass is finished |
| `trace check` — a gate, unchanged | Whether to author a metric task, and its content |

Each CLI item is either a collision hazard (`_next_id` racing a human running
`factory requirements new`), a silent-malformation hazard (hand-authored YAML that
`parse_requirement` rejects, discovered much later by something else), or a set
lookup. None of them constrains what the agent can see or say.

### 2.2 What was traded away

Without a deterministic coverage checklist, two doctor runs over the same
repository may propose different sets. There is no machine fixpoint. The human
accepting candidates is the fixpoint and the register is the durable state.

This is a deliberate loss. The alternative — an anchor-per-heading checklist —
buys reproducibility by making a heading the unit of coverage, which silently
caps a section at one requirement and makes a later-noticed fourth claim in an
already-"covered" section unreachable. Reproducible and wrong is worse.

## 3. What already exists and is not respecified

**Linking existing tasks to requirements is built.** `propose.py:27-32` maps
`sr_unsatisfied -> task` and `task_no_sr -> sr`; `trace next` serves ranked,
never-truncated candidates and `link_satisfies` commits them. The drone repo's 25
unlinked tasks are reachable today through `\trace-fix`.

The doctor's new capability is **minting requirements that do not yet exist**. It
does not link, exempt, defer, or validate.

## 4. Prerequisite: the scorer seam

Folded into this design because promotion (§6.3) depends on it, and because it is
small.

`.factory/factory.yaml` gains one key on the existing harness entry:

```yaml
harnesses:
  sim-testbench:
    type: sim-testbench
    traces_dir: validation/traces
    scorers: drone.validation.scorers      # module exporting metric -> callable
```

`SimTestbenchHarness.from_config` imports that module and builds its scorer map
from it. The module-level `_TRIAL_SCORERS` constant is deleted, and
`src/factory/validation/metrics/preemption.py` moves to the drone repository as
`src/drone/validation/scorers.py`.

Consequences:

- The factory stops shipping drone vocabulary. The boundary rule from the
  separation design (§2) is honoured for metrics, not only for code and tasks.
- `UnknownMetricError` becomes a **target-repo condition** — a metric the project
  has not implemented yet — rather than a permanent factory limit.
- A metric-implementation task now delivers a file in the **same repository** as
  the requirement it serves. The cross-repo dangle that an earlier version of this
  design would have created disappears.

A harness entry with no `scorers:` key resolves to an empty scorer map: every
binding is unimplemented, reported honestly (§8), and nothing crashes.

This lands on top of `inc2`'s `factory.config`, not beside it — that branch is
already editing `load_config`.

### 4.1 The trust boundary this introduces

There is no dynamic import anywhere in the factory today. Resolving `scorers:`
means the factory imports and executes a module from the target repository.

That is not a new exposure. `.factory/factory.yaml` already causes the factory to
run arbitrary target-authored shell commands — `ConfigGateRunner` executes every
gate step via `subprocess.run(cmd, shell=True)`, and `playgrounds.services`
launches target commands the same way. Importing a module the same file names is
strictly less powerful than that. The trust posture is unchanged: **a project's
`.factory/factory.yaml` is trusted code, and running the factory against a
repository means running that repository's declarations.**

The import must be scoped so it stays a target-repo concern:

- the module is imported by name against the target repo's own interpreter
  environment, not injected into the factory's package namespace
- an import failure is reported as an unusable harness — the same class as an
  undeclared one — and never crashes graph or status commands, which is why §8
  keeps this out of the trace path entirely

## 5. The proposed requirement state

### 5.1 Representation

```markdown
---
id: SR-004
title: Investigate is abandoned when the swim zone clears
statement: When the swim zone becomes empty during an investigate directive, the
  navigation system shall abandon the investigation and resume patrol.
domain: behavioral
upstream: []
source: docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md
---

## Rationale
...
```

No `binding:`, no `checksum:`, no `status:`. The absence of the binding **is** the
state.

### 5.2 Blast radius

Every change is additive; no existing green test needs to change its assertions.

| File | Change |
|---|---|
| `register.py:9` | `binding` leaves `_REQUIRED` |
| `register.py:24` | `Requirement.binding: Binding \| None` |
| `register.py:71` | `content_checksum` raises on a proposed SR; callers must not reach it |
| `register.py:89` | `is_checksum_current` returns `True` for a proposed SR — there is nothing to be stale against, and `False` would print `STALE` forever |
| `requirements/cli.py:60` | `cmd_index` skips proposed SRs rather than checksumming them |
| `requirements/cli.py:20` | `_TEMPLATE` mints proposed — deleting the hardcoded `sim-testbench` / `preemption_success_rate` / `shark_detected` template, closing separation design §7 |
| `requirements/cli.py:73` | `cmd_status` prints `[proposed]`, not `[current]` — `is_checksum_current` returning `True` would otherwise read as a validated-and-fresh requirement |
| `requirements/cli.py:84` | `cmd_show` prints `binding: (proposed — not yet measurable)` |
| `trace/model.py:18` | `Node` gains `proposed: bool`, set for `sr` nodes whose frontmatter has no `binding` key |
| `pipeline.py:14` | `select_requirement_ids` skips proposed SRs |
| `report.py:37` | a proposed SR named in a task's `satisfies:` yields an honest `error` entry instead of crashing on `binding.harness` |
| `gaps.py` | see §8 |
| `health.py` | see §8 |

`report.py` already isolates a bad requirement to its own entry, and
`pipeline.py:39-42` already treats an `error` entry as a setup gap rather than a
suite failure. A proposed SR reaching validation therefore degrades correctly
with no new control flow.

## 6. The doctor CLI

`python -m factory.doctor`, argparse prog `factory-doctor`, matching
`factory-trace` and `factory-requirements`.

### 6.1 `factory doctor context`

Prints, as text or `--json`, the agent's field of view:

- every spec file path under `docs/superpowers/specs/`
- every requirement in the register: id, title, statement, domain, `source`,
  state (`proposed` / `active`), and the binding when active
- the metric names exported by each declared harness's scorers module
- the harnesses declared in `.factory/factory.yaml`, or that the file is absent

It does **not** summarise, rank, filter, or excerpt the specs, and it does not
emit their text — the agent reads those files with its own tools. The command
provides only what the agent cannot cheaply derive: the register state and the
scorer inventory.

### 6.2 `factory doctor mint`

```
factory doctor mint --source <path> --title <t> --statement <s> [--domain behavioral]
```

Assigns the next SR id via the existing `_next_id`, constructs the frontmatter,
writes `requirements/SR-NNN.md`, prints the id and path.

`--source` is required and its path is verified to exist. This mirrors
`link_satisfies` refusing a non-existent target rather than writing a dangling
reference.

### 6.3 `factory doctor promote`

```
factory doctor promote SR-NNN --harness <h> --experiment <e> --metric <m> \
    --assert <expr> [--trials N] [--window-json '{"after_event":"shark","within_s":5}']
```

`--window-json` rather than a `k=v` list: the window carries typed values
(`within_s: 5` is a number, `after_event` a string) and a flat key-value syntax
cannot express that without guessing at types.

Fills the binding, making the requirement active, and writes the checksum.

It then reports whether `<m>` is present in `<h>`'s declared scorers module. It
**does not refuse** when the metric is missing — "bound, and we know it cannot run
yet" is a state the register is now able to hold honestly, and refusing would
push the project back to describing that state in prose.

### 6.4 `factory doctor task`

```
factory doctor task --satisfies SR-NNN --title <t> --dod <d> [--dod <d> ...] [--body -]
```

Assigns the next task id, constructs frontmatter with `status: todo` and the
`satisfies` link, writes `tasks/T-NNN.md`. The payload is authored by the agent;
the id, frontmatter and write are not.

This is `polish/routing.py:19` with an agent-authored payload in place of a
`Finding` — the same division that routing already proves.

## 7. The doctor skill

`.pi/skills/doctor/SKILL.md`, modelled on `.pi/skills/trace-fix/SKILL.md` but
with the ownership line drawn where §2.1 puts it.

The skill owns: reading the specs, judging which claims are falsifiable
requirements, judging whether the register already covers them, phrasing
statements, deciding when the pass is done, and authoring metric-task content.

The skill does not own: id assignment, frontmatter, or the scorer lookup.

Loop:

1. `factory doctor context`, then read the spec files directly.
2. Judge. For each claim that could be contradicted by a measurement and that no
   existing requirement covers, propose one requirement to the human with its
   statement and the passage it came from.
3. Wait. One proposal, one confirmation. Never batch approvals.
4. On accept, `factory doctor mint`.
5. When the human is ready to bind a requirement, `factory doctor promote`. If
   promote reports the metric is unimplemented, propose a metric task and, on
   accept, `factory doctor task`.
6. Say when you believe the pass is complete, and say what you based that on.

Step 6 is a claim, not a gate. `factory trace check` remains the gate and remains
stateless.

## 8. Reporting: gaps and health

Today `sr_unvalidated` means "absent from the validation report" and conflates two
different facts. Against the drone repo — which has no `.factory/factory.yaml` at
all — every requirement lands in that bucket permanently, and because requirements
cannot be exempted (`write.py:66`), each one must be deferred by hand.

It splits into three:

| kind | meaning | derived from | disposition | in `SR validated` denominator |
|---|---|---|---|---|
| `sr_proposed` | no binding yet | `Node.proposed` | **deferred** (derived) | no |
| `sr_unvalidatable` | bound, but the run could not happen | report entry `state == "error"` | pending | yes — unfilled |
| `sr_unvalidated` | bound, never attempted | report entry absent or `never_validated` | pending | yes — unfilled |

### 8.1 Why `sr_unvalidatable` is read from the report, not from the config

The obvious derivation — load `.factory/factory.yaml`, check the harness is
declared, import the scorers module, check the metric is in it — would make
`factory trace status`, a read-only command, import and execute target-repo code
(§4.1). That is the wrong place for it.

It is also unnecessary, because the answer is already recorded.
`run_requirement_validation` (`report.py:37-44`) catches any harness or scorer
failure and writes an `error` entry, and `validation_status.py:12` already models
`"error"` as a first-class state with the message attached. So:

- **`sr_unvalidatable` is an SR whose last validation attempt errored** — no
  harness declared, no scorers module, metric not in it, missing trace fixture.
  The reason is already in `SrStatus.error` and is surfaced in the gap detail.
- **`sr_unvalidated` is an SR nobody has tried yet.**

This keeps the trace path free of config loading and dynamic imports entirely, and
it is more honest besides: on a repo where validation has never run, an SR with an
undeclared harness reads as *unvalidated*, not *unvalidatable*, because nothing has
established that it cannot run. We do not know until we try.

### 8.2 Reasoning behind each row

- **`sr_proposed` is excluded from the validation denominator** because nobody has
  yet claimed the requirement is measurable. Counting it as an unfilled validation
  slot would punish the doctor for recording a real state.
- **`sr_proposed` is dispositioned `deferred`, derived from the absent binding, not
  from `trace_deferred:` frontmatter.** A human accepted this requirement knowing
  its measurement was unresolved; that is precisely "discussed, still open". Making
  it `pending` would red-gate the repository the moment the doctor is used, which
  is hostile to the workflow it exists to enable.
- **`sr_unvalidatable` stays in the denominator and counts as unfilled.** Excluding
  it would hand a project with no config a green validation score — the same false
  green the configurable-gates design removed.

Proposed requirements remain in the **`SR satisfied`** denominator. A requirement
nobody has written a task for is a real gap whether or not its binding is decided,
and that gap is the doctor's whole reason for existing.

`compute_health` reports proposed separately, beside the existing `dangling` and
`deferred` lines.

This also repairs `\trace-fix`: the deferral pressure-valve described above stops
being the only legal move on a requirement gap.

## 9. Testing strategy

**Register (`-m unit`):**
- a requirement with no `binding:` parses, and `binding is None`
- a requirement with a binding parses unchanged — the existing suite is the guard
- `is_checksum_current` is `True` for a proposed requirement
- `content_checksum` raises on a proposed requirement rather than returning junk
- `cmd_index` leaves a proposed requirement's file byte-identical

**Scorer seam:**
- a harness resolves scorers from a module named in config
- a harness entry with no `scorers:` key yields an empty map, and a binding
  against it reports unimplemented rather than raising at load
- `UnknownMetricError` still raised for a metric absent from a populated module
- a migration guard asserting the factory no longer imports
  `validation.metrics.preemption`

**Doctor CLI:**
- `context` lists every register entry and every declared scorer, against a temp
  repo with one proposed and one active requirement
- `context` on a repo with no `.factory/` reports the absence rather than failing
- `mint` assigns the next free id, writes parseable frontmatter, and refuses a
  `--source` path that does not exist
- `mint` twice yields consecutive ids
- `promote` fills the binding, writes the checksum, and reports an unimplemented
  metric without refusing
- `task` writes a task with `satisfies` set and `status: todo`

**Gaps and health:**
- `load_nodes` sets `proposed` on a requirement with no `binding:` key, and leaves
  it `False` for a bound one and for every non-`sr` node
- a malformed requirement file still degrades to a filename-labelled node rather
  than crashing the graph — the existing `model.py` contract, re-asserted because
  `proposed` adds a second frontmatter read
- a proposed requirement produces `sr_proposed`, dispositioned deferred
- a requirement whose report entry has `state == "error"` produces
  `sr_unvalidatable`, and the gap detail carries the recorded error message
- the same requirement with **no** report at all produces `sr_unvalidated`, not
  `sr_unvalidatable` — the distinction in §8.1
- a bound, runnable, unrun requirement still produces `sr_unvalidated`
- proposed requirements are out of the `SR validated` denominator and in the
  `SR satisfied` denominator
- `build_graph` performs no config load and no dynamic import — asserted by
  building a graph in a repo whose `.factory/factory.yaml` declares a scorers
  module that would raise on import
- `trace check` does not fail on a proposed requirement alone

**Skill:** a prompt test asserting the skill names `factory doctor context` and
states that completion is the agent's call, mirroring
`test/skill-prompt.test.ts:37`.

## 10. Non-goals

- **`factory init`.** Interactive project onboarding — a default config, an
  interview for project specificities, and an extension task that becomes the
  project's first development work — is the next spec. The doctor is a step it
  will call, not a part of it.
- **Inferring business requirements.** `BR-*` and `SR-001`'s dangling
  `upstream: [BR-002]` are untouched.
- **An SR->spec slot class in `health.py`.** `source:` is provenance. Adding a
  sixth slot class changes the health denominator and belongs in its own change.
- **Auto-accept, batch accept, or any mode where a requirement enters the register
  without a human.**
- **Changing `trace check` semantics**, the candidate ranking, or anything else in
  the `\trace-fix` loop. Ergonomic fixes to that loop are specified separately in
  `2026-08-06-trace-fix-field-of-view-design.md`.
- **Re-specifying task->SR linking**, which `trace next` already does (§3).
