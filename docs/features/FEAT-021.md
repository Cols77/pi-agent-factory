---
id: FEAT-021
title: "OPTIONAL-CONTRACT-ARTIFACTS"
description: Optional contract artifacts make declared interfaces first-class trace, bundle and freshness inputs while every project without a catalog keeps its current behaviour.
requirements:
  - SR-073
  - SR-074
  - SR-075
  - SR-076
---

# FEAT-021 — OPTIONAL-CONTRACT-ARTIFACTS

Status: authored feature dossier; SR-073–SR-076 were consented by the project owner in an
interactive session on 2026-09-17.

A project's contract artifacts — local JSON Schemas, fixtures, templates, DDL manifests and
protocol descriptions — are critical interfaces. Today a prose-spec/plan trace can be healthy
while a local JSON Schema `$ref` target, a fixture relationship, or a declared validator has
drifted. This feature lets a project declare exactly which artifacts it claims, and gives the
native tooling one reusable representation of that closure instead of a project-specific
manifest checker.

Source plan: `.hermes/plans/2026-09-17_135641-optional-contract-artifacts.md`.

## Initial intent

```text
.factory/contracts.yaml   (the project's own opt-in inventory)
    → schema-validated catalog model          [SR-073]
    → lexical + resolution path safety        [SR-074]
    → deterministic in-memory closure         [SR-075]
    → trace nodes / bundle members / freshness[SR-076]
```

The catalog contains identity, relationships and status only. Each contract file remains
authoritative for its own semantics, and the compiler reports syntax and reference closure
rather than domain meaning.

## Boundary with neighbouring features

- **FEAT-013 / FEAT-017 / FEAT-018** govern planning and governed execution. This feature adds
  an artifact family and consumes their existing freshness, trace and bundle machinery; it
  adds no new lifecycle stage and no new gate vocabulary.
- The compiler is deterministic and read-only. It never executes a project validator, fetches a
  remote schema, or materializes a second authoritative artifact.

## Scope of "compile"

Parse, validate, normalize, resolve safe local relationships, and hash. Explicitly not: code
generation, arbitrary protocol semantics, network retrieval, shelling out to validators, or a
materialized lock/closure file. Those remain deferred until an evidence-backed need exists.

## Command surface

No new top-level CLI group. Contract diagnostics surface through the existing `trace check`,
`navigate health`, `navigate freshness`, bundle/membership checks, and JSON status projections.
A narrowly scoped read-only view is added only if existing output cannot expose catalog entries
and compiler diagnostics clearly.

## Compatibility contract

- Absence of `.factory/contracts.yaml` is valid and produces no contract-specific findings.
- Presence of a catalog makes every declared entry authoritative and fail-closed: malformed
  declarations, duplicate ids or paths, unresolved relationships, unsafe paths and missing
  files are visible findings.
- Only local repository-relative paths and local `$ref` values are supported. Absolute paths,
  parent traversal, URLs and symlink/reparse-point escapes are rejected before resolution.
- No generic scan of JSON files. A project opts in by listing exact artifacts.
- Existing bundle member kinds and JSON outputs remain backward-compatible; `contract:<id>` is
  additive.
- Existing freshness fingerprint formats are reused. No parallel hashing, dependency-graph, or
  evidence subsystem.

## Out of scope

- inferring contracts from all JSON/YAML/TOML files;
- fetching remote schemas or resolving HTTP(S) `$ref` values;
- executing external schema compilers, code generators, or provider tools;
- a generic protocol compiler or semantic validator framework;
- a materialized lock/closure file;
- declaring a consumer contract "validated" from the compiler alone — validation remains an
  executed gate/evidence assertion;
- changing the behaviour of any project without a catalog.

## Initial acceptance intent

For a fixture project declaring a root schema with a local `$ref`, a fixture and a consumer, a
change to the referenced schema changes the root contract's compiled fingerprint without the
root file changing; the change propagates through contract findings to the declared consumer and
its recorded evidence. Invalid variants — an unsafe declared path, a missing `$ref`, a changed
transitive dependency — each produce their stable machine-readable code, and a project with no
catalog shows no new finding, no new invalidation and no changed existing output.
