# SR-to-code and validation traceability implementation plan

**Spec:** [[docs/superpowers/specs/2026-08-31-sr-code-validation-traceability-design|SR code and validation traceability design]]  
**Feature:** [[FEAT-001]] REQ-TRACEABILITY  
**Related:** [[FEAT-007]] MEASURE-AUDIT, [[FEAT-014]] VALIDATION-GATES, [[FEAT-017]] PLANNING-BOOTSTRAP

## Goal

Make implementation-time trace maintenance a governed obligation. An implementation task must
update canonical SR relations to production symbols and validation test nodes, mirror them as
Obsidian wikilinks, and pass specialist structural and fidelity reviews before completion.

## Non-duplication boundary

- Extend [[SR-001]] for explicit implementation/validation relation navigation.
- Extend [[SR-049]] only where gate validation of produced-code declarations is needed.
- [[SR-050]] adds implementation-time relation maintenance and the per-SR structural/evidence/fidelity review contract.
- Reuse [[SR-004]] code-map indexing, [[SR-006]] pytest markers, and [[SR-023]] import-overlap audit.
- Keep coverage, integrity, and fidelity as independent review outputs under SR-050; do not duplicate the existing audit requirements as separate SRs.
- Do not add a second workflow to [[FEAT-017]]; bootstrap consumes the traceability gate.

## Work packages

### T1 — Relation schema and resolver

Add the canonical SR fields `implemented_by` and `verified_by` with path, optional symbol, and
optional pytest node ID. Validate project-relative paths, supported target syntax, and duplicate
relations. Add a resolver that returns stable artifact references and explicit missing states.

**Tests:** valid references, missing paths, outside-root paths, unresolved symbols, unresolved
pytest nodes, duplicate declarations, and non-pytest validation files.

### T2 — Obsidian mirror and writers

Add a deterministic writer used by implementation workflows to update typed SR fields and the
corresponding Markdown sections. Preserve unrelated prose and make repeated writes idempotent.
Render source paths/symbols and test paths/node IDs with `[[...]]` links.

**Tests:** first write, update, removal, ordering, idempotence, and preservation of existing SR
frontmatter/body content.

### T3 — Implementation workflow obligation

Require an implementation task that changes production or validation code to declare the affected
SRs and update their relations before completion. Keep task `satisfies` as the attribution edge;
the new SR relations identify the concrete implementation and validation artifacts.

**Tests:** missing relation blocks, complete relation passes, changed-but-unlinked finding, and
relation declarations reconciled to the task's SR set.

### T4 — Structural review agent

Implement a deterministic structural reviewer for missing, dangling, malformed, out-of-scope,
duplicate, and unaccounted relations. Register it as a blocking governed obligation. Reuse the
existing code map and evidence readers rather than scanning Git as an authority.

**Tests:** one fixture per finding class, including a changed file that has no SR link and a link
to a deleted test node.

### T5 — Fidelity review agent

Implement the specialist review contract and evidence packet. It should inspect SR statement,
design context, linked symbols, linked test nodes, import overlap, and test outcomes. Record
structured findings with confidence and citations. High-assurance unresolved findings block;
other unresolved findings escalate and remain visible.

**Tests:** supported link, overstated link, partial/understated link, incidental helper link,
and high-assurance versus normal disposition.

### T6 — Dossier and console projection

Extend the feature dossier with navigable production implementation and validation sections,
including relation status, review findings, and evidence reconciliation. Keep Python authoritative;
TypeScript only renders canonical payloads. Existing `implementation_files` remains as an
observed-evidence field and is not replaced silently.

**Tests:** payload compatibility, link rendering, missing-state rendering, and bounded lists.

### T7 — Gate and dogfood integration

Bind structural review to the applicable governed profiles and fidelity review to high-assurance
profiles. Run the feature traceability slice through direct execution and the FEAT-017 planning
handoff. Record before/after evidence for declared, changed, and validated artifacts.

**Tests:** gate ordering, fail-closed behavior, human escalation, and no silent downgrade.

## Verification commands

```bash
uv run python -m pytest tests/unit/trace -q
uv run python -m pytest tests/unit/system -q
uv run python -m pytest tests/unit/orchestrator -q
uv run ruff check src tests
uv run python -m coherence navigate health --json
uv run python -m coherence register check
```

Completion requires every work package to have tests, the structural and fidelity findings to be
machine-readable, and a representative implementation to show declared links reconciled against
actual source/test evidence.
