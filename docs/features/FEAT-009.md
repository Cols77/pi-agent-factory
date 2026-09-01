---
id: FEAT-009
title: "HOST-ADAPTERS"
description: Host adapters expose the same authoritative Coherence contracts through different execution hosts.
requirements:
  - SR-027
  - SR-028
  - SR-047
---

# FEAT-009 — HOST-ADAPTERS

Status: declared feature dossier (Inc-9 health-resolution, decision-level register).

This feature registers **HOST-ADAPTERS** in the Coherence / pi-agent-factory feature set. It covers the host-neutral adapter railway: direct Pi and Claude Code execution, the Coherence MCP surface, and Hermes desktop/dashboard projections.


## Design boundary

Coherence's Python backend and canonical contracts remain authoritative. Hosts expose and
drive those contracts; they do not reimplement workflow interpretation, traceability,
validation gates, evidence provenance, or final run status.

The portable unit is the Coherence Run and its execution contract. A host may provide a
direct transport, or select an optional Hermes Kanban transport. The first Kanban scope is
Hermes-initiated durable execution; Pi and Claude Code retain full direct Coherence
execution and do not depend on Kanban.

The Hermes integration uses documented extension boundaries rather than a Hermes fork:
MCP for canonical tools, skills for routing and worker guidance, and desktop/dashboard
plugins for native views. Kanban is operational infrastructure behind the Hermes transport,
not a second Coherence authority.

## Related requirements

- [[SR-027]]
- [[SR-028]]
- [[SR-047]]
