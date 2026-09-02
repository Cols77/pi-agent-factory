# SR-to-code and validation traceability design

**Date:** 2026-08-31  
**Status:** design draft for implementation planning  
**Scope:** Coherence traceability, feature dossiers, implementation workflow, and review gates

## Decision summary

Implementation is incomplete until it updates the trace relations between the affected SRs and
the production and validation artifacts that implement and verify the change. Coherence keeps
machine-readable typed fields authoritative; the Markdown body mirrors those fields with
Obsidian wikilinks for human navigation.

The first implementation supports repository-relative file paths plus stable symbol and test
node identifiers. It does not use line numbers as identity.

## Existing requirements and non-duplication

This design modifies the scope of existing requirements rather than duplicating them:

- [[SR-001]] remains the lifecycle-navigation requirement and is clarified to include explicit
  production and validation relations.
- [[SR-004]] remains responsible for the code map and import edges; it is not a trace-declaration
  requirement.
- [[SR-006]] remains responsible for pytest SR markers.
- [[SR-023]] remains responsible for test/import overlap coverage.
- [[SR-030]] remains responsible for rendering the feature dossier.
- [[SR-049]] remains responsible for gate-validating produced-code traceability.
- [[SR-050]] adds implementation-time relation maintenance and the per-SR structural, evidence-integrity, and semantic-fidelity review contract.

FEAT-017 consumes this capability when its planning pipeline prepares a governed run; it does
not own or reimplement the traceability model.

## Canonical relation model

SR frontmatter carries stable artifact references:

```yaml
implemented_by:
  - path: src/coherence/navigate/feature.py
    symbol: coherence.navigate.feature:feature_context
verified_by:
  - path: tests/unit/system/test_feature.py
    test: tests/unit/system/test_feature.py::test_feature_context_contains_only_connected_recorded_facts
```

Rules:

1. `path` is repository-relative and must resolve inside the project.
2. `symbol` identifies a production definition where symbol indexing supports it.
3. `test` is an optional pytest node ID; file-only validation is allowed for non-pytest harnesses.
4. An SR may have multiple implementation and validation references.
5. Relations are updated by the implementation task, not reconstructed from Git after execution.
6. Evidence manifests remain observations: they reconcile declared links with changed files and
   executed tests but do not silently create declarations.
7. The Markdown body mirrors the same references:

```markdown
## Production implementation

- [[src/coherence/navigate/feature.py#coherence.navigate.feature:feature_context]]

## Validation

- [[tests/unit/system/test_feature.py#tests/unit/system/test_feature_context_contains_only_recorded_facts]]
```

The exact Obsidian heading/block syntax may be adapted to the supported editor, but the stable
path and symbol/test identity must remain present in the typed relation.

## Trace graph semantics

The graph gains explicit artifact targets:

```text
SR ──implements──> production file/symbol
SR ──verifies────> validation file/test node
Task ──satisfies─> SR
Run ──observes───> changed files and executed validation
```

Source and test artifacts are not requirements and must not be misclassified as SR nodes.
They are typed artifact references resolved by a dedicated artifact resolver/code map.

## Review agents

### Structural trace reviewer

Deterministically checks:

- relation schema and target syntax;
- path existence and project-scope confinement;
- symbol and test-node resolution;
- duplicate/conflicting declarations;
- missing production or validation links where the SR/profile requires them;
- changed production files and executed tests with no owning SR relation;
- declared links absent from the corresponding task/evidence scope.

Structural findings are blocking for governed work.

### Fidelity reviewer

Uses the SR statement, design records, code-map symbols/import edges, linked production code,
and linked validation nodes to judge whether the relation supports the claim. It reports:

- overstated links;
- links to incidental helpers rather than behavior owners;
- tests that cover only a weaker subset;
- code or tests that implement a different behavior;
- missing links needed to cover part of a compound SR.

For `high_assurance` work, unresolved fidelity findings block. Otherwise they escalate for
human disposition and remain visible in the run result.

### Evidence reconciliation reviewer

Compares declarations to manifests and validation output:

- declared and changed;
- declared but not changed;
- changed but undeclared;
- declared and executed;
- executed but unlinked;
- linked but stale or failed.

It never treats a changed file as proof that the SR relation was correctly declared.

## Workflow placement

The implementation task sequence becomes:

```text
read SR/design
  → implement production + validation code
  → update SR typed relations
  → mirror Obsidian links
  → run structural review
  → run fidelity review
  → execute gates
  → reconcile declarations with evidence
```

A task cannot be marked complete merely because tests pass. It must also leave the relation
review result and any accepted human disposition in the canonical artifacts.

## Out of scope

- inferring ownership solely from Git history or import reachability;
- replacing the existing code map or pytest marker mechanism;
- using line numbers as durable identity;
- allowing an LLM to silently approve an unresolved fidelity finding;
- making FEAT-017 responsible for traceability implementation.

## Acceptance intent

A governed implementation of a representative SR updates production-symbol and validation-test
relations, renders equivalent Obsidian links, rejects broken structural targets, detects changed
but unlinked files, and produces a fidelity review that distinguishes a supported claim from an
overstated one. Existing task/SR/evidence trace behavior remains compatible.
