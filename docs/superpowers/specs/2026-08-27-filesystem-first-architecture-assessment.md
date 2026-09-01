# Filesystem-First Architecture Assessment (GYST-CORE reference)

_Date: 2026-08-27. Status: analysis + recommendation. For integration into the Inc-09
features/plans (a decision, not yet a locked change)._

**Thesis under scrutiny:**
> Durable project knowledge should primarily live as structured, human-readable,
> version-controlled files in the repository. Graphs/databases/indexes should be *derived*
> where possible and reserved for relationships, impact analysis, state transitions,
> traceability queries, and evidence freshness.

**Reference (architecture only, not a product analogue):** `RaphGonz/GYST-CORE` — a
filesystem-driven pipeline: plain markdown files as durable truth, a `CONTEXT.md` run order
living "nowhere else," numbered stages, per-stage contracts, Git for history, **no
database/state machine** — just files + a wizard reading them. Its ordering insight is
*render/projection vs. source*: the source is files; everything coordinating is either a
contract in a file or a pure reader.

**Grounding (what I actually read from this repo before writing):**
- `src/substrate/kb/index.py` — `kb/index.json` is a **derived** summary built from
  `kb-*.md` frontmatter (`build_index`). Rebuildable.
- `src/substrate/codemap/imports.py` — the codemap import index is **explicitly a
  write-through side-artifact**: "`build_import_closure` always recomputes from source; a
  missing or stale edges file never changes the answer." Fingerprint-keyed (sha256).
- `src/coherence/trace/graph.py` — `build_graph(root)` **reconstructs the graph on every
  call** from files (`load_nodes` + `extract_edges` + `find_gaps`). Not a stored DB.
- `src/coherence/staleness.py`, `inbox.py` — **pure reads**: "strictly read-only … never
  writes, never executes a resolver"; compose sources (coverage gates, deferrals, stale
  register bindings, suspect edges) from on-disk files.
- `src/coherence/runs/store.py` — `RunSource` protocol is **read-only**; adapters expose no
  writer; `coherence.runs.service` is the only assembler.
- `src/factory/orchestrator/{nodes,backends,runner}.py` — evidence via `EvidenceContext+Connector`,
  `finalize_run_evidence`, `write_run_manifest`, git_ops; gates via a `ConfigGateRunner` over
  `.factory/factory.yaml`; `AgentBackend` protocol as the host seam.
- On-disk inventory: `requirements/*.md` + `index.json` (derived), `kb-*.md` + `kb/index.json`
  (derived), `.factory/code-index/*.json` (sha256 cache), `sessions/*.session.json` (run
  transcripts/state), `coverage-reviews/` — all JSON+markdown, **no sqlite/ORM/graphlib anywhere.**

---

## 1. Headline verdict

**The architecture is already ~80% filesystem-first — and the hypothesis is *more true*
than a first read suggests.** It is not over-engineered as a *database* (there is no
database and no substantive graph store to justify). Where it *is* over-engineered, the cost
is in **persisted derivative state and orchestration ceremony**, not in the durable-knowledge
layer. The right move is **not a simplification that removes graphs** (the graph is already
derived and cheap), but a **consolidation of derivation + a hard "files canonic, derived
regenerable" discipline** — made explicit and central, exactly in the direction GYST-CORE
pushes.

### What this means for the hypothesis, point by point

| The split | Status in this repo | Action |
|---|---|---|
| **files = canonical meaning** | ✅ largely true (`requirements/*.md`, `kb-*.md`, `docs/`, `*design.md`) | Keep. Make it the explicit stated invariant. |
| **Git = history** | ✅ true (run transcripts to `sessions/`, code commits) | Keep. |
| **structured metadata = machine semantics** | ⚠️ true but **proliferated** (`index.json` × several, `status.json`, `session.json`, `factory.yaml`, `code-index/*.json`) | **Consolidate.** Fewer, well-named derived indexes. |
| **graph/index = derived relationships & queries** | ✅ **already true** — `build_graph` recomputes each call; codemap index is a fingertr教 write-through cache | Keep; state it as a hard rule. |
| **runtime state = ephemeral orchestration** | ⚠️ mixed — `sessions/*.session.json`, `.factory-*.json` persist run state that is arguably **ephemeral-orchestration-adjacent** but written durably | **Clarify the boundary.** These are *records of orchestration*, legitimately durable as history/evidence — but they must not be *counted on as reconstruction inputs*. |
| **UI/Obsidian = projection** | ⚠️ partial — the console/Navigator are projections, but some "surfaces" are being built as if they owned state | Make every console/dossier/teach surface a **pure projection of `coherence ... --json`** (already the thin-adapter goal). |

---

## 2. What could be simplified / replaced by repository-native files

These are the concrete simplification opportunities (low-to-medium risk, each in the
GYST-CORE direction: files = meaning, index = derived, git = history):

1. **`kb/index.json` (derived) is fine but should be an explicit *generated artifact*.** It
   already is (`build_index`); the only change is to treat it as *regenerable-by-command
   `coherence register ...`/`kb`* and **never hand-edited**. No DB — already correct.

2. **`requirements/index.json` (derived register) — same.** Keep `requirements/*.md` as
   canonical; index is a projection. Already so; *document it*.

3. **Duplicate/derivative `status.json` surfaces.** `sessions/.factory-status.json`,
   `.factory-review-surface.json`, `.factory-run.log` are **projection caches**. They are safe
   to treat as disposable (rebuild from source) — GREATER risk is if any workflow *consumes*
   them as if they were canonical. **Recommendation:** mark them as `derived/`; invert any
   workflow that reads them to read the source instead. This matches the GYST-CORE "one source
   of truth (files), readers derive" idea and kills a whole class of drift bugs.

4. **`code-index/*.json` (sha256-cached import/symbol index)** — already rebuilt from source
   on fingerprint mismatch. This is the *cheapest and most correct* cache to keep; it's not
   over-engineered — it is a **correct derived cache with an explicit staleness rule.** Keep.

5. **`documents/ADRs` + trace graph.** `load_adrs` → `_adr_nodes` → `build_graph` reads these
   files. The graph is derived; ADR markdown is canonical. Keep; no change.

6. **Config/contract files (`factory.yaml`, policy compiler).** These are the *right*
   filesystem-first artifacts — declarative gates as YAML, not DB rows. Keep and point to.

```
What is ALREADY correct (files-first, keep):
  requirements/*.md  kb-*.md  docs/**  factory.yaml  ADRs  run logs (history)

What should become explicitly "derived, regenerable, never hand-edited":
  requirements/index.json  kb/index.json  status.json  review-surface.json
  code-index/*.json  any coverage-reviews/status.json (read)  run transcripts

What is the real "must stay structured/explicit" core (a genuine graph/query need):
  traceability relationships (trace graph), obligations/compiler, freshness kernel,
  evidence/manifest model, human-review DecisionFile, NC-* nonconformance record.
```

---

## 3. What genuinely requires explicit structured state / graph semantics / a database

**Answer: very little needs a *database*, and none of it exists today as one.** Honest
catalog of what *needs* explicit structure (all filesystem-representable, so keep as files):

- **The trace graph + gaps** — relationships between SR/spec/task/code/obligation. Needs
  *graph semantics* (edges, reachability — `build_graph`, `find_gaps`), but **must stay
  derived** (you already do this). No DB; a fresh graph per query is correct at this scale.
- **Obligation compiler (`policy/compiler.py`)** — the *machine semantics* of requiredness
  (`not_applicable|advisory|required|blocking`). This is genuine structured semantic logic —
  keep as deterministic Python over declarative YAML config.
- **Freshness kernel (`substrate/freshness`)** — checksum/staleness rules. This is the
  **consistency authority** that decides what's *derived-and-stale* vs *canonical*. Keep.
- **Evidence / manifest model (`factory/evidence`)** — runs, manifests, `ObservationEnvelope`.
  This is **the one genuinely stateful, append-only, non-derivable layer**: you cannot
  reconstruct "what tests ran and passed when" purely from source. It is *history/evidence*,
  not graph. Files (manifests) are the right store; **never collapse into a graph**.
- **Human review / NC-* / gating decisions** — `DecisionFile`, `NC-*`, coverage-review
  status. These are **authoritative records** (a human said yes/no). Must be durable files
  with provenance, not derived.

**The only thing I'd archete** *as* a DB — and it's a *projection*, not a store — is a
**derived read-model / indexes** for the *queries* the console/dossier/teach run hardest on
(impact analysis, "which SRs does this task cover", "what changed since X"). SQLite or an
in-memory graph over the derived graph is **appropriate as a build-cache**, NOT as canonical
state. GYST-CORE's lesson applies: the DB serves *queries*, files serve *truth*.

---

## 4. Rebuildability (the crux) — how much survives a deleted index/graph

This is the strongest proof the architecture is already filesystem-first correct:

**If every `index.json` + the codemap cache + the trace graph were deleted:**
- **Fully rebuildable, deterministically, from repo files:** the trace graph
  (`build_graph` re-reads `requirements/*.md`, docs, ADRs, codemap), the KB index
  (`kb-*.md` frontmatter), the register index (`requirements/*.md`), the import/symbol
  index (`*.py` AST). **~unbounded fraction — these are pure functions of the repo.**
- **Rebuildable only approximately / from evidence:** the *manifests* and *run records*
  (evidence) are the exception — they are *append-only facts* ("this gate ran, exit 0, on
  commit X, at T"). You cannot re-derive *that it happened*; you can only re-run. But this is
  **intentional** — they are *evidence/history*, not indexes. Losing them loses *provenance*,
  not *meaning*.
- **The most precious (non-derivable):** human `DecisionFile`s, `NC-*` closure records, gate
  run manifests. These should be **git-committed deliberately** (like GYST-CORE commits its
  six markdown outputs). If *they* are lost, rebuilds can only *re-run*, not *re-attest*.

**Conclusion:** the rebuildability test passes strongly — **the derived layer is fully
re-hydratable from files, and the non-derived layer (evidence/decisions) is exactly and
only the layer that *should* be durable+versioned.** This is the correct split, and it
validates the hypothesis rather than challenging it.

---

## 5. Challenge / failure modes / where the current architecture is SUPERIOR

I want to push back on an over-eager "files-only" reading, because there are real places
the current design beats a naive GYST-CORE filesystem analog:

1. **Graph-queries need an index eventually (scale).** At pi-agent-factory's scale (one
   project, ~160 artifacts) deriving the graph per query is trivially fine. But coherence
   targets *consumer repos* (PAAD) with **183+ SRs, 66 tasks, 183 suspect edges**. Across
   many projects, a *per-query re-derivation* of the full graph + coverage + freshness could
   get slow. A **derived indexed read-model** (SQLite/serialized graph, rebuilt on fingerprint
   change) is the *correct* scalability answer — and it must be *explicitly a cache*, exactly
   as `code-index/` already is. Do NOT jettison the index concept; formalize it as cache.
2. **Message/token cost.** A pure "read every file + recompute" loop makes an agent reparse
   everything each context-gather. The **fingerprinted derived index is what makes context
   cheap** (fresh check = 1 checksum). Removing it would hurt, not help.
3. **Evidence provenance is not filesystem-trivial.** GYST-CORE writes six markdown files;
   that's enough for a sprint. Coherence's *evidence* ("what actually validated this claim")
   needs **structured, append-only, immutable, provenance-linked records** that plain
   human-authored markdown would corrupt (someone edits the "passed" line and history lies).
   The current **hash/fingerprint + exact manifest** model is a *strength* — don't regress it.
4. **Deterministic gating.** The "no-self-cert, evidence-gated" guarantee requires the
   *machine semantics* (obligations, freshness, gates) to be **code-authored and
   recomputed**, not markdown-asserted. A pure-discussion-files approach would let an agent
   "declare" greens — the thing HLR-04 forbids.

**So the challenge verdict:** the hypothesis is *directionally right and already mostly
honored*, and a *naive over-simplification* (treat everything as human-editable markdown,
drop the fingerprint/evidence model) **would be a regression** — it would break the
determinism + provenance guarantees that are coherence's differentiator. **Over-engineering
is not in "having a graph"** (there isn't a real one); it is in **scattered derived JSON +
ceremony**, which is exactly what to trim.

---

## 6. Concrete target architecture (recommended)

Adopt the split **explicitly**, as a named contract in the coherence docs (mirror GYST-CORE's
"CONTEXT.md says where things live"):

```
LAYER A — CANONICAL (versioned files, human-meaning; the source of truth)
  requirements/*.md   kb-*.md   docs/superpowers/**   factory.yaml + policy YAML
  ADRs(sp: docs)      DecisionFiles (human reviews/NC)   evidence manifests (append-only)

LAYER B — DERIVED (regenerable from A; NEVER hand-edited; fingerprints)
  requirements/index.json   kb/index.json   status.json   review-surface.json
  code-index/*.json   trace graph (on-query)   read-models for console/dossier/teach

LAYER C — RUNTIME/EPHEMERAL (orchestration only, disposable)
  sessions/*.factory-transcripts   .factory-run.log   in-flight run state
  (These are *records of orchestration*; keep as history but never as reconstruction input.)

LAYER D — PROJECTION (UI surfaces read LAYER B canonical JSON; never own state)
  Coherence console / dossier / teach / Pi nav / MCP / Obsidian
```

**One structural rule state it plainly:** *files = canonical truth; Git = history;
fingerprinted derived indexes = regenerable machine semantics; runtime state = ephemeral;
UI = pure projection. CEV re-derives everything not in Layer A; only evidence/decisions
(which are *history*) are immutable durables.*

**The matching increment change:** in the console/dossier slice plans (already faithful to
thin-adapter), add an explicit **"derived, never canonical" contract** for the aggregate
endpoints + a **fingerprint-gated rebuild** so persistence never becomes a drift source.

---

## 7. Smallest incremental changes (no disruption to planned increments)

These are safe, additive, and align with what's already built — none require removing the
deterministic backend or the graph:

1. **Add a `docs/superpowers/specs/2026-08-27-filesystem-first-contract.md`** that codifies
   the 4-layer split above as the architecture's stated invariant (like GYST-CORE's
   CONTEXT.md ordering). **This is the single highest-value, lowest-cost action** — it turns a
   latent *implied* design into an *explicit* one.
2. **Mark the derived artifacts as such** (a `# derived — generated by <cmd>, do not edit`
   header in each `index.json`, or a `.gitattributes`/`derived/` convention), so neither agents
   nor humans hand-edit them.
3. **Ensure every console/dossier/teach surface is a pure projection** (already the planned
   thin-adapter) and state that each endpoint is a *derived read-model*, not a store.
4. **Fingerprint-gate the derived rebuild** (already true for code-index; extend the same
   checksum discipline to `requirements/index.json` + `kb/index.json`).
5. **Fold the contract into FEAT-10 (Console), FEAT-13 (Governed Exec), and the
   health-resolution plan** as a one-para "storage treaty" so new surfaces respect
   files=canonical / derived=regenerable.
6. **Keep the evidence/freshness/obligation kernel in Python** (unchanged) — it *is* the
   machine-semantics layer, and its determinism is the product's differentiator.

---

## 8. Recommendation / opinion

**Yes — integrate it, but as a *contract + consolidation*, not as a rewrite toward "files
only."** My honest opinion:

- The **hypothesis is essentially already the architecture's design** — this repo has no
  database, derives its graphs/indexes from files, and fingerprints caches. The analysis is
  worth *writing down* and *enforcing*, because it (a) prevents future over-engineering, (b)
  makes the rebuildability guarantee explicit (killer feature for any consumer trusting
  coherence), and (c) aligns console/dossier/FEAT-13 with an unambiguous storage treaty.
- **What NOT to do:** rip out the evidence/provenance/fingerprint model or the derived graph
  in favor of "just human readable files." That would forfeit the deterministic, no-self-cert
  guarantee — coherence would become a markdown notes app with extra steps.
- **What to do:** codify Layer A–D; keep fingerprints/evidence; consolidate scattered derived
  JSON; make every new surface a pure projection. **Smallest sequence:** contract doc → derived
  markers → fold into FEAT-10/13 + health-resolution → fingerprint-gate rebuilds.

This is low-risk, reversible, and strengthens the product's central claim (rebuildable,
evidence-backed, filesystem-canonical) without sacrificing provenance or determinism.

_Status: proposed analysis; if you approve, I'll (a) write the contract spec, (b) add
"derived — do not edit" markers, and (c) add the storage-treaty note to the console/dossier/
health + FEAT-13 docs. No execution/push._