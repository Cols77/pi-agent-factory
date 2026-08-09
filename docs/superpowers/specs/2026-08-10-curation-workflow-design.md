# Curation Workflow — Design

**Status:** Draft for written review
**Date:** 2026-08-10

## 1. Why

The factory can build a system. It cannot yet keep the system's own description honest.

Three artifact families describe what the system is and whether it works: the requirement
register, the traceability graph, and the navigator's declared bundles. Two of the three have
no way to be written.

Measured in `cool_physical_ai_project` on 2026-08-10:

- **181 system requirements exist. One has a `binding:` block.** The other 180 are *proposed* —
  `register.py` states it directly: "the absence of a binding IS the proposed state." A proposed
  requirement has no decided measurement, so nothing can validate it. The navigator reports each
  one as `[missing] (n/a) SR-nnn: proposed requirement has no binding to validate`, which is
  correct and useless.
- **Zero bundles exist, in any repository.** The 60-second feature briefing — the navigator's
  headline capability, built across Increments A and B — is scoped to `bundle:<id>`, and no
  bundle had ever been authored anywhere until a trial one was written for this design.
- **280 traceability gaps exist and 275 carry an explicit disposition.** Only 5 are open.

That last number is the point. Trace is the one family that is healthy, and it is healthy because
it is the only one with a vocabulary for deciding: `link`, `defer`, `exempt`, and a recorded
`disposition` on every gap. The other two families have no such vocabulary, so their backlog is
invisible rather than small.

The cause is mechanical, not cultural:

| CLI | Verbs | Can write? |
| --- | --- | --- |
| `factory-trace` | `status graph link next check exempt defer` | yes |
| `factory-requirements` | `new index status show` | only `new` — **no `bind`** |
| `factory-system` | `brief matrix timeline story reverse guide scope` | nothing |

`factory-system` reads two artifacts that nothing in the codebase can write. `factory-requirements`
can mint a requirement but never decide how to measure it.

## 2. Goal and non-goals

**Goal.** A reliable, gated workflow that keeps the system navigable: every requirement has a
decided measurement and an owner, every traceability gap has a disposition, every bundle resolves,
and drift is detected rather than absorbed.

**Non-goals.**

- **Judging whether a binding is a *good* measurement.** The gate is structural closure. Whether
  `preemption_success_rate >= 0.90` is the right assertion for SR-001 is a human judgment, which is
  why the pipeline has a human review node.
- **Running the testbench.** A binding is accepted when it is well-formed and owned, not when it
  has been executed. Execution belongs to validation runs, which already exist.
- **Minting requirements from prose.** That is `doctor`, and it works.
- **Bundle *content* strategy.** Which features deserve bundles is a human decision; this design
  covers how a bundle is written and kept honest, not which ones should exist.
- **No new claim classes** in the navigator, and no change to its read path.

## 3. The unifying model: disposition and staleness

Generalise trace's model rather than invent one. Every curated item is either **decided** or
**pending**, and every decided item can go **stale** when its inputs change.

| Family | Legal states | Staleness signal | Today |
| --- | --- | --- | --- |
| Requirements | measured-passing · measured-failing · planned · unmeasurable · declined | `checksum` over statement + binding | states absent; no `bind`; `index` launders staleness |
| Trace | linked · deferred · exempt | — (a gap is recomputed from source each time) | complete |
| Bundles | all members resolve · members with recorded absence | none | no writer at all |

**The gate, in one sentence: zero pending, zero stale.**

It is mechanically checkable and needs no model. It verifies that every requirement has a decided
measurement and an owner — never that the measurement is a good one.

**Warnings do not fail the gate.** Findings carry a severity, reusing the tiers
`freshness.model.FreshnessSeverity` already defines — `INTEGRITY`, `BLOCKING`, `WARNING`. Pending
and stale are `BLOCKING`; an unmeasurable requirement (§3.3) is a `WARNING`. `check` exits non-zero
on blocking findings only, and always reports warnings.

### 3.1 Requirement states

- **measured-passing** — bound, checksum current, a validation result exists and passes.
- **measured-failing** — bound, checksum current, a validation result exists and fails.
- **planned** — bound, checksum current, no result yet, and a linked task exists in the ledger
  that is **not already `done`**.
- **unmeasurable** — the measurement is decided (metric, assertion) but **no harness is named yet**.
  Legal, and carries a `WARNING`. See §3.3.
- **declined** — deferred or exempt, with a recorded reason.
- **pending** — anything else: unbound with no disposition, bound but orphaned, or stale.

`measured-failing` is legal and must render visibly distinct from `measured-passing`. A failing
measurement is honest evidence; flattening it into "measured" is the same class of lie as
reporting a stale pass as a pass.

**Where each input comes from — one owner per fact.**

| Input | Owner |
| --- | --- |
| the binding | the requirement's own `binding:` frontmatter, via `requirements.register` |
| checksum currency | `register.is_checksum_current` |
| a validation result | the `validation` array of run manifests, via `evidence.manifests.list_run_manifests` |
| the linked task | task frontmatter `satisfies`, via `orchestrator.ledger.load_tasks` |
| a disposition | the trace graph's `disposition` on the corresponding gap |

A manifest `validation` entry is a list of `{report: <blob ref>, requirements: [...]}`, where each
requirement carries `id`, `passed` and `stale` among others. **passing** means every requirement
entry for that id has `passed: true`; any `passed: false` is **failing**. The `report` blob is not
read — the verdict comes from the inline array, matching the rule already established for
`latest_validation` in the navigator's briefing aggregates.

Requirements are read through `requirements.register` and tasks through `orchestrator.ledger` — the
existing loaders. No parallel parsing rules.

The `done`-task exclusion in **planned** is load-bearing. Without it, a completed task that never
produced a result parks its requirement in `planned` permanently — a parking space disguised as a
plan.

### 3.2 Staleness

`register.content_checksum` already computes a digest over statement, harness, experiment, metric,
assert expression, trials and window. It deliberately excludes `cadence`, because scheduling is not
a metric input and changing it must not stale the requirement. `is_checksum_current` returns `True`
for proposed requirements so they do not print STALE forever. This machinery is correct and is kept.

**`factory-requirements index` currently destroys the signal it depends on.** `cmd_index`
recomputes the checksum for every bound requirement and writes it back unconditionally, recording
`"stale": False` regardless of what it found. Editing a requirement's statement — the exact event
the checksum exists to catch — is silently re-stamped as current by the next routine `index` run.
Nobody re-judges whether the binding still measures the changed statement.

New rule: **`index` writes a checksum only where none exists.** A stale checksum is reported and
exits non-zero. Staleness is cleared only by a decision (§4).

### 3.3 The harness may not exist yet

A binding names a `harness`. The workflow does **not** validate it against a registry, because a
registry of harnesses does not exist and inventing one would block every binding on infrastructure
that has not been built.

Instead, `bind` **asks the human** which harness measures this requirement, and accepts three
answers:

1. **An existing harness** — e.g. `sim-testbench`, the only one observed in the register today.
   The requirement proceeds to `planned` or `measured`.
2. **A harness that does not exist yet** — recorded as named, and the requirement is `planned`:
   building that harness is work, tracked like any other, and the requirement cannot be measured
   until it lands.
3. **"I don't know yet"** — the harness is left undefined. The requirement is `unmeasurable` and
   carries a `WARNING`. It is honest and visible rather than blocking, and it resolves the moment a
   harness is named.

The third answer requires a representation change: `Binding.harness` is currently a required `str`
with no default and must become `str | None`. `content_checksum` joins `b.harness` directly, so it
becomes `b.harness or ""` — which leaves every currently-bound requirement's digest byte-identical
and adds behaviour only for the new `None` case. No existing requirement is staled by this change.

The general principle: **an unnamed harness is a warning, never a blocker.** A requirement whose
measurement is decided but whose instrument does not exist yet is strictly more honest than one
that was never decided at all, and the register must be able to say so.

### 3.4 Bundle drift

Bundle members are exact refs (`task:T-059`, `sr:SR-086`). Rename the task or retire the
requirement and the bundle quietly begins reporting `missing`, with no way to distinguish a member
that was always aspirational from one that used to resolve and moved. Bundles gain a checksum over
their resolved member set, so drift is a signal rather than an absence.

## 4. One CLI vocabulary

| Verb | Kind | requirements | trace | bundles |
| --- | --- | --- | --- | --- |
| `status` | read | exists | exists | new |
| `check` | read — **the gate**, non-zero exit on pending/stale | new | exists | new |
| `next` | read — next open decision with candidates | new | exists | new |
| `show` | read | exists | via `graph` | new |
| `bind` / `link` / `add`+`remove` | write — the positive decision | **new** | exists | new |
| `defer` | write — recorded reason | new | exists | new |
| `exempt` | write — recorded reason | new | exists | new |
| `index` | maintenance — checksums | exists (fixed) | — | new |

**`bind`** writes the `binding:` block (`harness`, `experiment`, `metric`, `assert`, `trials`,
`window`) and stamps the checksum, exactly as `doctor/write.py` already does when minting. It asks
the human for the harness and accepts "not yet" (§3.3); it never validates the harness against a
registry.

**`bind --reaffirm --reason "..."`** clears staleness without changing the measurement: it records
that the statement changed and the existing binding still measures it. A flag rather than a new
verb, to keep the vocabulary small. Reaffirming without a reason is refused.

**`defer` and `exempt` require a reason.** An empty or whitespace reason is refused — the existing
`Override` validation in `preflight/checks.py` sets this precedent and it is followed.

## 5. The curation pipeline

Same shape as `/factory-run`. The unit of work is a **batch of open decisions** — one or many.

A run selects a batch at `survey`, and `propose` makes one judgment per item in it. Batching is
what makes 180 pending requirements tractable; a strict one-decision-per-run loop would need 180
runs. Batch size is a parameter of the run, and a batch of one is the degenerate case, not a
special one.

The human review gate reviews **the batch as a set**, with per-item annotations — the same shape
`FileHumanReviewGate` already archives, where a decision carries an `annotations[]` list. A
rejection names the items it rejects; those return to `propose` while the approved items proceed.
This matters: forcing an all-or-nothing verdict on a batch of thirty would push a reviewer toward
approving items they have not actually examined.

```
survey → propose → [gate: schema + refs] → human review → apply → verify
```

| Node | Owns | Scope |
| --- | --- | --- |
| `survey` | compute the closure report; select the next pending item and its candidates | `allow=[]`, bash deny |
| `propose` | **the one judgment** — a binding, or an honest defer/exempt, with reasoning | `allow=[]`, bash deny |
| gate | mechanical: schema valid, harness exists, refs resolve | — |
| `review` | human approve/reject with annotations | reuses `FileHumanReviewGate` |
| `apply` | invoke the CLI that owns the write | no file access — CLI only |
| `verify` | re-run `check`; the run completes only if closure improved and nothing regressed | read only |

**No agent role receives write access to `requirements/**` or `bundles/**`.** The orchestrator
applies decisions by invoking the CLIs. This generalises the principle already stated in
`ROLE_SCOPE`, where Dev is allowed `src/**`, `tests/**` and `docs/traceability/**` and requirements
are deliberately excluded because they "remain human-owned and writable only through the registered
trace tools."

**One judgment per node invocation.** `doctor` and `trace-fix` both already state this rule — the
agent owns exactly one decision and the tools own every write. It is preserved because it is what
makes a proposal reviewable.

### 5.1 Why a separate runner

`runner.py` is task-centric throughout: it reads the task ledger, checks a DoD, commits code, and
records `changed_files` from a git range. A curation run satisfies no DoD and produces no code
commit. Reusing it wholesale would require loosening those assumptions for every run, including
task runs, which is a worse outcome than a second runner.

The curation runner therefore reuses the *primitives* — `ROLE_SCOPE` confinement, the gate runner
from `config.py`, `FileHumanReviewGate`, and the evidence/session writers — but has its own node
sequence and its own unit of work.

### 5.2 Evidence

Each curation run writes a session record and an evidence manifest through the existing writers,
with `changed_files` listing the requirement and bundle files it touched.

Curation runs consequently become visible in the navigator built in Increments A and B:
`story --scope task:<id>` and `reverse --scope file:requirements/SR-086.md` both work on them, and
a bundle briefing's `implementation_summary` counts them. The V-cycle closes over the curation work
itself.

Note for whoever renders review evidence: `finalize._review_evidence` pops the raw `diff` and
`review_guide` from each archived review record and replaces them with blob refs named `patch` and
`guide`. A renderer must follow the blob ref; it cannot read them inline.

## 6. Failure handling

- A malformed requirement file is skipped with a recorded reason, never fatal to the run — the
  precedent set by `load_session_runs` and `bundles.list_bundles`.
- A proposal that fails the mechanical gate is returned to `propose` with the failure, up to the
  configured attempt limit, then escalates. It is never written.
- A human rejection at `review` is recorded with its annotations and returns to `propose`.
- `verify` failing — closure did not improve, or a previously legal item became pending — fails the
  run. Nothing is rolled back: the writes are already recorded decisions, and reversing them
  silently would be worse than reporting a regression.
- `check` exiting non-zero is the intended signal for CI and preflight, not an error.

## 7. Security

- No agent role may write `requirements/**` or `bundles/**` directly (§5).
- Reason strings and proposals reach files through the CLIs, which validate against the existing
  schemas before writing.
- `bundles/` and `requirements/` are already in `guide._FORBIDDEN_EXPORT_DIRS`, so a guide export
  can never write into them. That guard is retained.

## 8. Testing discipline

`pyproject.toml` sets `addopts = "-m unit"`. Integration commands must pass
`-m 'unit or integration'` or they collect nothing and exit green.

**Fixtures must be built through the real writers.** A requirement fixture is produced by
`factory-requirements new` plus `bind`; a bundle fixture by the bundle writer; a manifest by
`evidence.manifests.write_run_manifest`. A hand-rolled dict that resembles an artifact is what let
an earlier increment ship a query reading a storage layout no producer writes — its tests passed
because the fixtures encoded the same wrong assumption as the code.

The closure rule needs a test per state, including the two that are easy to conflate:
`measured-failing` must not read as `measured-passing`, and a `planned` requirement whose task is
`done` must be `pending`.

## 9. Increments

**Increment 1 — level the CLIs.** `bind`, `bind --reaffirm`, `defer`, `exempt`, `check` and `next`
for requirements; the optional-harness representation change (§3.3); fix `index` so it refuses to
launder staleness; the closure state model with its severity tiers, and its tests. No pipeline.
This unblocks binding work immediately and settles the vocabulary before it is baked into node
contracts.

**Increment 2 — bundles.** The bundle writer (`new`, `add`, `remove`), the member checksum, and
`check`/`next`/`status` for bundles.

**Increment 3 — the pipeline.** The curation runner, its nodes, roles and scopes, the human review
gate, and evidence recording.

Increment 1 is a prerequisite for 3: a pipeline needs a tool that owns the write.

## 10. Resolved questions

Both questions this design opened were settled on 2026-08-10:

- **Where a harness name comes from.** The workflow asks the human. No registry, no validation. An
  unnamed harness is left undefined and carries a `WARNING`; a named-but-unbuilt harness is work to
  be implemented alongside the system. See §3.3.
- **Batch or single decision.** A run may cover a batch. The review gate reviews the batch as a set
  with per-item annotations, and a rejection names the items it rejects. See §5.

## 11. Known gaps

- **`measured-failing` has no observed example.** No requirement in any repository has a failing
  validation result today, because only SR-001 is bound at all. The state is designed from the
  manifest schema and one observed passing entry. Whoever implements §3.1 must not fabricate a
  fixture that merely resembles a failing result — build it through the real writers, or record the
  state as unproven until a real failing run exists.
- **Trace has no unlink operation.** The drone's `SR-001 → BR-002` dangling upstream is deferred
  with the recorded reason that it cannot be removed. This design does not add one; a curation
  workflow that can decide but never undo is an accepted limitation of the first three increments.
