# Coherence — Release Strategy (Spec)

**Status:** spec
**Date:** 2026-08-24
**Supersedes:** `docs/2026-08-24-coherence-release-strategy-review.md` as the canonical release
strategy statement. The review draft is retained as an audit trail; this spec is the decided,
decision-ledger form.

**Why:** the review doc correctly identified the tension between the *job* goal and the
*adoption/standard* goal, then left its own pushbacks as open questions. This spec converts those
into decisions with open, re-visitable defaults, and maps each decision onto the Coherence
increment roadmap so the strategy is executable, not just argued.

**Companion docs:**
- `docs/2026-08-24-coherence-positioning-release.md` — the *why* / positioning brief (not superseded).
- `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md` — product architecture (§13 = progressive assurance).
- `docs/superpowers/plans/2026-08-20-coherence-programme-execution-map.md` — increment execution map (authoritative for sequencing).
- `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` — design of increment 2B (the standard artifact).

---

## 1. Purpose & scope

Define **what Coherence releases, in what order, to which audience, and under what licence**, as
decisions a plan can implement. This spec does **not** define product architecture (see the toolset
design), does not restate the marketing rationale in full (see the positioning brief), and does not
re-derive increment sequencing (see the programme execution map). It only commits the strategic
choices and binds them to the roadmap.

Two goals, in tension, both real:

- **(A-job) Show off work** → maximize job odds (embedded + CV + agentic, forward-looking,
  safety-adjacent). Served by a *small honest public artifact that shows the idea*.
- **(B-adoption) Drive adoption** → maximize the project living past the author. Served by a finished
  product *and* a patron that may never appear.

These are **orthogonal bets on different artifacts and different timelines**. They are not served by
one gated sequence; they are served by a *portfolio*. "Release" is the wrong unitary verb.

---

## 2. Decisions (decision ledger)

Each decision has an **open default** and a **revisit trigger**. A revisit trigger is the condition
under which the default is re-opened deliberately — not an escape hatch.

### D1 — Two bets, not one release
- **Default:** Release A (Proof of Position) and Release B (Product v0.1) are independent bets.
  They do **not** gate each other; each has its own gate and its own failure mode.
- **Revisit:** if new evidence shows they are actually coupled (e.g., a publisher demands the whole
  tool before anyone will look at the idea).

### D2 — A quality bar precedes Release A, not just B
- **Default:** the Release A proof-of-position demo is a *first public product moment* and must clear
  a **fresh-eyes sweep before it publishes**. Quality assurance is not deferred to Release B.
- **Why:** the artifact most likely to be tested first by a stranger is the proof-of-position demo.
  A broken first impression ("people test it and find it useless") poisons both bets.
- **Revisit:** none practical — this is a gate, not a trade.

### D3 — Dogfooding is the regression/validation gate, not the external-proof gate
- **Default:** self-dogfood **is** a strong and expected gate for catching regressions and validating new
  features/fixes on the project's own repo — it is the fastest, most familiar integration test the
  author has, and it is used as the end-to-end engineering validation pass (increment 6B). It is an
  *exercise/certification of correctness on a known surface*.
- **Default (continued):** self-dogfood is **not, on its own, the release proof of usefulness to a
stranger.** The Release-B proof of external value is an **external, non-author, non-project**
end-to-end run plus an **independent polish sweep** on the actual demo path.
- **Why the split:** dogfooding the project's own repo overwhelmingly tests *does it work on my
codebase, where I already know where to look* — the right tool for regressions. It is *recursive
confidence* only when used as the *sole* evidence that the tool is useful to someone else; its domain
(the author's repo) does not by itself generalize to a general assurance substrate. Keep both: dogfood
for correctness/regression, external run for independent usefulness.
- **Outcome in the roadmap:** increment **6B stays as the dogfood validation pass**, de-gated from
being the *release* proof; the external run is the Release-B proof gate.
- **Revisit:** if an external verification channel proves unavailable and an honest substitute with
real independence is found.

### D4 — Lead with the standard + trust layer, not the tool; the differentiator is *layered*
- **Default:** release as a **standard**, not as a tool. The candidate contract is the
  evidence / non-conformance record (`NC-*`, provenance-blocked disposition) as a thin, versioned,
  JSON-Schema contract plus reference implementation — MCP-scale.
- **The moat is layered — no single layer is the whole moat.**
  1. **Format** — copyable in a week (only adopted if it becomes the shared standard).
  2. **Substrate** — copyable in months by any big vendor.
  3. **Regulatory frame** (ISO 26262 / ASPICE-adjacent, anchored by a body/OEM) — genuinely defensible,
  but **contingent on a patron that a solo dev cannot manufacture** (see D5). Unsecured upside, not the spine.
  4. **Workflow-encoded interface** (the *interface a safety-conscious
  operator actually works in*: provenance-blocked refusal as a walkable decision, one judgment per
  step as a navigable model, the human-decides ergonomics) — the defensible layer a single actor can
  **work on today, compounding from dogfood.** This is the layer most likely to *be the honest
  craft-proof* of Release A and the "wow-a-stranger" of Release B, but it is still copyable by a
  platform team that hires one practitioner.
- **Therefore:** the defensible positioning is **not "the tool is the moat" and also not "only the
regulatory frame is the moat."** It is: *the adopt-safe contract (standard) as the anchor, the
workflow-encoded interface as the layer a solo actor can extend today, and the regulatory frame as
the contingent upside.* Commodity UI surfaces (sandboxing, cost tracking, generic polish) are not part
of any moat — a platform absorbs those first.
- **Revisit:** if a big model vendor ships an equivalent safety-reviewed workflow UX before the
workflow-encoded interface is established, re-assess whether the interface remains defensible or
should be ceded while the contract stays.
  the format, not a loss.
- **Revisit:** if a model vendor ships a comparable certified evidence frame first, re-evaluate the
  wedge's positioning (D4 default may shift to "cooperate/cede format, keep reference impl").

### D5 — The standard leg is contingent on a patron appearing
- **Default:** the adoption/standard bet is **conditional on a patron** (consortium / OEM /
  AUTOSAR-adjacent body). It is not "the market discovers me." The MCP precedent is *not* treated as
  transferable to a solo dev: MCP's engine was a dominant publisher + a protocol between
  mutually-interested parties, and the `NC-*` record is not a shared seam (its value accrues only to
  people who already chose to be audited).
- **Revisit:** if a patron appears, the standard bet graduates from contingent to primary; the job
  bet (Release A) remains independent.

### D6 — Open the standard unconditionally; open the tool through the first demo
- **Default:** the **standard** (the `NC-*` format) is open, no matter what — it is the only layer
  that can be adopted. The **tool** is open at least through Release A, so the impressive layer
  (the status/gate/inbox/mission-control loop) is the part a stranger runs first. There is **no
  closed commercial wedge at this stage**.
- **Why the wedge is on the wrong layer here:** closing mission-control (the "wow a stranger" layer)
  while opening the dull-necessary trust contract kneecaps the adoption display and guarantees a
  patron never sees the impressive bit.
- **Revisit:** only when there is real, concrete sales exposure. Until then the whole thing stays open.
- **Note:** the `docs/2026-08-23-pi-package-adoption.md` "package-private" sequencing is a *release
  sequencing artifact* ("until public distribution is approved"), not a product decision; it does not
  create license ambiguity for this spec.

---

## 3. Mapping to the increment roadmap

The execution map is authoritative for sequencing; this section only tags each increment by which
bet it serves and whether it is load-bearing for a release. **Shipped** = on `main` today.

| # | Name | Serves | Load-bearing? | Note |
|---|---|---|---|---|
| 0 | Evidence register | substrate | — | shipped |
| 1 | Agentic-IO / freshness foundation | substrate | — | shipped |
| 1B | Neutral substrate extraction | substrate | — | shipped |
| 1C | Codemap / KB signatures | substrate | — | shipped |
| 2 | Trace / register | substrate | — | shipped |
| 3 | Navigate / present / goals / sim | substrate | — | shipped |
| **2B** | **Progressive-assurance foundation (obligations, typed justification, `NC-*`)** | **standard (D4) + gates everything after** | **YES** | **shipped — the standard artifact itself; on `main`** |
| 2C | CI obligation consumer | standard / adoption | yes | shipped — on `main` |
| 3B | Obligation-aware views | standard + demo | yes (gates 4) | shipped — on `main` |
| 4 | Audit / measurement / observations | demo | yes (tangible loop) | shipped — on `main` (pred 1C, 2, 3B met) |
| 5 | Status / focus / dispatcher | demo | yes (loop) | shipped — on `main` (pred 3B, 4 met) |
| 6 | Gate / inbox / staleness | demo | yes (loop) | unbuilt; pred 5 |
| **6B** | **Thin vertical slice (dogfood)** | validation only | **NO (de-gated, D3)** | unbuilt — keep as E2E validation pass, not a release gate |
| 7 | Unified long-run surface / mission-control | demo (the "wow") | yes (Release B's wow) | unbuilt; pred 6 |
| **8** | **Artifact families (specs/courses/SR markers, KB scope)** | polish / coverage | **NO (cuttable)** | unbuilt — not load-bearing for A or B |

**Consequences:**

1. **Do not treat "land all increments" as a release gate.** That is the *"release the finished
   product"* conflation. Increment 8 is cuttable for both goals; 6B is de-gated by D3.
2. **Next step:** **6** (Gate / inbox / staleness). Increments 2B → 5 (the standard artifact,
   obligation-aware views, audit, and the status/focus/dispatcher loop) are all shipped on `main`;
   the remaining demo-loop work is 6 → 7, with 6B as the validation pass.
3. **Release B ships increments 2B → 2C/3B → 4 → 5 → 6 → 7** (with 6B as validation, 8 excluded).
   2B → 2C/3B → 4 → 5 are already on `main`; the remaining build is **6 → 7**.
4. **Sequencing** follows the programme execution map waves verbatim: serialize the substrate
   imports on the spine; run 2C/3B in parallel after 2B; 6B cuttable with 7/8.

---

## 4. Release definitions

### Release A — "Proof of Position" (now, independent of 4–8)
- Ships: the named story/essay on the deterministic split; a recorded demo of what already works
  (trace/register/navigate) expressed as a **behavioral contrast** ("here is a fake-easy agent; here
  is what provenance-blocked refusal does in the same situation"), **not** a feature tour; preview
  of the `NC-*` evidence/non-conformance contract.
- Gate: clears a **fresh-eyes sweep before publish** (D2). Does not depend on increments 4–8.
- Failure mode: nothing ships; the idea stays private and the job proof never exists.

### Release B — "Product v0.1" (after increments 2B–7 land)
- Ships: the complete status → gate → inbox → mission-control loop; the `NC-*` standard + reference
  impl open (D6); the safety-certified wedge positioning (D4).
- Gate: increments 2B → 2C/3B → 4 → 5 → 6 → 7 landed; **external non-author end-to-end run +
  independent polish sweep** (D3). Increment 8 excluded; 6B is validation only.
- Failure mode: the demo reads as skeletonware on the exact axis it claims to fix (a mid-refactor
  status/gate/inbox); the proof gate is self-referential dogfood rather than external.

---

## 5. Traceability

This spec is a strategy; it has no code acceptance criteria of its own. Its decisions bind to the
increment plans listed in §3 and to the execution map. Any future plan that ships Release A or B
SHALL cite this spec (spec link) and SHALL satisfy D1–D6. Re-opening a decision requires a
revisit trigger from §2, not a preference change.

*Not a roadmap. The roadmap is the programme execution map; this spec only commits the strategy and
binds it to that map.*
