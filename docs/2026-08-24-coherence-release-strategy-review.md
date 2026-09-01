# Coherence — Release Strategy (for critical review)

> **Status:** superseded by spec · **Date:** 2026-08-24.
> **The decisions in this review are now canonical in
> `docs/superpowers/specs/2026-08-24-coherence-release-strategy.md` (D1–D6, §2).** This draft is
> retained as the audit trail of the reasoning; it is no longer the authoritative statement.
> **Revision history:** this draft was reviewed, then converted from a positioning essay into a
> decision ledger, then absorbed into the spec.
> **Audience:** Claude (or another critical reviewer). The goal of this doc is to be
> **pressure-tested**, not to be agreed with. Please attack the assumptions, not the prose.
>
> Companion docs:
> - `docs/2026-08-24-coherence-positioning-release.md` — the positioning brief (the *why*).
> - `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md` — the product architecture.
> - `docs/superpowers/plans/2026-08-20-coherence-programme-execution-map.md` — increment status.
>
> Product: **Coherence** — an assurance toolset for continuous system understanding, built on the
> doctrine *"the model makes exactly one judgement per step; code enumerates, holds state, proves
> on disk and verifies."* The repo name is `pi-agent-factory`; the marketed identity is Coherence.

---

## 1. The two goals in tension

1. **Show off work → maximize job odds.** I am an embedded-software / computer-vision / agentic
   engineer at Bosch moving toward Melbourne. The project is strong evidence I am a forward-looking,
   safety-adjacent, coding-agent-power-user. I want employers to see it.
2. **Drive adoption → maximize the project living past me.** I want the project to get uptake,
   ideally become a *standard / contract* other agent pipelines conform to.

**My claim:** these are not in conflict *if sequenced* — but they optimize for different things and
cannot both be served by one monolithic "release." I propose splitting into **Release A**
(positioning/proof, now) and **Release B** (product/demo v1.0, after increments land).

---

## 2. Ground truth about where the project is (verified on `main`)

> **Status note (2026-08-25):** this section was written 2026-08-24 and is a *historical snapshot*,
> retained as the audit trail of the reasoning. It is **not** current. As of 2026-08-25 increments
> **2B, 2C, 3B, 4 and 5 are all shipped on `main`** (obligation compiler/CI/views, audit/measurement,
> and `coherence.{status, focus, explain, router}` plus the 11-dimension health vector). Increments
> **6, 6B, 7, 8 remain unbuilt**. The authoritative, current status is `docs/superpowers/specs/
> 2026-08-24-coherence-release-strategy.md` §3. Do not rely on the "Not yet built" list below.

Shipped / on `main`:
- `coherence.{trace, register, doctor, navigate, presentation, goals, simulation}` — incremental
  **0, 1, 1B, 1C, 2, 3** (the "shipped and unchanged" set).

Not yet built:
- `coherence.{audit, measurement, status, gate, inbox, focus, explain, runs}` — incremental **4–8**
  plus progressive-assurance **2B/2C/3B/6B**. The source directories do not exist yet.

**Consequence I want reviewed:** the *product as a tangible whole* — the "status → gate → inbox →
mission-control" loop (increments 5–7) — does **not exist yet**. So asking "how do I release the
product" today is asking how to release something that is still several increments away.

---

## 3. The proposal: a *portfolio* of two bets, only loosely sequenced — not one binary release

> **Revision note:** the earlier draft framed these as two *gated, sequenced releases*. The review
> pushed back: the two goals are **orthogonal bets on different artifacts and different timelines**, not
> sequential gates. The job proof is best served by a small, honest, public artifact showing the
> *idea*; the adoption/standard bet needs a finished product *and* a patron that may never appear. So
> Release A and Release B do **not** gate each other — each has its own gate and its own failure
> mode. "Release" is the wrong unitary verb.

### Release A — "Proof of Position" (NOW, independent of 4–8)
**Purpose:** job-showcase + adoption seed. Low project-cost.
**Quality bar:** this is a *first product moment*, not a warm-up. The proof-of-position demo is the
one most likely to be tested by a stranger first — so it must clear a **fresh-eyes sweep before it
publishes**. Quality assurance is *not* something that only gates Release B. This is the direct
answer to the reviewer's worry: "people test it and find it useless."
- A **named story / essay** on the deterministic split — "the agent proposes, the substrate proves."
- A **recorded demo** of what already works (trace/register/navigate), showing the credibility asset
  that *already exists* in 0–3: provenance-blocked refusal, no-LLM-narration, deterministic.
- Introduce the **opinion/standard idea**: a thin *evidence / non-conformance record* contract, in
  preview (not yet standardized).

**Why now:** the credibility asset does not require 4–8. Delaying Release A solely for
"everything perfect" conflates *"release the finished product"* with *"release the proof of
position"*. The proof already exists.
**What A is NOT:** a recorded demo that is a feature tour (trace/register/navigate) — a stranger
will read that as skeletonware. The demo must be a **behavioral contrast**, not a feature tour:
"here is a fake-easy agent, and here is what provenance-blocked refusal does in the same
situation." The deterministic-split denial is a *story* tellable without a full product.

**Release B — "Product v0.1" (AFTER increments 4–7 land)**
**Purpose:** a *demonstrable complete loop*, not just proof. This is the true "once all increments
are implemented" moment.
**Gate:** 4–7 (audit/status/gate/inbox/mission-control) — the moment the tool is repeatedly
impressive to a stranger. Increment 8 (artifact families: specs/courses/tests) is cuttable and not
load-bearing; 6B dogfood must be replaced by an external proof (see §4).

**Why gated:** This release *presents the tool*, which must not look unfinished on the very axis it
claims to fix (status/gate/inbox). A mid-refactor skeleton would *undermine* the "not-fake-confidence"
position.

---

## 4. The dogfood problem (the strongest pushback on the draft)

The draft made "6B dogfood" the *end-to-end proof* gating Release B. That is **unvalid as a proof**, for two reasons that must be separated:

**1. Self-dogfood is recursive confidence.** The factory dogfoods the project it built itself, on its
own doctrine, its own repo/history, by its own designers. That is the *least independent* test a
stranger can run. Showing "it works on my own repo" is almost trivially true — the tool was shaped
against exactly that codebase. It says nothing about a stranger's task, stack, or repository. For a
product whose thesis is "fake confidence is the enemy," a self-referential dogfood-as-proof is
dangerously close to the failure mode it claims to fight.

**2. Dogfood domain ≠ claim domain.** The claim is a general assurance substrate; the dogfood domain
is one special case (the author's repo). Success there generalizes nowhere a stranger can trust. The
proof must come from an **external, non-author, non-project** run — a real embedded/CV/agentic task
the tool had no prior shape for — or at minimum an external-aligned repo.

**3. Separate exercise from certification.** The phrase "we'll catch quality by dogfooding" puts the
quality gate *inside* the thing measured. The gate must be an **independent fresh-eyes sweep** on the
actual demo path, plus that external test. Dogfood exercises; it does not certify.

**Decision: Release B's proof gate = an external run + independent polish sweep, never self-dogfood
alone.** This is the reviewer's "quality or people find it useless" concern, turned into a gate.

---

## 5. The sharp correction: don't lead with the tool — lead with the standard + trust layer

**Assumption to review:**
- Ideas are infinitely forkable in the AI era. The *scarce* good is **earned trust**.
- A model vendor can **learn** ISO-26262/ASPICE/AUTOSAR and beat a human on *knowing the standard*.
  Do **not** bet on compliance knowledge — it's commoditizable.
- Bet on the **auditable evidence trail** — intervening fine-tuning cannot fake *this particular
  artifact's* provenance.
- Therefore: **release as a standard, not as the tool.** The candidate contract = the
  **evidence / non-conformance record** (`NC-*`, provenance-blocked disposition) as a thin,
  versioned, JSON-Schema contract + reference implementation — MCP-scale, not architecture-scale.

**Why a standard can win (MCP precedent — and its limit):**
MCP won because a dominant platform (Anthropic) published a **universal, non-competitive**
connector, MIT-Open, with a reference impl, and rivals adopted it rather than cede the ecosystem.
Standards win on **who publishes + ubiquity of shared value**, not spec quality.
**Handicap I concede — and which weakens the MCP analogy:** a solo dev lacks distribution. MCP's
engine was a dominant publisher + a protocol that sits between mutually-interested parties. The NC
evidence record is not a shared seam — its value only accrues to people who *already chose to be
audited*. So the correct conclusion is not "standards can win," it is "**a patron can win, only if
one appears.**" That is a much weaker, contingent claim, and the standard leg is explicitly marked
**contingent on a patron materializing** (consortium / OEM / AUTOSAR-adjacent body), not "the market
discovers me."

**What the differentiator actually is (landed):** the *format* (a JSON-Schema `NC-*` record) is
copyable in a week, and the *substrate* is copyable in months by any big vendor. Neither is a moat.
The defensible thing is the **safety-certified regulatory frame** (ISO 26262 / ASPICE-adjacent)
anchored by a body or OEM. If that patron never appears, the "unabsorbable" differentiator does not
appear either. Plan for a small, generic, vendor-printable wedge + reference implementation, so a big
vendor cooperating with a safety body is a *win* for the format, not a loss.

---

## 6. Open / closed decision (factors)

Open-source is *strongly* indicated for the **trust/substrate** layer — openness is a
compliance-signal and the adoption channel. **But exactly what opens, under which license, and
whether the experience (mission-control/status) is kept as a commercial wedge** is not yet settled.
The package-private sequencing note in `docs/2026-08-23-pi-package-adoption.md` is a *release*
sequencing artifact ("until public distribution is approved"), **not** a product decision.

**Reviewer pushback on the wedge layer:** the open-core line is *on the wrong layer.* From a
standard-adoption view, the trust contract is the *dull-necessary* layer, and the "wow a stranger"
layer is exactly the mission-control/status loop a demo needs. Closing mission-control both kneecaps
the adoption display and guarantees a patron, when one appears, never sees the impressive bit.

**Decision (open; default = whole thing open at least through first demo):** open the **standard**
(the `NC-*` format) no matter what — it is the only layer that can be adopted. Open the **tool** at
least through Release A so the impressive layer is the part a stranger runs first. Revisit
the closed-commercial-wedge question only when there is real sales exposure, which there is not yet.

---

## 7. Explicit questions I still want attacked (now with defaults)

1. **Is two-bets the right frame?** Are these truly orthogonal, or do I just *want* them sequential?
   (Default: orthogonal; job artifact is its own bet.)
2. **Is "standard first" realistic for a solo dev / small project** vs platform absorption? The
   doc's own MCP comparison concedes the solo dev lacks distribution — and that concession weakens
the standard-wins claim. **Default:** the standard leg is contingent on a patron appearing; it is
not assumed viable.
3. **Should the compliance-knowledge *not* be bet?** Is it truly commoditizable, and is the
"prove it against my artifact, on disk" also copyable once a big vendor ships equivalent
evidence? **Default:** the format and substrate are copyable; only the safety-certified frame
is defensible, and only with a patron.
4. **What is the *actual* differentiator a big platform cannot copy?** If they ship audit +
   trace right tomorrow, does my deterministic-evidence layer get absorbed, or is there a causal /
   safety-regulatory gap they won't ship? **Default:** the honest answer is *the regulatory wedge*,
   not the tool — plan for a vendor-printable wedge + reference impl.
5. **Job-after-the-project tension**: does any of this actually *serve the job goal*? In practice
   employers care about "an open project with 3 PRs / 2 adopters", not "it's a standard I proposed"
   — so Release A's *job artifact* is what the job leg should optimise, not the standard.

---

## 8. The anomaly, and the pushback I want
- My whole thread has oscillated: first "open-source now," then "private/course, never," then
  "open-core standard." That oscillation is itself a signal — **I lean by inertia.** The most
  consistent pull-away was the reviewer's basic worry: "people test it and find it useless." That
  worry is correct — but it is *not* an argument for nothing being released. It is an argument for
  **external proofs and a quality gate on Release A too**, which is exactly the correction adopted
  in sections 3 and 4.
- Hardest thing to say honestly: the job goal and the adoption goal may actually **not** be in one
  release sequence — the job-proof is best served by a *small, honest, public* artifact that shows
  the *idea*; the adoption/standard goal needs a *perfection of the product* + a patron that may
  not appear. So a "release strategy" may actually be a *portfolio* of independent, differently
  sequenced bets, and "release" is the wrong unitary verb.

---

*Reviewed draft. Not a specification. The sharper my assumptions are exposed, the better — this
revision converts the doubts into decisions with open, re-visitable defaults.*