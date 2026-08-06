# Design: Factory Evidence Lifecycle, Freshness, and Recovery

**Date:** 2026-08-07
**Status:** Approved; foundation implemented with follow-ups listed below
**Author:** Colin AUBE (with AI assistance)

## Implementation status (2026-08-07)

Delivered:

- content-addressed artifacts, validated durable run manifests, exact-path
  evidence commits, evidence query APIs, and browser task evidence;
- append-only journals, atomic checkpoints, binary/untracked patch snapshots,
  conservative recovery classification, inspect/resume/abandon CLI flows, and
  explicit start blocking when an interrupted run exists;
- explicit agent interruption classification and fresh-session continuation for
  context-limited development attempts;
- content-based dependency fingerprints, start/completion preflight, and a
  read-only reconciliation inventory that never invents task attribution;
- shared Python-backed evidence, preflight, reconciliation, and run-state APIs
  consumed by the browser and read-only PIF system-context tools;
- the `/system` navigator, durable implementation/validation/review views, and
  guarded interrupted-run recovery controls.

Verified after implementation with 654 Python tests, Pyright, Ruff, 552
TypeScript tests, and TypeScript typechecking.

Known follow-ups (not silently treated as complete):

- publication queue retry and bounded reconciliation repair commands, plus a
  severity-aware CI reconciliation gate;
- an explicit evidence schema-v2 migration that makes generic dependencies
  mandatory rather than optional for older manifests;
- process-kill/reboot integration coverage and continuation support for
  context-limited roles other than development;
- richer browser focus URLs and the later feature/SR briefing, validation matrix,
  decision timeline, and grounded natural-language guide.

## 1. Context

The factory now produces useful project artifacts and runtime evidence:
requirements, plans, tasks, trace links, validation reports, role transcripts,
human-review decisions, and captured review patches. The browser can navigate the
artifact graph and inspect a task's retained human-review history.

That is not yet a dependable foundation for a long-lived system guide:

- runtime evidence lives under ignored `sessions/.factory-transcripts/` paths;
- a completed session record is written only after `run_task` returns;
- live status can identify where a process stopped, but cannot resume the node;
- validation freshness is specialized to requirement checksums rather than a
  general dependency model;
- out-of-band human changes are not reconciled into implementation evidence;
- the browser and agent have no shared evidence API beyond individual commands;
- a reboot or context-limit failure can leave useful work in the working tree but
  no deterministic continuation record.

The future V-cycle navigator must not compensate for these gaps by generating a
convincing retrospective explanation. It needs durable, attributable, fresh
evidence first.

## 2. Goal

Create the reliability foundation that lets PIF and its browser remain current
throughout development:

1. publish immutable evidence from each factory run;
2. distinguish canonical artifacts, disposable indexes, immutable evidence, and
   local recovery state;
3. detect integrity defects and stale task-scoped evidence before expensive or
   unsafe transitions;
4. checkpoint runs so they can recover after a dead process, reboot, or agent
   context limit;
5. reconcile changes made outside `factory-run` without inventing provenance;
6. expose one deterministic evidence model to the browser and coding agent.

## 3. Non-goals

This design does not yet implement:

- the final feature/SR briefing UI or natural-language guide;
- S3, cloud-database, or vendor-specific artifact-store adapters;
- concurrent factory runs in one working tree;
- automatic attribution of manual commits to tasks or requirements;
- transparent continuation of an agent's private model context;
- deployment/release/incident ingestion;
- full symbol-level static analysis.

Those features consume this foundation in later designs.

## 4. Design principles

### 4.1 The browser is a projection, never the source of truth

The browser may cache layout or rendered Markdown, but all authoritative data
comes from repository artifacts, evidence manifests, and run checkpoints. A stale
browser cache is rebuilt, never treated as a project failure.

### 4.2 Recorded, derived, and synthesized information stay distinct

Every field shown to a user is classified as:

- **recorded** — directly authored or emitted by a deterministic producer;
- **derived** — computed deterministically from recorded inputs;
- **synthesized** — generated explanation with citations;
- **missing** — required information that was not recorded.

This foundation stores only recorded and derived data.

### 4.3 No inferred provenance

A changed file without a declared task relationship is reported as an
`unattributed_change`. Reconciliation may propose a relationship, but cannot write
one without confirmation.

### 4.4 Content defines freshness

Freshness uses SHA-256 fingerprints of relevant content and tool/schema versions,
not mtimes. Every stale result includes the dependency that changed.

### 4.5 Local durability precedes remote publication

A producer writes an artifact completely and atomically to the local store before
advancing. Publication to another filesystem or future remote backend is a
separate, retryable state.

### 4.6 A run never depends solely on conversation history

The working tree, checkpoint manifest, prior node outputs, and evidence artifacts
must be sufficient to start a continuation agent in a fresh context.

## 5. Four data layers

### 5.1 Canonical project artifacts

Version-controlled inputs remain in their existing locations:

- `requirements/`
- `docs/superpowers/specs/`
- `docs/superpowers/plans/`
- `tasks/`
- architecture/decision records introduced by a later design
- source code and tests
- `.factory/factory.yaml`

These are read directly; they are not uploaded into the browser.

### 5.2 Derived index

The trace graph, search index, health summaries, and rendered documents are
rebuildable projections. They are never committed as authoritative evidence.

The existing `factory.trace graph --json` remains the initial graph provider. New
evidence and run commands follow the same Python-model/TypeScript-presentation
boundary.

### 5.3 Immutable evidence

Each completed producer action emits an `EvidenceManifest` plus zero or more
content-addressed blobs.

Initial local layout:

```text
.factory/artifacts/
  objects/sha256/<first-two>/<full-hash>
  publish-queue/<hash>.json

evidence/
  runs/<run-id>.json
```

`.factory/artifacts/` is ignored runtime storage. `evidence/runs/*.json` contains
compact, portable manifests suitable for a separate evidence-only Git commit.
Large patches, logs, traces, screenshots, and reports are object-store blobs
referenced by hash.

The initial `LocalArtifactStore` supports a configurable filesystem root. A shared
network directory can therefore act as a team store without committing to a cloud
provider. The interface leaves HTTP/object-store publication for a later adapter.

### 5.4 Recovery state

Local, ignored operational state lives at:

```text
sessions/.factory-runs/by-session/<run-id>/
  journal.jsonl
  checkpoint.json
  checkpoints/<sequence>.patch
```

The append-only journal preserves transitions. `checkpoint.json` is an atomically
replaced latest-state projection. Patch checkpoints preserve uncommitted work.
Neither is presented as durable project evidence until finalized.

## 6. Evidence model

### 6.1 Blob reference

```json
{
  "sha256": "<64 lowercase hex characters>",
  "size": 1234,
  "media_type": "text/x-diff",
  "local": true,
  "publication": "local|queued|published|failed",
  "uri": null
}
```

Writing a blob is idempotent: equal bytes produce the same path and hash.
Publication verifies the destination hash before marking it published.

### 6.2 Run evidence manifest

```json
{
  "schema_version": 1,
  "run_id": "2026-08-07T12-00-00Z",
  "task_id": "T-042",
  "started_at": "...",
  "ended_at": "...",
  "start_commit": "...",
  "result_commit": "...",
  "outcome": "completed",
  "inputs": {
    "task": {"path": "tasks/T-042-....md", "sha256": "..."},
    "requirements": [{"id": "SR-007", "sha256": "..."}],
    "factory_config_sha256": "..."
  },
  "implementation": {
    "changed_files": ["src/example.py"],
    "patch": {"sha256": "...", "size": 1234, "media_type": "text/x-diff"}
  },
  "validation": [],
  "reviews": [],
  "decisions": [],
  "publication": {"state": "local", "errors": []}
}
```

The manifest records the final code commit. It is produced after that commit, so
if manifests are tracked, the factory creates a separate evidence-only commit
staging exact evidence paths rather than using `git add -A`. This avoids a
self-referential commit hash and prevents runtime files entering the commit.

### 6.3 Review evidence

The human-review archive introduced previously becomes a producer of immutable
review evidence. Each round records:

- task and run IDs;
- round and timestamp;
- start commit and candidate worktree fingerprint;
- decision, reviewed files, and annotations;
- captured patch blob;
- review-guide blob;
- automated reviewer verdict and findings when available.

The existing ignored review JSON remains a compatibility source during migration,
but the run manifest becomes the browser's durable source.

### 6.4 Validation evidence

Every validation entry records:

- test/gate identity and level;
- command or harness identity;
- requirement IDs or acceptance criteria verified;
- candidate tree fingerprint;
- input/configuration hashes;
- result (`passed`, `failed`, `error`, `blocked`, `flaky`, `not_run`);
- timing, metrics, logs, and artifact references.

`stale` is derived when current dependency fingerprints differ; it is not stored
as an unexplained boolean.

## 7. Artifact-store interfaces

Python owns the storage contract:

```python
class ArtifactStore(Protocol):
    def put(self, data: bytes, media_type: str) -> BlobRef: ...
    def get(self, sha256: str) -> bytes: ...
    def has(self, sha256: str) -> bool: ...
    def publish(self, sha256: str) -> PublicationResult: ...
```

The first implementation is `LocalArtifactStore(root: Path,
publish_root: Path | None = None)`:

- `put` writes through a temp file and atomic rename;
- an existing object is reused after hash verification;
- `publish` copies atomically to `publish_root` when configured;
- no `publish_root` means `local`, not an error;
- failed publication remains queued and retryable.

Project policy decides whether `local` is sufficient or publication is required
before task completion. The default is local durability required, publication
optional.

## 8. Factory-run lifecycle

The pipeline becomes:

```text
preflight
  create run journal + capture inputs
context-gather
  checkpoint
for each dev/review cycle:
  dev
  checkpoint working-tree patch
  validation
  publish validation evidence
  automated review
  publish review evidence
human review
  publish each decision before consuming it
finalize code commit
publish implementation manifest
(optional) evidence-only commit
session review
close journal
```

Every node transition has a stable `attempt_id` and appends `started`, then exactly
one of `completed`, `failed`, or `interrupted`. Replaying a completed attempt must
not rerun its side effects.

## 9. Freshness and preflight

### 9.1 Dependency fingerprints

A result records named dependencies:

```json
{
  "task:T-042": "sha256:...",
  "requirement:SR-007": "sha256:...",
  "factory-config": "sha256:...",
  "candidate-tree": "git-tree:...",
  "validator-version": "factory-validation-v1"
}
```

The freshness engine returns issues with:

- `code`;
- `severity` (`integrity`, `blocking`, `warning`);
- affected artifact/task/requirement;
- expected and actual fingerprints;
- repair action where deterministic.

### 9.2 Start-time hard failures

`factory preflight --task T-042` fails before invoking a model when:

- task/requirement IDs are malformed or duplicated;
- the selected task references missing mandatory artifacts;
- required factory configuration or gates are invalid;
- the baseline commit cannot be resolved;
- a conflicting interrupted run owns a different working-tree fingerprint;
- an evidence manifest needed for resume is corrupt or schema-incompatible.

A stale derived index is rebuilt and never causes a hard failure.

### 9.3 Completion blockers

Before human approval/completion, the factory blocks when:

- required task-scoped validation is missing, failed, or stale against the
  candidate tree;
- mandatory review evidence could not be persisted;
- unresolved must-fix annotations remain;
- the implementation manifest cannot be finalized.

Unrelated stale requirements remain warnings.

### 9.4 Explicit override

A project may permit an authorized human to override a completion blocker. The
override requires a recorded reason and becomes evidence. Integrity failures
(malformed canonical artifacts, corrupt checkpoint, unresolved baseline) cannot
be overridden.

## 10. Reconciliation

`factory evidence reconcile [--task T-042] [--json]` compares canonical artifacts,
Git history, current evidence manifests, and local run state.

It reports:

- completed tasks missing evidence;
- manifests whose commits no longer resolve;
- code commits or working-tree changes with no task attribution;
- test/requirement links whose latest results are stale;
- missing local blobs and failed publication;
- abandoned/interrupted runs;
- legacy review evidence eligible for migration.

Reconciliation is read-only by default. `--repair` may perform only deterministic
operations: rebuild derived indexes, retry publication, and migrate evidence whose
provenance is already explicit. It never assigns an unknown commit to a task.

Invocation points:

- lightweight check when PIF starts;
- scoped check when the browser opens an artifact;
- full check in CI;
- explicit user command for repair.

## 11. Checkpoint and resume

### 11.1 Checkpoint contents

The latest checkpoint records:

- run/task IDs and pipeline node;
- node attempt and remaining budgets;
- start commit, current HEAD, and working-tree fingerprint;
- patch-checkpoint blob/path;
- completed node output references;
- active/previous Pi session IDs;
- pending human-review round;
- latest validation and review evidence references;
- interruption reason.

### 11.2 Stale-lock recovery

The existing PID lock continues preventing a concurrent run. When its PID is dead,
PIF reads the checkpoint and offers:

- Resume from the last safe checkpoint
- Inspect changes/evidence
- Restart the interrupted node
- Abandon the run

No option mutates the working tree until fingerprint compatibility has been
verified.

### 11.3 Resume compatibility

Resume is safe only when:

- the recorded start commit still resolves;
- current HEAD matches the checkpoint expectation;
- working-tree fingerprint matches the checkpoint, or the saved patch can be
  applied cleanly to the expected tree;
- referenced completed artifacts pass hash verification.

Otherwise PIF asks the user to preserve/adopt external edits, restart from a new
baseline, or abandon. It never silently merges external work into the old run.

### 11.4 Context-limit continuation

A context-limit or token-budget interruption marks only the agent attempt as
interrupted. The factory:

1. preserves transcript, session ID, patch checkpoint, and deterministic handoff;
2. starts a fresh Pi role session;
3. supplies task context, prior completed outputs, current diff, gate results, and
   remaining work from the checkpoint;
4. continues within the same configured attempt budget.

This continuation may be automatic because repository compatibility has not
changed. Reboot/process recovery requires user confirmation by default.

## 12. PIF and browser integration

The existing extension remains the presenter and control surface:

- `/factory-run` starts the producer pipeline;
- `/factory-watch` opens the navigator focused on the active run;
- `/review-plans` remains a compatible document-focused entry point;
- a later `/system` command becomes the general V-cycle entry point.

Python CLI commands provide the shared model:

```text
factory evidence run <run-id> --json
factory evidence task <task-id> --json
factory evidence reconcile --json
factory preflight --task <task-id> --json
factory run-state current --json
factory run-state resume <run-id>
```

The TypeScript browser server calls these commands, as it already calls
`factory.trace`. Coding-agent tools wrap the same commands. There is no second
TypeScript implementation of freshness, evidence parsing, or resume policy.

Initial browser updates use polling of immutable manifests and the checkpoint
projection. Server-sent events are deferred until polling proves insufficient.
The browser remains read-only except for explicit, narrow commands such as retry
publication or request resume; each command routes through Python validation.

## 13. Failure handling

| Failure | Behaviour |
|---|---|
| local evidence write fails | do not advance the producer node |
| optional publication fails | queue retry, warn, continue |
| required publication fails | block completion |
| corrupt evidence manifest | quarantine from views, report integrity failure |
| missing blob | show manifest metadata plus missing-artifact warning |
| stale derived index | rebuild automatically |
| partial journal tail | ignore incomplete final line; use atomic checkpoint |
| process/reboot interruption | stale-lock recovery flow |
| context limit | checkpoint and fresh-session continuation |
| external edit after interruption | require explicit preserve/adopt/restart decision |
| browser unavailable | factory continues; evidence production is UI-independent |

## 14. Security and data handling

- Artifact paths are confined to configured roots.
- Blob hashes are verified on read and publication.
- Browser paths retain the existing repository traversal protection.
- Logs may contain secrets; publication policy supports media-type/path exclusion
  and redaction before a blob becomes publishable.
- Raw transcripts are local-only by default. Publishing them requires explicit
  project configuration.
- The browser never serves arbitrary object hashes not referenced by a manifest
  visible to the current project.

## 15. Testing strategy

### Python unit tests

- content-addressed put/get/idempotency and hash verification;
- atomic manifest and checkpoint writes;
- publication states and retry;
- dependency fingerprint and stale-reason calculation;
- preflight severity and exit status;
- journal replay and partial-tail tolerance;
- compatible/incompatible resume decisions;
- reconciliation without inferred attribution;
- context-limit continuation handoff construction.

### Python integration tests

- a real temporary Git repository from run creation through final evidence;
- interrupted dev work resumed from a patch checkpoint;
- validation evidence becoming stale after a relevant code/config change;
- optional and required publication policies;
- evidence-only commit stages exact paths and references the code commit.

### TypeScript tests

- PIF command wrappers parse success and structured failures;
- browser models render local/queued/published and stale reasons;
- interrupted-run actions route to deterministic Python commands;
- no TypeScript freshness or resume-policy duplication.

### End-to-end tests

- kill the orchestrator after a checkpoint and resume the same run;
- simulate a context-limit backend result and continue in a fresh role session;
- open the browser during a run and observe node/evidence transitions;
- clone with compact manifests but absent optional blobs and get an honest degraded
  view rather than a crash.

## 16. Delivery decomposition

This design is delivered through four implementation plans, each independently
useful and reviewable:

1. **Evidence store and manifests** — content-addressed local storage, compact run
   manifests, migration of human-review records.
2. **Run journal and recovery** — checkpoints, patch snapshots, stale-lock resume,
   context-limit continuation contract.
3. **Freshness, preflight, and reconciliation** — fingerprints, policy, CLI, CI
   gate.
4. **PIF/browser evidence integration** — shared command wrappers, live run and
   evidence status, recovery controls.

The user-facing feature/SR briefing and grounded guide follow in a separate design
after this foundation is operational.

## 17. Success criteria

The foundation is complete when:

- every interactive `factory-run` creates a durable, hash-verifiable evidence
  manifest tied to its code commit;
- a browser or agent can retrieve the same task/run evidence through one Python
  model;
- task-scoped stale validation blocks completion with an actionable reason;
- out-of-band changes are visible as unattributed rather than silently assigned;
- killing the process after a checkpoint leaves a run that can be inspected and
  resumed without relying on conversation history;
- context-limit continuation starts a fresh session from deterministic state;
- missing optional remote artifacts degrade honestly without making the project
  browser unusable.
