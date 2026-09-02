---
id: progressive-review-decision-presentation-seed
title: "Progressive review-decision presentation — seed"
status: seed
---

# Progressive review-decision presentation — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-056]]) discovered during the FEAT-001 first-vertical-slice run
> ([[2026-09-01-feat001-reference-run]]), so the requirement has a real source anchor. It is
> deliberately minimal. The full design — packet schema, per-surface rendering, how it composes
> with [[FEAT-017]] PLANNING-BOOTSTRAP's own authoring-consent step — waits for FEAT-017 to land,
> because that is the mechanism that will actually exercise this requirement at scale and is the
> right place to plan it against real bootstrap traffic rather than one hand-run slice.

## What the run found

FEAT-001's authoring-consent walkthrough (T-4b) was conducted by hand, in a chat session, one SR
at a time: source excerpt, derived acceptance criteria, any recorded source/code disagreement,
then a real accept/reject/defer from a human. [[SR-044]] already requires that no bulk approval
happen and that a human decide explicitly — but nothing specifies *how* the material a human needs
to decide attentively gets assembled and presented. That gap was filled ad hoc, once, by an agent
composing the packet by hand from the register, the acceptance criteria, and the ledger. It should
not stay ad hoc: the same packet is needed for every future authoring-consent (`sr:`) and
verification-review (`review:`) decision, on every surface a human might be using —
an interactive coding-agent session (what was actually used), the browser console
([[FEAT-010]] COHERENCE-CONSOLE), and Obsidian (a read-only projection per D-P7).

## Why this is one SR under FEAT-010, not a new FEAT

[[SR-029]] already establishes the pattern this generalizes: "one canonical interactive console
... rendered by Pi and Hermes as thin skins over the same canonical source." The content differs
(a decision packet rather than health/dossier/teach), but the architecture is the same one
FEAT-010 already owns: **one canonical projection, computed from disk, thin-rendered per surface.**
A new FEAT would duplicate that ownership rather than extend it. If FEAT-017's landing reveals the
packet needs its own lifecycle (versioning, packet-level freshness, a queue distinct from the
console's other projections) independent of FEAT-010's rendering concern, splitting it out then is
cheap — decision-grain SRs don't require FEAT reassignment to move, only a re-filed owner.

## What the eventual SR should specify (not committed here)

- A deterministic function from one pending gate item (`sr:SR-###` or `review:SR-###`) to a single
  review packet: the item's source excerpt, its derived acceptance criteria or diff, any recorded
  source/code disagreement, and its decision history — computed from disk on every read, per
  [[SR-045]]'s pattern for the inbox.
- Presentation one item at a time, never as a bulk list a human can rubber-stamp past.
- The same packet content rendered identically by every surface — no surface re-derives it.
