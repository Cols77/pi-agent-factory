# Coherence Programme Execution Map

This map coordinates the implementation plans without weakening their individual acceptance
criteria. A label of “parallel” means independent production changes with disjoint file
ownership after the listed prerequisite has landed; research, test-fixture preparation, or
documentation work alone does not qualify.

**Amended 2026-08-22** — progressive assurance (obligations, typed justification/lifecycle
relationships, `NC-*` records, health vector, CI, suspect-link review). See
`2026-08-22-coherence-progressive-assurance-design.md` for the full design. Increments 0–3 are
verified shipped on `main` and are not reopened; the delta the source planning guide assigned
to increments 0/1/2/3 lands instead as new increments 2B, 2C and 3B. Increments 4–8 gain their
assigned delta in place, since none has been built yet. A new increment 6B is inserted after 6
for the thin vertical slice (dogfood).

## Plan Set

| Plan | Purpose | Mandatory predecessor |
|---|---|---|
| 2026-08-20-coherence-increment-0-evidence-register.md | Correct evidence-state audit and bootstrap the register | none |
| 2026-08-20-coherence-increment-1-agentic-io-freshness-foundation.md | Artifact/snapshot/observation/projection contracts and guarded code-map refresh | Increment 0 |
| 2026-08-20-coherence-increment-1b-neutral-substrate-extraction.md | Complete safe neutral substrate extraction and compatibility adapters | Increment 1 foundation |
| 2026-08-20-coherence-increment-1c-codemap-kb-signatures.md | Unified code-map import edges, KB migration, and TN-14 gate signatures | Increment 1B |
| 2026-08-20-coherence-increment-2-trace-register.md | Migrate trace/register and add unlink | Increment 1C |
| 2026-08-20-coherence-increment-3-navigate-presentation-goals-simulation.md | Migrate navigation, presentation, goals, and simulation | Increment 2 |
| 2026-08-22-coherence-increment-2b-progressive-assurance-foundation.md | Evidence-correctness fix, obligation compiler, mandatory manifests, typed justification/relationships, NC-* records | Increment 2 |
| 2026-08-22-coherence-increment-2c-ci-obligation-consumer.md | CI workflow driven off the compiled obligation set | Increment 2B |
| 2026-08-22-coherence-increment-3b-obligation-aware-views.md | Obligation-aware navigator/presentation/goals/simulation, effective-profile projections | Increment 2B and Increment 3 |
| 2026-08-20-coherence-increment-4-audit-measurement-observations.md | Migrate audit/measurement and connect domain observation adapters; gains profile-aware verification-contract validation and policy-bound auto-rerun | Increment 1C, Increment 2, Increment 3B |
| 2026-08-20-coherence-increment-5-status-focus-dispatcher.md | Status, focus, explain, TUI and using-coherence routing; health becomes the applicable-obligation vector | Increments 3B and 4 |
| 2026-08-20-coherence-increment-6-gate-inbox-staleness.md | Decision protocol, computed inbox, deferrals and stale-item routing; gains requiredness and suspect-edge review | Increment 5 |
| 2026-08-22-coherence-increment-6b-thin-vertical-slice.md | Dogfood: T-031 and one requirement-delivery task through the full spine under prototype/high_assurance | Increment 6 |
| 2026-08-20-coherence-increment-7-unified-long-run-surface.md | Unified status/mission-control protocol; gains profile-controlled rerun/cost display | Increment 6 |
| 2026-08-20-coherence-increment-8-artifact-families.md | Specs, courses, SR test markers, and KB symbol scope; gains profile-aware test markers | Increment 1C and Increment 2; TN-15 additionally needs Increment 4 codemap cutover |

## Conservative Execution Waves

    0 --> 1 foundation --> 1B --> 1C --> 2 --> 3 --> 2B --> 5 --> 6 --> 7
                                                       |            |     ^
                                                       +--> 2C      +--> 4 -+
                                                       +--> 3B ----------^
                                                                    6 --> 6B
                               2 --> 8A (spec/course/SR markers)
                               4 --> 8B (KB symbol scope)

The serial spine protects public imports and ensures every consumer sees one stable substrate
contract. Increment 2B is the new pinch point after 3: it supplies the Obligation contract
every later increment (2C, 3B, 4, 5, 6, 6B) consumes. 2C and 3B may run in parallel once 2B
lands — 2C needs only the Obligation contract, 3B needs it plus already-shipped Increment 3.
Increment 4 production execution follows Increment 3B (its obligation-aware canonical paths are
inputs); only its isolated fixture research may overlap. Increment 8A can execute in parallel
with Increment 3 after Increment 2; its final TN-15 subtask waits for Increment 4’s code-map
overlap cutover. Increment 6B needs 2B, 4, 5 and 6 but not 7 or 8, so it is mutually cuttable
with 7 and 8, the same property those two already had with each other.

## Intra-plan Parallel Work

| Plan | Parallel units after its contract checkpoint | Must remain serial |
|---|---|---|
| 0 | Manual-record contract and register fixture preparation | Evidence-state propagation follows the record contract; register commit follows its fixture |
| 1 foundation | Artifact/snapshot contracts and observation/projection contracts | Freshness extraction before recipe guard; code-map adapter after guard |
| 1B | Paths/schemas/schema validation; ledger/plan parser; config declaration extraction; agents inversion; evidence read model | Validator/agent dependency inversion before integrating callers; final shims/import-cycle check |
| 1C | Codemap relocation/import edges and KB relocation | Structured gate result before TN-14 runner wiring; import-edge codemap before audit cutover |
| 2 | Trace parser/read-model migration and register migration | The trace/system ADR cycle is broken before their public CLI integration; unlink after graph/write model moves |
| 3 | Goals, presentation, simulation can have isolated regression work | Their move plus system-to-navigate integration is one atomic consumer cutover |
| 4 | Measurement adapters and audit adapter fixtures | Unified codemap import edges before audit overlap; deterministic report assembly after parallel SR results |
| 5 | Read-only probe implementations, focus storage, and TUI formatting | Dispatcher integration waits for stable status sources; compatibility aliases are last |
| 6 | Individual inbox-source adapters and decision-file validation | Shared gate protocol precedes coverage/doctor adoption; expiry routing follows writer integration |
| 7 | Python status-protocol fixture and TypeScript renderer fixture | Final mission-control integration waits for the protocol and gate/inbox sources |
| 8 | Spec, course, and pytest-marker checks | KB symbol scope waits for import edges and audited code-map snapshots |

## Shared-file Ownership Rule

Only one implementation worker owns a file at a time. In particular:

- compatibility shims and package entry points are owned by the migration task that moves their
  canonical module;
- factory.orchestrator.runner and gate-result types belong to Increment 1B until TN-14 is
  complete;
- factory.system’s coordinated move is owned by Increment 3;
- coverage report assembly is owned by Increment 4;
- pi-ext mission-control integration is owned by Increment 7.

Each plan’s final verification runs after all parallel units in that plan have been integrated.
No cross-plan parallel work may land by bypassing its predecessor’s compatibility checks.
