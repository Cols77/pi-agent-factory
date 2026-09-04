---
id: commit-claim-traceability
title: "Commit-claim traceability — design"
status: design
---

# Commit-claim traceability — design

**Date:** 2026-09-04
**Scope:** Git commit trailers as an SR-attribution input to the evidence store, the commit-time
check that enforces them, the reconciliation they sharpen, the gate they bind, and the fidelity
packet they narrow.

## Decision summary

A commit records one fact nothing else in the system holds: **which requirement the work was done
in service of.** Everything else a traceability review needs — which files changed, which symbols
they contain, whether a path is production or validation — is already derivable from the diff, the
code map, and the requirement's own frontmatter. So a commit trailer declares intent attribution
and nothing more:

```
SR: SR-050, SR-023
```

Commits are an **input consumed at a checkpoint**, never a durable ledger. Any
`coherence register review` or `full` gate run ingests the commit range since the newest manifest
and writes what it learned into an evidence manifest; from that moment the manifest is
authoritative and the commits themselves no longer matter. Squashing or rebasing before ingestion
is harmless because nothing depended on the commits yet; rewriting after ingestion cannot lose
anything, because the manifest retains the per-commit detail. **No workflow needs to be
forbidden.**

## Existing requirements and non-duplication

This design implements an existing requirement and sharpens two others; it introduces no new
requirement.

* [[SR-049]] ("Produced-code traceability validated by gates") is currently `proposed` and unbound.
  Its statement — that artifacts a slice produces carry canonical relations to their owning SR,
  gate-validated, so a slice is not healthy unless its links are complete — is a description of
  this mechanism. **This design gives SR-049 its first binding and acceptance criteria.**
* [[SR-050]]/AC-2's deterministic reviewers gain a correct denominator (see *Reconciliation*).
  No new finding taxonomy, no third reviewer, no change to AC-2's own criterion text.
* [[SR-050]]/AC-4's fidelity packet gains claim facts, narrowing the judge's search space (see
  *Fidelity packet*). AC-4 stays `kind: manual` — nothing here makes a judgement call mechanical.
* [[SR-048]] (CI as a compiled obligation consumer) supplies the CI half for free: a new blocking
  gate command in `.factory/factory.yaml` is picked up by construction, with no CI wiring of its
  own.
* [[SR-023]] (requirement coverage audit) is untouched. Its import-overlap mechanism remains the
  answer to "what does this change reach", which is a different question from "what was this
  change *for*".

### This does not overturn "never scan git as an authority"

`coherence.register.review.unaccounted_changed_files` reads changed files from evidence manifests
and documents the constraint explicitly: *"never from `git diff`/`git log`, per the source plan's
explicit 'reuse... evidence readers rather than scanning Git as an authority' instruction"*
(`src/coherence/register/review.py`).

That constraint is preserved exactly. **No reviewer reads git.** Git is consumed once, at
ingestion, into the manifest; every reviewer continues to read only manifests, through the same
readers it uses today. Git becomes an input to the evidence store, never an authority the review
layer consults.

## The trailer

A standard git trailer, so `git interpret-trailers` parses it and it matches the trailer
convention already in this repository's commit messages:

```
SR: SR-050, SR-023
```

Multi-SR commits need no special case. Ingestion attributes the commit's whole file set to *each*
named SR, and the reconciliation then reports, per SR, which of those files that SR actually
declares. A file legitimately shared by two requirements is declared by both; a file claimed for
an SR that declares no relation to it is a finding against that SR specifically.

The trailer never names files, symbols, or relation kinds:

* **Symbols are derivable.** `coherence.register.relations._resolve_symbol` requires a declared
  symbol's dotted module to equal `_module_from_path(rel_path)`, so a changed file plus the code
  map (`substrate.codemap.build.file_signatures`) enumerates every candidate symbol. A trailer
  restating them would duplicate the index.
* **Relation kind is derivable from path.** `src/**` is `implemented_by`, `tests/**` is
  `verified_by`; `_module_from_path` already strips the leading `src` segment, and the test layout
  is uniformly `tests/unit/<pkg>/test_*.py`.
* **Per-file relation triples would duplicate the requirement.** `requirements/SR-050.md`'s
  `implemented_by:` block is the canonical declaration site. Restating it in commit messages
  creates two hand-authored copies of one fact, which drift.

## Commit-time check

A versioned `commit-msg` hook at `.githooks/commit-msg`, enabled by
`git config core.hooksPath .githooks`. At `commit-msg` time the change is staged, so
`git diff --cached --name-only` yields the paths. The hook checks three cheap things, with no code
map involved:

1. every staged path matches an exemption glob → pass, no trailer required;
2. otherwise a `SR:` trailer is present;
3. every id it names exists in the register (`requirements/SR-*.md`).

**The hook is fast feedback, not the enforcement.** Hooks are per-clone and never cloned with the
repository, and `--no-verify` bypasses them by design. Enforcement lives at ingestion time, where
commits already exist and nothing can be skipped. To keep the hook from being silently absent, the
`full` gate asserts `core.hooksPath` is set — a missing hook becomes a gate failure rather than an
invisible gap on one machine.

## Configuration

One file, `.factory/trace-claims.yaml`, following the precedent of `.factory/profile.yaml`:

```yaml
epoch: <commit-sha>          # no claim expected before this commit
exempt:                      # path globs whose changes never require a trailer
  - "docs/**"
  - "evidence/**"
  - "**/*.md"
```

### Exemptions must be auditable

A path-scoped exemption list is frictionless, which is also its failure mode: it grows silently
until it covers everything inconvenient, and nothing shows that it happened. So the reconciliation
emits an **`exempted`** result carrying the count of changed files skipped and the glob that
skipped each. List creep becomes a number in every review rather than an absence.

### The epoch is load-bearing

Without it the first run is unusable. No historical commit carries a trailer, so on day one every
declared relation across the register would report as never-claimed — a wall of false findings, and
the mechanism switched off within the hour. Claim-based findings therefore fire only for files
touched after the epoch commit; anything earlier falls back to today's manifest-scoped behaviour.

## Ingestion

Triggered by any `coherence register review` or `full` gate run, before reviewing. A `--no-ingest`
flag preserves genuinely read-only inspection.

**Range:** the newest manifest's `result_commit` to `HEAD`. Self-healing — a missed checkpoint only
makes the next range longer, and gaps close themselves without intervention. When that
`result_commit` is not an ancestor of `HEAD` (a branch switch, or history rewritten after the
manifest was written), there is no meaningful range: ingestion reports the divergence and ingests
nothing rather than guessing a merge base. The manifest already holds its own tree digest, so the
divergence is detectable rather than silent.

**One manifest per ingestion run.** Ingestion writes a *new* manifest with its own `run_id`; it
never mutates an existing one. Manifests are immutable records — the authority the checkpoint model
rests on — and re-ingesting an already-covered range produces nothing rather than rewriting
history in the evidence store.

**Per commit it records:** sha, subject, the trailer's SR ids, the changed paths, and which paths
were exemption-matched together with the matching glob.

**Schema.** `src/substrate/schemas/evidence_manifest.schema.json` sets
`additionalProperties: false`, so this requires an explicit new property: an **optional top-level
`commits` array**. Optional means no `schema_version` bump and no migration — manifests written
before this change simply lack the field, and every existing reader keeps working.

Keeping per-commit granularity *inside the manifest* is what makes history rewriting a non-issue.
Once ingested, the commit-level detail lives in an immutable record; git may later lose it to a
squash without the coherence system losing anything.

### An ingestion manifest has no task, and the schema currently requires one

The manifest schema requires `task_id` matching `^T-[0-9]+$` and an `inputs.task` block carrying a
real file's path and sha256. Both encode an assumption this design breaks: that every manifest
originates in an orchestrated task. Ingestion triggered by a gate or review run has no task brief.

The resolution is to make `task_id` and `inputs.task` **optional** in schema v2 — additive, and
backward compatible because every manifest written so far carries both. The alternative,
synthesising a task id and a plausible `inputs.task` digest, would fabricate provenance for work
that had none, which is precisely the failure this system exists to prevent. When ingestion *does*
run inside an orchestrated task, it records that task exactly as today.

**Backward compatibility.** Ingestion also populates the existing
`implementation.changed_files` with the union of the commits' paths, so
`unaccounted_changed_files` and `evidence_reconciliation_review` continue to work untouched — they
simply receive better input.

**Idempotency and atomicity.** Writes are keyed on commit sha, so re-ingesting a range is a no-op,
and use the tmp-file-then-`Path.replace()` pattern `coherence.audit.runner._write_status` and
`write_verdict_atomically` already establish, so a concurrent reader never observes a partial
manifest.

### CI ingests without persisting

Evidence manifests are tracked files. Auto-ingest therefore splits by context:

* **Locally**, ingestion writes a manifest that someone commits. That commit touches `evidence/**`,
  which is exemption-listed, so it needs no trailer and the recursion terminates.
* **In CI**, the gate writes a manifest into a throwaway checkout that nobody commits. CI's review
  is still correct — it ingested the real commit range — but its manifest evaporates.

This is accepted deliberately. Ingestion is idempotent, so nothing breaks; the consequence is that
**CI validates against a record it does not persist**, and the durable evidence store stays only as
complete as local and orchestrated runs make it. The alternatives — CI committing to the
repository, or an evidence store outside git — are worse.

## Reconciliation

`coherence.register.review.evidence_reconciliation_review` already partitions declared-vs-changed
and declared-vs-executed facts into six categories (`declared_and_changed`,
`declared_but_not_changed`, `changed_but_undeclared`, `declared_and_executed`,
`executed_but_unlinked`, `linked_but_stale_or_failed`), and its own docstrings name the weak point:
scoping "changed" to manifests that happen to carry a validation entry for the SR is a documented
judgement call, not a precise denominator.

**Claims do not add a taxonomy. They re-base the existing one onto a denominator that is correct.**
Per SR there are now two clean sets — CLAIMED (files from commits whose trailer names it) and
DECLARED (its `implemented_by`/`verified_by` paths) — and the existing categories fall out of the
set arithmetic with the heuristic removed:

* `changed_but_undeclared` stops meaning "changed in some manifest that happened to validate this
  SR" and starts meaning **"a commit explicitly claimed SR-050 and touched this file, which SR-050
  declares no relation to."** Same category; blame now attached.
* `declared_but_not_changed` becomes "this SR declares a relation to a path no commit claiming it
  ever touched" — post-epoch only.
* The register-wide `unaccounted` finding stays for genuinely orphan files and shrinks to the files
  no commit claimed at all, which is what it always meant to express. Its documented
  blamelessness — *"an unaccounted file or test has, by definition, no single owning SR to attach
  the finding to"* — remains true of exactly that residue, and stops being true of everything else.

## Gate

This binds [[SR-049]]. Every part of the check is deterministic set arithmetic over git facts and
frontmatter, so its acceptance criteria are all `kind: test_marker`.

**Requiredness.** The fidelity `--check` precedent blocks only under `high_assurance`, correctly,
because it gates a model's judgement. Claim reconciliation has no judge in the loop, so it
**blocks under every compiled profile** (`prototype` and `high_assurance`). The epoch, not the
profile, is what keeps it quiet.

**Wiring.** One command in `.factory/factory.yaml`'s `full` gate, alongside
`coherence mirrors check` and `coherence register review --fidelity --check`. By [[SR-048]], CI
extends automatically; no CI-specific work is required.

## Fidelity packet

`coherence.register.fidelity_packet.build_fidelity_packet` currently composes the SR's statement,
acceptance criteria, design-source excerpt, resolved relations with signatures and bounded source,
import-overlap facts, and validation outcomes. It has no knowledge of what work was actually done —
only what the requirement claims about itself.

Adding claim facts ("SR-050 was claimed by commits A, B, C touching X, Y, Z; X and Y are declared,
Z is not") changes the judge's question from *"do these declared links look plausible?"* to *"does
the work that was actually done match what this requirement says about itself?"* — better posed,
and answerable against a concrete diff rather than an open-ended reading of the codebase.

**This is the scaling property.** The judge examines one SR's claimed diff, whose size does not
grow with the register. Going from 60 requirements to 600 leaves per-SR judge cost flat.

**Claims are claims, never facts.** A trailer is an assertion by whoever wrote the commit, and a
false claim is precisely the `different_behavior` finding the judge exists to catch.
`coherence.register.fidelity_findings.build_finding` already cross-checks a candidate finding's
relation against the packet's own resolved entries so a hallucinated citation cannot become a
finding; claim facts carry the same discipline — usable as evidence of *intent*, never as proof of
*correctness*.

## Testing

Repository convention: TDD, `@pytest.mark.sr("SR-049")` markers, one fixture per result class.

The one genuinely new cost is that ingestion needs git, so it needs a fixture building a temporary
repository with real commits: trailers present and absent, multi-SR trailers, exemption-matching
paths, pre- and post-epoch commits, and **a squash performed after ingestion**, proving the
manifest survives history rewriting. That last fixture is the load-bearing test of the
manifest-checkpoint model this design rests on.

## Out of scope

* Forbidding, guarding, or detecting history rewriting. The manifest-checkpoint model makes it
  unnecessary.
* Per-file or per-symbol trailers. Symbols come from the code map; relation kind comes from path.
* Making [[SR-050]]/AC-4 mechanical. Fidelity judgement stays a model/human call by nature.
* Generalising `human_review` requiredness across profiles — that is [[SR-059]]'s own scope.
* A standalone coverage-overlap CLI surface for [[SR-023]].

## Acceptance intent

[[SR-049]] gains `test_marker` acceptance criteria covering: a well-formed trailer parsed and
attributed to every named SR; a commit with only exemption-matching paths requiring no trailer; an
unknown SR id rejected; a claimed-but-undeclared path reported against the claiming SR; a
post-epoch declared-but-unclaimed path reported and a pre-epoch one not; exemption counts reported
with their globs; ingestion idempotent across repeated runs; and the gate exiting non-zero under
both compiled profiles on an open claim finding.

## Work packages

Mirrors the [[SR-050]] slice's T1–T5 decomposition, and is the same size:

1. **T1** — trailer parsing, `.factory/trace-claims.yaml` config, `.githooks/commit-msg`, and the
   `core.hooksPath` gate assertion.
2. **T2** — ingestion: commit-range walk and divergence handling, the schema changes (optional
   `commits`, optional `task_id`/`inputs.task`), `changed_files` back-population, idempotency and
   atomic writes.
3. **T3** — reconciliation re-based onto the claim denominator, epoch handling, `exempted`
   reporting.
4. **T4** — [[SR-049]] binding, acceptance criteria, and the `full` gate command.
5. **T5** — fidelity packet claim facts.
