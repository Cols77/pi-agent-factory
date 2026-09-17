# Contract artifacts

This document is the authoritative user-facing reference for Coherence's optional
contract-artifact inventory (FEAT-021 / SR-073…SR-076). It explains the *strict local-only
model*, catalog *ownership*, the *compiler boundary*, the *relationship vocabulary*, how
`contract:<id>` behaves in bundles, and how a consumer project records validation evidence.

Contract artifacts are entirely **opt-in**: a project that keeps no catalog is untouched,
byte-for-byte, by everything described here. A project that opts in makes every declared entry
authoritative and fail-closed.

---

## 1. The strict local-only model

The catalog and every artifact it names live **inside the repository root**. Nothing in the
contract pipeline reads, resolves, or writes anything outside it. Concretely:

- **Local repository-relative paths only.** Every declared `path` is interpreted with forward
  slashes and resolved under the repository root. On Windows, forward slashes work everywhere.

- **Declared-path safety (SR-074).** A declared path is checked *lexically*, on the string
  itself, before any resolution, and rejected with a per-declaration diagnostic when it is any
  of:

  - rooted/absolute POSIX (`/abs/path`) or UNC (`//server/share/...`) — SR-074/AC-1;
  - drive-rooted (`C:\...`, current-drive-rooted `\...`) or using a drive letter — SR-074/AC-1;
  - containing a parent `..` component (escaping the root) — SR-074/AC-1;
  - containing a NUL byte, or Windows alternate-data-stream `:` syntax — SR-074/AC-1;
  - resolving outside the resolved root through a symlink, junction, mount point or other
    reparse point — SR-074/AC-2 (reported as `CONTRACT_PATH_ESCAPES_ROOT`).

  An in-root resolution can never rescue unsafe declared syntax — the lexical check runs first
  and wins.

- **`$ref` resolution.** Inter-contract references (`$ref`) resolve only to *local,
  repository-relative* targets. A `$ref` that resolves to a missing or non-file target is
  reported as `CONTRACT_REFERENCE_BROKEN` and the reference is rejected (SR-074/AC-3). A `$ref`
  that points at a network URL, or uses any non-file URI scheme, is rejected (SR-075).

The model is *strict* by design: rejected input is reported loudly with a named declaration,
never silently normalized, skipped, or "rescued" into an in-root interpretation.

## 2. Catalog ownership

`.factory/contracts.yaml` is the project's **opt-in inventory**. It carries only:

- **identity** — each `id` (referenced elsewhere as `contract:<id>`);
- **relationships** — `authority`, `validates_against`, `consumers`;
- **status** — `active` | `deprecated` | `draft`.

It is an inventory, **not** a second copy of contract content. Each contract file stays
authoritative for its own semantics. A catalog entry that carries a contract's bytes would be
rejected or ignored — the catalog schema permits only the fields above (`additionalProperties:
false` at every level).

Two consequences follow from "inventory only":

- **Absence is valid.** A project with no `.factory/contracts.yaml` produces **zero** contract
  findings and byte-identical output everywhere (`trace`, `navigate health`, `navigate
  freshness`). See §6.1.
- **Presence is authoritative and fail-closed.** Once a catalog exists, `status` is never
  defaulted, a supported `kind` is never assumed, and an entry whose file is missing
  (`CONTRACT_DECLARED_FILE_MISSING`) or whose `$ref` is broken (`CONTRACT_REFERENCE_BROKEN`) is
  reported rather than silently dropped.

## 3. The compiler boundary

The contract pipeline is deliberately narrow. `compile_contracts` performs exactly:

**parse → validate → normalize → resolve safe local relationships → hash**

It does **not** do any of the following, and the model treats these as out of scope:

- **codegen** — nothing generates code, fixtures, or derived artifacts;
- **network retrieval** — nothing fetches remote schemas (SR-075 rejects them outright);
- **external validator execution** — nothing shells out to a validator;
- **a second authoritative artifact** — the compiled closure is a derived projection of the
  catalog and the declared files, never an independent source of truth.

Semantic schema validation (does this payload satisfy this schema?) therefore lives **in gates
and consumer tests**, not in the compiler. The compiler decides *that relationships and
references are well-formed and local*; it never decides *that a contract is semantically
satisfied*.

## 4. Relationship vocabulary

Relationships attach to contract declarations in the catalog and surface in the trace graph
as *typed edges* between `contract:<id>` nodes and other artifacts. The compiler emits exactly
five edge kinds, each naming a declared relationship:

| Field / edge | Meaning |
|---|---|
| `defines` | A contract (or `contract:<id>`) is defined/produced by this artifact (source of the contract as a node in the graph). |
| `consumed_by` | This contract is consumed by the named artifact — the inverse of `consumers`. |
| `validated_by` | This contract is validated by the named artifact (a fixture validating against its schema). |
| `validates_against` | `contract:<id>` naming another declaration this artifact validates (e.g. a `fixture` validating against the `json_schema` it satisfies). |
| `references` | A local `$ref` dependency from one contract to another. |

The catalog declares intent through `authority`, `validates_against`, and `consumers`;
`compile_contracts` turns those declarations into the typed edges above.

Validation evidence is recorded separately (see §7); the vocabulary above only *declares*
intent. The compiler exposes typed edges for these relationships, which appear in the trace
graph as `contract:<id>` nodes and typed edges.

## 5. The six stability codes

When a catalog is **present**, `coherence navigate freshness --json` and
`coherence navigate health --json` report stable, machine-readable findings under exactly six
`CONTRACT_*` codes:

| Code | Severity | Meaning |
|---|---|---|
| `CONTRACT_REFERENCE_BROKEN` | error | A declaration carries a compiler `$ref` diagnostic: a dangling or non-local `$ref`. |
| `CONTRACT_MISSING_PROVENANCE` | warning | A declaration has no `authority`, no `validates_against`, and no consumers — provenance is unreadable. |
| `CONTRACT_STALE` | error | A contract's closure changed: its recorded validation fingerprint no longer matches the current compiled closure. |
| `CONTRACT_CONSUMER_STALE` | error | A consumer evidence entry (run) has a recorded contract closure fingerprint that no longer matches. |
| `CONTRACT_FIXTURE_STALE` | error | A fixture contract whose validating schema changed (or whose own closure changed) needs re-validation. |
| `CONTRACT_VALIDATION_UNAVAILABLE` | warning | A declared consumer/test has no recorded validation evidence for the declaring contract. |

These codes are **stable and additive**: they never overwrite or renumber an existing finding
code, they are all gated on a present catalog, and a declared contract is never reported as
covered merely because its file exists.

## 6. Bundle behaviour

`contract:<id>` is an **additive** permitted bundle member:

- Membership expresses *scope* — which contract artifacts a bundle groups for coverage and
  download — but the catalog remains artifact authority. A bundle never edits contract content.
- Projects **without** a catalog keep every existing bundle valid; no bundle is invalidated by
  the presence or absence of the contract member kind.

`coherence navigate coverage` counts `contract` as an ordinary member kind: a declared contract
is covered only when it is a member of some bundle (coverage is about bundling, not validity —
validity is the freshness/stability question above).

## 7. How a consumer project records validation evidence

Validation is **always an executed gate or assertion that is recorded as evidence** — it is
never *inferred* by the compiler. A consumer project records evidence by writing a run manifest
under `evidence/runs/<run-id>/manifest.json` whose `dependencies` list carries a
`kind: contract` entry naming the contract source and the recorded closure digest:

```json
{
  "run": "RUN-PAYLOAD-WIRE",
  "feature": "FEAT-WIRE",
  "dependencies": [
    {
      "kind": "contract",
      "name": "SCHEMA",
      "source": "SCHEMA",
      "digest": "<closure-fingerprint>"
    }
  ]
}
```

The freshness engine compares that recorded digest against the contract's **current** compiled
closure (its file plus every transitive local `$ref`). When the closure changed:

- the recorded consumer evidence entry is reported `CONTRACT_CONSUMER_STALE`;
- the contract itself is reported `CONTRACT_STALE`;
- a `fixture` validated against a changed schema is reported `CONTRACT_FIXTURE_STALE`.

A declared consumer with **no** recorded evidence at all is reported
`CONTRACT_VALIDATION_UNAVAILABLE` — so an unvalidated contract is called out, never assumed
valid.

---

## 8. Real examples (generated with `coherence navigate freshness --json`)

These outputs are real, captured from the fixture projects under
`evidence/contract-artifacts/fixtures/`. Each block is the actual command output for that
state.

### 8.1 Catalog absent — zero contract findings

A project with no `.factory/contracts.yaml`:

```console
$ coherence navigate freshness --repo-root fixtures/nocatalog --json
{
  "findings": []
}
```

`fixtures/nocatalog` contains contract files but **no catalog**; absence is valid and the
project gets byte-identical, catalog-less output.

### 8.2 Valid catalog

A valid catalog with five declarations (`SCHEMA`, `DEFS`, `FIX`, `BROKEN`, `ORPHAN`) and
contract files present, before any validation evidence is recorded. The compiler is total and
does not fabricate staleness: without a changed record there is no `CONTRACT_STALE` /
`CONTRACT_CONSUMER_STALE` / `CONTRACT_FIXTURE_STALE`, but provenance and validation gaps are
surfaced:

```console
$ coherence navigate freshness --repo-root fixtures/valid --json
{
  "findings": [
    {
      "code": "CONTRACT_MISSING_PROVENANCE",
      "severity": "warning",
      "subject": "contract:BROKEN",
      "detail": "contract 'BROKEN' (contracts/broken.schema.json) has no authority, no validates_against and no consumers; provenance is unreadable"
    },
    {
      "code": "CONTRACT_MISSING_PROVENANCE",
      "severity": "warning",
      "subject": "contract:DEFS",
      "detail": "contract 'DEFS' (contracts/defs.schema.json) has no authority, no validates_against and no consumers; provenance is unreadable"
    },
    {
      "code": "CONTRACT_MISSING_PROVENANCE",
      "severity": "warning",
      "subject": "contract:ORPHAN",
      "detail": "contract 'ORPHAN' (contracts/orphan.json) has no authority, no validates_against and no consumers; provenance is unreadable"
    },
    {
      "code": "CONTRACT_REFERENCE_BROKEN",
      "severity": "error",
      "subject": "contract:BROKEN",
      "detail": "contract 'BROKEN' local $ref 'missing.json' resolves to a missing or non-file target; the reference is rejected"
    },
    {
      "code": "CONTRACT_VALIDATION_UNAVAILABLE",
      "severity": "warning",
      "subject": "code:backend/app.py",
      "detail": "declared consumer code:backend/app.py has no recorded validation evidence for contract 'FIX'"
    },
    {
      "code": "CONTRACT_VALIDATION_UNAVAILABLE",
      "severity": "warning",
      "subject": "test:tests/schema_test.py",
      "detail": "declared consumer test:tests/schema_test.py has no recorded validation evidence for contract 'SCHEMA'"
    }
  ]
}
```

**Broken `$ref`**: `BROKEN` declares `contracts/broken.schema.json`, whose content is
`{"$ref": "missing.json"}` — a local `$ref` to a target that does not exist → the
`CONTRACT_REFERENCE_BROKEN` finding above (SR-074/AC-3).

### 8.3 Stale consumer / evidence

After recording `SCHEMA`'s closure as evidence in `evidence/runs/RUN-SC` and then changing
`contracts/schema.schema.json`, the recorded fingerprint no longer matches:

```console
$ coherence navigate freshness --repo-root fixtures/stale --json
{
  "findings": [
    {
      "code": "CONTRACT_CONSUMER_STALE",
      "severity": "error",
      "subject": "run:RUN-SC",
      "detail": "recorded contract validation fingerprint no longer matches the compiled closure"
    },
    {
      "code": "CONTRACT_FIXTURE_STALE",
      "severity": "error",
      "subject": "contract:FIX",
      "detail": "fixture contract 'FIX''s validating schema contract:SCHEMA changed; re-validate the fixture"
    },
    {
      "code": "CONTRACT_STALE",
      "severity": "error",
      "subject": "contract:SCHEMA",
      "detail": "contract 'SCHEMA' closure changed (its source dependencies changed)"
    }
  ]
}
```

(The full `fixtures/stale` output also carries the `CONTRACT_MISSING_PROVENANCE`,
`CONTRACT_REFERENCE_BROKEN` and `CONTRACT_VALIDATION_UNAVAILABLE` findings from §8.2 alongside
these, exactly as in `evidence/contract-artifacts/ex-stale-freshness.json`.)

### 8.4 Malformed catalog — fail-closed, zero fabricated findings

A malformed/parseable-catalog with an unreadable `contracts:` list produces no declarations, so
the freshness projection reports nothing rather than inventing staleness — the compiler refuses
to fabricate state from input it cannot trust:

```console
$ coherence navigate freshness --repo-root fixtures/malformed --json
{
  "findings": []
}
```

The parse failure is reported by the catalog/compiler layer as `CONTRACT_CATALOG_INVALID` for
the document; the freshness layer contributes **no** `CONTRACT_*` findings because it derives
them only from *declared, accepted* relationships and recorded evidence — never from a guess
about what a broken catalog "should" have contained.

### 8.5 Human-readable projection

The same findings render as deterministic lines without `--json` (from `fixtures/stale`):

```console
$ coherence navigate freshness --repo-root fixtures/stale
freshness: 11 findings
  [CONTRACT_CONSUMER_STALE] error run:RUN-SC: recorded contract validation fingerprint no longer matches the compiled closure
  [CONTRACT_FIXTURE_STALE] error contract:FIX: fixture contract 'FIX''s validating schema contract:SCHEMA changed; re-validate the fixture
  [CONTRACT_MISSING_PROVENANCE] warning contract:BROKEN: contract 'BROKEN' (contracts/broken.schema.json) has no authority, no validates_against and no consumers; provenance is unreadable
  [CONTRACT_MISSING_PROVENANCE] warning contract:DEFS: contract 'DEFS' (contracts/defs.schema.json) has no authority, no validates_against and no consumers; provenance is unreadable
  [CONTRACT_MISSING_PROVENANCE] warning contract:ORPHAN: contract 'ORPHAN' (contracts/orphan.json) has no authority, no validates_against and no consumers; provenance is unreadable
  [CONTRACT_REFERENCE_BROKEN] error contract:BROKEN: contract 'BROKEN' local $ref 'missing.json' resolves to a missing or non-file target; the reference is rejected
  [CONTRACT_STALE] error contract:SCHEMA: contract 'SCHEMA' closure changed (its source dependencies changed)
  [CONTRACT_VALIDATION_UNAVAILABLE] warning code:backend/app.py: declared consumer code:backend/app.py has no recorded validation evidence for contract 'FIX'
  [CONTRACT_VALIDATION_UNAVAILABLE] warning test:tests/schema_test.py: declared consumer test:tests/schema_test.py has no recorded validation evidence for contract 'SCHEMA'
```

Output order is deterministic — findings are sorted by `(code, subject)` — so a consumer of the
JSON can rely on stable ordering across runs.

---

## 9. Delivery traceability

- **FEAT-021** — optional contract artifacts.
- **SR-073** — strict local-only catalog model and path/reference safety.
- **SR-074** — declared path and `$ref` safety with per-declaration diagnostics.
- **SR-075** — network URL and non-file URI schemes rejected.
- **SR-076** — six stable machine-readable `CONTRACT_*` freshness codes, exposed through the
  existing CLI JSON projections, additive and byte-identical for catalog-less projects.

Test evidence: `tests/unit/coherence/navigate/test_contract_freshness.py` (AC-2/AC-3),
`tests/unit/coherence/contracts/*` (SR-073/074/075), and
`tests/unit/coherence/test_contract_cli.py` (this task's CLI projection test).
