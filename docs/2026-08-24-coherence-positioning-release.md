# Coherence — Positioning & Release Strategy Brief

> **Status:** working draft · **Date:** 2026-08-24
> **Purpose:** capture the strategic discussion core outcome in one place. Not a spec, not a
> roadmap. This is the *why*, *who for*, and *how to present* — the marketing/positioning layer
> that the technical plans (esp. `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md`)
> deliberately do not cover.
>
> Brand: the product is **Coherence** (D1 of the toolset design). The repo name
> `pi-agent-factory` is the source name; the released/marketed identity is Coherence.

---

## 1. What the product actually is

Coherence is a **named assurance toolset for continuous system understanding**, built on one
load-bearing doctrine:

> **Code enumerates, holds state, proves on disk and verifies; the model makes exactly one
> judgement per step.**

The value is *not* "AI writes code". It is: **an agentic coding substrate where every claim is
backed by on-disk evidence, provenance, freshness, and a durable, auditable trail — the agent
proposes, the substrate proves, a human decides.**

Key capabilities that express this (non-exhaustive, see the toolset design):
- Provenance-preserving references (`ArtifactRef`/`SnapshotRef`) and typed `ObservationEnvelope`s —
  durable state and time-bound results are never conflated.
- A freshness compiler/resolver with four resolution classes, incl. **provenance-blocked**
  (missing evidence can never be auto-invented).
- One gate protocol, one findings inbox computed from disk, no LLM narration in the navigator.
- A safety-adjacent spine: typed `justification`, `NC-*` non-conformance records, an
  11-dimension health vector, suspect-edge STRICT-no-auto-`valid`.

## 2. The adversarial environment (why this is the right wager)

- AI lets anyone build and copy ideas. **Ideas are infinitely forkable.**
- But the one thing AI cannot cheaply mass-produce is **earned trust**. Verifiable, auditable,
  accountable engineering is the non-commodity in a world where everything else looks AI-authored.
- The bigger risk is **platform absorption**: if model vendors bake
  verifiability/traceability/audit into the *model or agent itself*, a standalone tool gets
  absorbed. Compete on *standard / trust*, not tool-vs-tool.

## 3. The honest threat to this position

The deterministic split is **necessary, not sufficient.** It is a *wedge*, not automatically a moat:
- The **idea** ("deterministic split") is a paragraph; it will be copied.
- The real partial-moat is the **earned invariants**: hard-to-reverse, and more importantly
  *truthful* engineering (provenance-blocked refusal, no-auto-valid) — hard to fake and
  especially valuable in safety-critical/audit domains.
- A vendor **can** train a model on ISO-26262/ASPICE/AUTOSAR and beat a human on
  *knowing the standard*. Do **not** bet on compliance *knowledge* — that layer is
  commoditizable. Bet on the **auditable evidence trail**, which fine-tuning cannot fake.

## 4. The strategic direction (working thesis)

Adoption, not tool-led competition:
1. **The product is a guardrail/proof layer that other agents declare compliance with** — a
   *proof* layer, not the whole toolset.
2. **Standardize ONE thin interchange contract, not the architecture.** The candidate is the
   **evidence / non-conformance record** (`NC-*`, provenance-blocked disposition) as a
   versioned, minimal JSON-Schema contract + reference implementation — MCP-scale, not
   whole-architecture scale.
3. **Anchor in the safety-certified wedge** (automotive: ISO 26262 / ASPICE-adjacent — "an agent
   can't prove it built this correctly" is a hard blocker today).
4. **Seek a governance patron** (consortium / OEM / standards body e.g. AUTOSAR-adjacent), not solo
   discovery. Publish the format openly, then sponsor it.

## 4. Why a standard can actually win (MCP as precedent)

MCP became a standard **not because its spec was best**, but because of adoption economics:
a dominant platform (Anthropic) published a **universal, non-competitive connector** layer that
everyone benefits from, MIT/Open, with a reference implementation, and rivals adopted it rather
than cede the ecosystem. **Lesson:** standards win on *who publishes + ubiquity of shared
value*, not spec quality. A solo dev lacks that distribution — so the realistic route is a
**patron**, not "the market discovers me."

## 5. Release framing — the bet summarized

- **Enemy / failure-mode:** "An AI said it's done" / "fake confidence in agentic coding."
- **Promise:** "The repository where the agent proposes and the substrate proves — and never lets
  a model alone call it done."
- **Naming:** release as **Coherence** (D1). Open the trust layer to become the *reference
  implementation* of the evidence/non-conformance contract.

## 6. Open/closed decision factors (not yet decided — see release follow-up)

Open-source is *strongly* indicated for the trust/substrate layer: in this product, openness is a
compliance-signal, adoption channel, and the way to become a standard. But what exactly opens, under
which license, must be decided deliberately (see `docs/` for the package-private sequencing caveat;
that is a *sequencing* artifact, not a product decision).

## 7. Dual-persona goal

There are two goals in tension and both matter:

- **(a) Show off work** → maximize job odds (embedded + CV + agentic engineering, forward-looking).
- **(b) Drive adoption** → maximize the project living beyond me (get uptake, a patron, a standard).

The framing below splits **bag** the open-standard play (matters to potential employers who value
forward-looking **safety-adjacent infra**) from **hold back the whole-substrate play** (matters
once there's a real commercial/spec risk). See `release-plan` draft notes for reconciliation.

---

*Draft — awaiting release-planning deep-dive. The sharpest correction this doc makes: **don't
lead with the tool; lead with the standard + the safety-attested trust layer.** Ideas are cheap;
earned, auditable trust in agentic output is the scarce good.* CV-flow