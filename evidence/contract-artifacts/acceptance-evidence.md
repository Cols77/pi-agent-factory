# Optional Contract Artifacts — Acceptance Criteria Evidence

Feature: **FEAT-021 — OPTIONAL-CONTRACT-ARTIFACTS** (SR-073..SR-076)
Plan: `.hermes/plans/2026-09-17_135641-optional-contract-artifacts.md`
Implementation branch: `feat/optional-contract-artifacts` (worktree `C:/coding/pi-agent-factory-wt/optional-contract-artifacts`)
Pre-change baseline: `04c8833`

## Commit lineage (all on one branch, single-author)

| Task | Commit | Subject |
|---|---|---|
| T1 | `fa90386` | SR-073..076 + FEAT-021 dossier + bundle + per-SR consent records |
| T2 | `c0dfc0c` + `e603a5e` | catalog schema + pure model (+ status-required spec fix from review) |
| T3 | `e7fad13` | lexical path safety + catalog loading |
| T4 | `21f84d1` + `2873648` | deterministic compilation (+ $ref-base fix from independent probe) |
| T5 | `185ea87` | contract nodes + typed edges in trace |
| T6 | `22cdda3` | contract bundle members + coverage |
| T7 | `52180f45` | freshness propagation + six CONTRACT_* codes |
| T8 | `89042967` + `4e447e06` | CLI diagnostics + docs |
| T9 | `effc1825` | e2e fixture project + acceptance sequence |
| L1 | `1f1648fc` | layer-review fix: reject relationships to undeclared ids |
| L2 | `d3784d19` | rename compiler test to unique basename (collection fix) |

## Method

Each task: a **dev** subagent (TDD, RED→GREEN, scoped commit) then **independent** verification — my own throwaway probes plus a fresh **broad reviewer** per task, twice over the whole feature as a **layer reviewer** (returned BLOCKED on one Important finding, which was then fixed and re-verified: `1f1648fc`). The final unit campaign ran from a **fresh process** at a pinned revision.

## Acceptance-criteria evidence

### SR-073 — Opt-in contract artifact catalog
- **AC-1** absent `.factory/contracts.yaml` → `present=False`, 0 declarations, 0 diagnostics (additive/no findings); present-but-malformed/unparseable → `CONTRACT_CATALOG_INVALID`; duplicate id → `CONTRACT_DECLARATION_DUPLICATE_ID`; duplicate path → `CONTRACT_DECLARATION_DUPLICATE_PATH`; unsupported kind → `CONTRACT_KIND_UNSUPPORTED`; omitted/blank status → rejected (schema `CONTRACT_CATALOG_INVALID` / model `CONTRACT_DECLARATION_INVALID` — no silent default, per `e603a5e`).
  - Evidence: `test_catalog.py` (SR-073 marker), `test_model.py`; my `verify_task2/3/status_fix` probes PASS; layer reviewer reproduced.
- **AC-2** one versioned schema requires `schema: coherence.contract-catalog.v1` and rejects unknown top-level fields (`additionalProperties:false`).
  - Evidence: `test_model.py` (SR-073 marker); probe PASS; reviewer confirmed the `const` identity + rejection live.

### SR-074 — Lexical contract path safety
- **AC-1** absolute/drive/UNC/current-drive-rooted/`..` declared path rejected **on its declared syntax before canonicalization**; an in-root resolve does not rescue unsafe syntax (`sub/../a.json` still rejected lexically).
  - Evidence: `test_catalog.py` (SR-074 marker); my probe (the 11-case fail-closed pass); reviewer reproduced (`CONTRACT_PATH_UNSAFE`, decls=0, in-root rescue still rejected).
- **AC-2** resolution that escapes the root via symlink/junction/mount/reparse point rejected as a diagnostic naming the declaration.
  - Evidence: `test_catalog.py` (SR-074); reviewer reproduced a live Windows **junction** escape (`mklink /J`) → `CONTRACT_PATH_ESCAPES_ROOT`, decls=0, diagnostic names the declaration. (True symlink needs admin on this runner — the repo test skip-guards it; the code path via `coherence.planning.paths.safe_resolve`/`has_reparse_component` is shared and covered by the junction repro.)

### SR-075 — Deterministic local contract closure
- **AC-1** a change to a transitive local `$ref` changes the referencing contract's compiled `closure_fingerprint` even when the referencing file's bytes are unchanged, and source→target edges are recorded.
  - Evidence: `test_contract_compiler.py` (SR-075 marker; renamed from `test_compiler.py` in `d3784d19` to fix a collection collision); my probe PASS (root fingerprint changed when the transitive `b.schema.json` changed); the `$ref`-base correctness (relative to the containing file, RFC 3986) is the `2873648` fix.
- **AC-2** node ordering + fingerprints are deterministic across repeated compiles/filesystem order.
  - Evidence: same file; my probe (two compilations byte-identical; nodes/edges sorted); reviewer PASS.
- **AC-3** a cycle, network URL, or non-file URI scheme is rejected as a reported diagnostic, never followed/dropped/retrieved.
  - Evidence: same file; my probe (`CONTRACT_REFERENCE_CYCLE`, `CONTRACT_REFERENCE_BROKEN` for `https:`/`urn:`); reviewer reproduced. Plus the layer-review fix `1f1648fc`: a `validates_against` to an **undeclared** id now emits `CONTRACT_RELATION_UNRESOLVED` and no dangling edge (reproduced).
- **Not** performed by the compiler: semantic schema validation stays in gates/consumer tests (documented in `docs/contract-artifacts.md`).

### SR-076 — Contract observability across trace, bundle and freshness
- **AC-1** `contract:<id>` trace nodes are absent with no catalog, present with the five typed edges (`defines`/`consumed_by`/`validated_by`/`validates_against`/`references`) with a catalog, deterministic ordering.
  - Evidence: `test_contract_nodes.py` (SR-076 marker); my probe (8 checks PASS incl. negative no-catalog); `trace check` on the repo (no catalog) is **byte-identical** to the Task-1 baseline.
- **AC-2** findings under stable codes `CONTRACT_REFERENCE_BROKEN`, `CONTRACT_MISSING_PROVENANCE`, `CONTRACT_STALE`, `CONTRACT_CONSUMER_STALE`, `CONTRACT_FIXTURE_STALE`, `CONTRACT_VALIDATION_UNAVAILABLE`; a declared contract is never reported as covered merely because its file exists.
  - Evidence: `test_contract_freshness.py` (SR-076 marker) asserts all six; T9 e2e (`test_contract_catalog_e2e.py`) asserts the machine-readable sequence and the honest `CONTRACT_VALIDATION_UNAVAILABLE` when no recorded evidence exists; layer reviewer verified all six are real + reachable and reproduced the false-cover is impossible (no-record ⇒ VALIDATION_UNAVAILABLE, never FRESH/covered).
- **AC-3** no catalog ⇒ no new invalidation, no new finding, no changed existing output.
  - Evidence: `test_contract_dependencies.py` (SR-076 marker) + a **three-surface byte-identical A/B** on this catalog-less repo, pre-change vs final HEAD:
    - `trace check` — byte-identical to Task-1 baseline (diff exit 0);
    - `navigate freshness --json` — byte-identical to baseline (diff exit 0);
    - `navigate health --json` — 106→110 findings, **only** the 4 `REQ_NO_IMPLEMENTATION` for SR-073..076, 0 removed.

## Full-campaign evidence (fresh process, pinned revision)

- Revision SHA: see `evidence/contract-artifacts/shipgate-sha.txt` (`d3784d19…`).
- Command: `uv run python -m pytest tests/unit/coherence tests/unit/factory/freshness -q`
- Scoped fresh-process run (affected directories + CLI/e2e): **100 passed, 0 failed, 1 skipped**.
- Collection integrity: 1677/1683 collected, no import-mismatch (after `d3784d19` rename).
- Full campaign output: `evidence/contract-artifacts/shipgate-unit.log` (counts to be filled from the run).

## Non-catalog invariance at a glance

| surface | base `04c8833` | final HEAD | delta |
|---|---|---|---|
| `trace check` | baseline txt | final txt | **identical** |
| `navigate freshness --json` | baseline json | final json | **identical** (0 added/0 removed) |
| `navigate health --json` | 106 findings | 110 findings | +4 `REQ_NO_IMPLEMENTATION` (new SRs) only |
