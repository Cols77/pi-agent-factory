# Coherence plan first-class requirement authoring

## Problem

The Coherence planning lifecycle correctly projects `author-requirements` as the
first action for a newly started run whose requirement evidence is missing. The
project-local `$coherence-plan` host adapter currently permits only
`author-spec`, `author-plan`, `review-spec`, and `review-plan` to enter its
bounded author/review loop. As a result, a fresh run reports the correct next
stage but cannot progress through the stage that creates its initial
requirements.

For FEAT-019 this is especially visible: the feature dossier explicitly has no
SRs yet and says that requirements are pending human-approved authoring.

## Decision

Make `author-requirements` a first-class authoring stage in the
`coherence-plan` workflow. When the latest validated projection declares that
exact action, the host may author provisional requirement candidates or
revisions using the feature request and bounded repository context.

Requirement authoring must remain distinct from requirement approval:

- authored requirements are provisional candidates, not adopted canonical
  requirements;
- the host must not grant consent, accept warnings, or claim human validation;
- the host must not invoke `record-sr-consent` without an explicit human
  decision for each candidate SR;
- after writing the candidates, the host must write a complete artifact
  manifest with fresh SHA-256 values and re-query legal actions;
- the expected next stage is `record-sr-consent`, where the workflow stops for
  human decisions.

## Scope and write boundary

The authoring operation may create or revise only requirement artifacts that
are in scope for the named feature. It must preserve unrelated dirty worktree
changes and must not alter the feature dossier, spec, plan, bundle, intent
journal, consent records, gates, handoff, or downstream execution state as a
side effect of requirement drafting. Existing SR revisions must be presented
as revisions, with their changed content visible to the human before consent.

If the feature request and available context do not support a concrete
requirement, the host must stop and ask for clarification rather than invent a
requirement. It may produce multiple candidate SRs when the scope requires
them, but each candidate remains independently consented and hash-bound.

## Evidence and lifecycle behavior

The host must follow this sequence:

1. Read the latest schema-2 legal-actions projection.
2. Confirm that it declares exactly `author-requirements` and that the run is
   not blocked.
3. Inspect the feature dossier and relevant bounded context.
4. Draft the smallest complete provisional requirement set.
5. Validate and write the requirement artifacts through the repository's
   existing requirement writer.
6. Write the complete current artifact manifest through the governed Coherence
   producer, including fresh hashes.
7. Re-run the legal-actions helper.
8. Report the candidates, changed files, evidence, and the resulting next
   action; stop before consent.

Every state-changing operation must be followed by a fresh projection. A
source mutation invalidates dependent evidence and must be handled by its
existing producers rather than by hand-editing planning state or reports.

## Alternatives considered

### Keep the current display-only boundary

This preserves the narrow adapter contract but leaves every new planning run
stalled at its first lifecycle stage. It contradicts the backend's ordered
workflow and requires a separate, undocumented host path for the normal first
step.

### Add `author-requirements` without extra safeguards

This would unblock the run but risks treating generated text as adopted
requirements, overwriting unrelated SRs, or allowing the workflow to continue
without per-SR human consent. It is rejected.

### Recommended: provisional authoring followed by a consent boundary

This aligns the host with the backend lifecycle while preserving the existing
human-authority boundary. It makes the first stage executable, retains
hash-bound evidence, and leaves approval/adoption entirely explicit.

## Testing

Add contract tests that require `author-requirements` in the executable stage
set while continuing to reject consent, gates, handoff, and downstream actions
as automatic transitions. Add an integration-style workflow test that starts a
run, authors provisional requirement artifacts, writes the manifest, verifies
the next projection is `record-sr-consent`, and proves no consent record is
created automatically. Cover missing context, existing-SR revision scope, and
fresh-hash manifest behavior.

## Non-goals

This change does not grant SR consent, adopt requirements, change Coherence's
projector, alter requirement semantics, launch downstream work, execute
planning gates, create a handoff, merge, or push.
