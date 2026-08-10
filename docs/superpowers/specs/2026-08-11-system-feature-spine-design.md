# SP-A — Feature Spine and Coverage: Design

**Date:** 2026-08-11
**Program:** [System Control Center](2026-08-10-system-control-center-program-decomposition.md), sub-project A of four (A → B → C → D).
**Status:** Design approved in conversation 2026-08-11. Next step is an implementation plan.

## Goal

Give the project a feature layer. Today the `/system` navigator's only
feature-level construct is a bundle, and `cool_physical_ai_project` has exactly
one covering 4 of its 181 requirements. SP-A makes bundles able to hold design
decisions, makes coverage measurable, authors the complete map, and gates it so
it cannot rot.

SP-A ships no UI. It is the data and contract layer SP-B renders.

## Context

Measured 2026-08-10 against `cool_physical_ai_project`: 181 SRs (180 `proposed`,
1 `current`), 43 tasks (22 `trace_exempt`), 6 specs, 5 plans, 2 ADRs — **237
bundleable artifacts**. One bundle exists, `reactive-planner`, with 7 members,
so **230 artifacts are unbundled** at the start of SP-A. `factory.trace status`
reports 69% traceability health over 253 slots, 280 gaps, and 1 dangling ref.

Three facts about the existing code shape this design:

- `_SCOPE_KINDS` (`queries.py:71`) is already `("bundle", "sr", "task", "file")`, but `list_scopes` (`queries.py:1180`) emits only `bundle` and `sr`. `task:` and `file:` are openable-but-unlisted. Adding `adr` follows that established pattern; SP-B later removes `sr` from the listing using the same mechanism.
- ADRs today carry **no frontmatter**. `docs/adr/0001-*.md` is `# ADR-0001: <title>`, a bare `Status: Accepted` line, then `## Decision` and `## Consequences`. There is no machine-readable id. SP-A migrates both to structured frontmatter.
- `orchestrator/git_ops.py:71` defines a `GitOps` Protocol with `SubprocessGitOps` and `FakeGitOps`. Recency reuses that pattern rather than adding new subprocess plumbing.

## Decisions

| Decision | Ruling | Rationale |
|---|---|---|
| ADR metadata | **ADRs become structured artifacts.** YAML frontmatter carrying `id`, `title`, `status`; prose sections remain the body. Both existing ADRs are migrated, and `adr.schema.json` joins `src/factory/schemas/`. | Ruled 2026-08-11. Only two ADRs exist, so the migration is cheap now and expensive later. It also brings ADRs in line with SRs and tasks, which are already frontmatter-carrying artifacts. |
| ADR ref scheme | **`adr:ADR-0001`**, resolved by id from a scan of `docs/adr/`, not `adr:<filename-stem>`. | With an `id` in frontmatter, id-based refs match `sr:SR-001` and `task:T-059`, and renaming a file for readability stops breaking every bundle that references it. |
| ADR parse failure | **Degrade visibly.** Missing or malformed frontmatter yields a `missing`/`n/a` claim, never a guess. Schema violations are reported, not silently tolerated. | Same discipline as the rest of the navigator. |
| Map review | **The agent auto-approves and escalates only on doubt.** Escalation triggers are defined below; every decision is recorded in ADR-0003 regardless. | Ruled 2026-08-11. Per-bundle blocking review costs more human time than the decisions warrant. The record is preserved so the map stays reviewable after the fact. |
| ADR page | **Brief only.** The other six tabs are hidden, not rendered degraded. | A decision has no validation matrix, no runs, no reverse walk. Six permanently-degraded tabs would teach the reader to ignore degraded states where they carry meaning. |
| Coverage question | **At least one bundle**, per artifact kind. | Membership is many-to-many; "which bundle owns this" has no answer by design. |
| Coverage scope | `sr`, `task`, `spec`, `plan`, `adr`. | Ruled at program level. |
| Ordering signal | **Most recent commit touching any member artifact.** Bundle-file edits do not count. | Ranks by where development is happening. Curation activity competing with development for the top of the list would make the sidebar a record of what you last tidied. |
| Ordering fallback | When git is unavailable, recency is `null` for every bundle, ordering falls back to id ascending, **and the payload says so.** | A silent fallback makes an arbitrary order look meaningful. |
| Empty bundles | **Legal**, rendered as explicitly empty. | Lets a feature be forward-declared before its artifacts exist — planned-but-absent work is exactly what a control center should show. Coverage counts artifacts, not bundles, so an empty bundle cannot inflate it. |
| Map authoring | **Agent drafts one bundle at a time with a recommendation; the human rules.** Tools verify, never propose. | Clustering 181 requirements lexically is inference, and `propose.py:125` already establishes that a lexical heuristic must not decide what is reachable. |
| Gate wiring | **Wired in last, after the map is authored.** | Resolves "block from day one" against "230 red artifacts" with no warn phase: the gate arrives green. |
| `--force` | Manual invocation only; prints exactly what it suppressed. `factory.yaml` never passes it. | A silent override makes a gate decorative. A pipeline run must not be forceable. |

## Architecture

Python only. Five components in `factory.system`, plus content and one line of
wiring in the product repo.

```
factory.system.bundles     _parse_member_ref  +adr:
factory.system.coverage    bundle_coverage(), member_target()  <- new module
factory.system.adr         parse_adr(), load_adrs()      <- new module
factory.system.ordering    bundle_recency()              <- new module, uses GitOps
factory.system.queries     _SCOPE_KINDS +adr, list_scopes +adr, adr brief
factory.system.cli         `coverage`, `bundle check`    <- new subcommands
factory.schemas            adr.schema.json               <- new

cool_physical_ai_project   docs/adr/000{1,2}-*.md        <- migrated to frontmatter
                           bundles/*.json                <- the map
                           docs/adr/0003-feature-bundle-map.md
                           .factory/factory.yaml         <- one gate line
```

### `factory.system.bundles`

`_parse_member_ref` (`bundles.py:49`) gains `adr:<stem>` → `docs/adr/<stem>.md`.
The existing behaviour is preserved exactly: an unresolvable member records a
reason (`bundles.py:114`) and never drops the bundle.

Coverage lives in its own module, `factory.system.coverage`, rather than inside
`bundles.py`: `bundles.py` loads one declared file, coverage reasons about the
whole artifact population. Separating them keeps `bundles.py` free of a
dependency on `factory.trace`.

```python
@dataclass(frozen=True)
class KindCoverage:
    kind: str              # "sr" | "task" | "spec" | "plan" | "adr"
    total: int
    bundled: int
    unbundled: list[str]   # refs, deterministic order

@dataclass(frozen=True)
class Coverage:
    kinds: list[KindCoverage]
    total: int
    bundled: int
    unbundled: list[str]   # every kind's unbundled refs, for the gate

def bundle_coverage(repo_root: Path) -> Coverage: ...
def member_target(repo_root: Path, member_ref: str) -> Path | None: ...
```

Pure functions over existing loaders — `trace.model.load_nodes` for
sr/task/spec/plan, `load_adrs` for ADRs. No persisted index, no cache;
projections are computed on demand, as everywhere else in the navigator.

**Refs are not uniform, so comparison is by path.** `sr:`, `task:` and `adr:`
are id-based; `spec:` and `plan:` are repo-relative paths
(`queries.py:177`). Task filenames carry slugs (`T-030-missionstate.md`), so an
id cannot be concatenated into a path. `member_target` resolves any member ref to
the artifact path it names — the one representation all five kinds share — and
returns `None` when the ref is well-formed but names nothing that exists.

### `factory.system.adr`

ADRs become structured artifacts. Frontmatter, validated against a new
`src/factory/schemas/adr.schema.json`:

```yaml
---
id: ADR-0001
title: Evolve the Existing Packages Through a Typed Contract Spine
status: accepted          # proposed | accepted | superseded
superseded_by: null       # an ADR id, when status is superseded
---
```

```python
@dataclass(frozen=True)
class AdrDocument:
    path: Path
    id: str | None                     # None when frontmatter is absent
    title: str | None
    status: str | None
    superseded_by: str | None
    sections: list[tuple[str, str]]    # (## heading, body), in file order
    schema_errors: list[str]           # empty when valid

def parse_adr(path: Path) -> AdrDocument: ...
def load_adrs(repo_root: Path) -> dict[str, AdrDocument]: ...   # by id
```

Refs are id-based (`adr:ADR-0001`), resolved through `load_adrs`. Prose sections
stay in the body and render as recorded claims, unchanged in spirit from the
original design — the frontmatter only makes identity and status machine-readable
rather than parsed out of prose.

`None` fields become `missing` claims with `n/a` freshness in the brief, never a
substituted default. Both existing ADRs are migrated as part of this step.

### `factory.system.ordering`

```python
class RecencySource(Protocol):
    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None: ...

class GitRecency: ...      # real subprocess git
class FixedRecency: ...    # test double: a path -> timestamp table

def bundle_recency(repo_root: Path, git: RecencySource) -> dict[str, str | None]: ...
def ordered_bundle_ids(repo_root: Path, git: RecencySource) -> tuple[list[str], bool]: ...
```

`bundle_recency` returns an ISO timestamp per bundle id — the most recent commit
touching any member artifact path — or `None` when unknown. Bundles are loaded
inside rather than passed in, so callers cannot supply a list inconsistent with
what is on disk.

`ordered_bundle_ids` returns the order plus `recency_available`. Ordering is
recency descending, then bundle id ascending; undated bundles sort after every
dated one. The tiebreak is deterministic and never random, mirroring
`propose.py:129`, and reversing only the timestamp component keeps the id
tiebreak ascending.

A narrow `RecencySource` Protocol rather than the full `GitOps` Protocol: this
needs one read-only query, and depending on an interface that also commits and
applies patches would be borrowing far more authority than the job requires. The
Protocol/double shape mirrors `git_ops.py:71` so no test needs a real repository.

### CLI

```
uv run python -m factory.system coverage [--json] [--gate] [--force]
uv run python -m factory.system bundle check --draft <path|-> [--json]
```

`bundle check` answers four deterministic questions about a draft the agent
wrote: member resolution (with unresolved refs named), coverage delta
(`230 → 224 unbundled`), overlaps with existing bundles (informational —
multi-membership is legal, but it should be visible), and id/filename
consistency. It proposes nothing.

`coverage --gate` exits non-zero listing every unbundled artifact. `--force`
bypasses the failure and prints what it suppressed.

## Escalation policy for the authoring pass

The agent drafts, verifies, and writes each bundle without asking. It stops and
asks only when a trigger fires.

**Mechanical triggers — decidable by `bundle check`, always escalate:**

1. A member ref does not resolve.
2. An artifact would land in more than one bundle. Multi-membership is legal, but it is a deliberate claim that two features genuinely share an artifact.
3. An artifact remains unbundled once every bundle is drafted.
4. A bundle would be written empty. Legal for forward-declaration, but never as a side effect of a pass that was supposed to place things.

**Judgment triggers — the agent's own call:**

5. It cannot state a one-sentence rationale for the cut that it believes is true.
6. An artifact could plausibly sit in another bundle already drafted.
7. The bundle has grown past the point where "read this to understand the feature" is still true.

Triggers 5–7 are not deterministic and cannot be made so — they are exactly the
judgment that was delegated when the ruling was "an agent proposes the cuts".
Calling them a rule would be dishonest. What *is* deterministic is the record:
every placement and its rationale lands in ADR-0003, and every bundle file is an
ordinary git-visible artifact. The map is therefore fully reviewable after the
fact even though it is not reviewed before the fact. That trade is the point of
the ruling, and its cost is that a wrong-but-confident placement will ship and
be found later.

## Error handling

| Condition | Behaviour |
|---|---|
| Member ref unresolvable | Existing behaviour: reason recorded, bundle kept (`bundles.py:114`). |
| ADR file missing or unreadable | Brief degrades visibly for that scope only. |
| ADR frontmatter missing or schema-invalid | The affected claim is `missing`/`n/a` and the violation is reported. The document's prose sections still render. |
| `adr:` ref resolves to no id | Existing unresolvable-member behaviour: reason recorded, bundle kept. |
| Two ADRs declare the same `id` | Loud failure. An ambiguous id makes every ref to it meaningless. |
| Git unavailable or not a repo | All recency `null`, order falls back to id ascending, stated in the payload. |
| Bundle id ≠ filename stem | Existing `BundleIdMismatchError`. Unchanged. |
| Empty bundle | Legal. Rendered as explicitly empty. |

Consistent with the navigator's standing rule: missing or corrupt evidence
degrades one scope, never the whole surface.

## Testing

TDD, `pytest`, against tmp fixtures and `FakeGitOps`. `pyproject.toml` sets
`addopts = "-m unit"`, so integration commands must pass
`-m 'unit or integration'` or they collect nothing and exit green.

- `_parse_member_ref` accepts `adr:ADR-0001`, rejects `adr:` with an empty identifier, stays case-sensitive.
- `parse_adr` on: a well-formed ADR; one with absent frontmatter; one violating the schema; one with no `##` sections; an unreadable file.
- `load_adrs` on: a directory with duplicate ids (loud failure); an absent `docs/adr/` directory; a file whose id does not match its filename (legal — refs are id-based).
- `bundle_coverage` with: an artifact in two bundles counted once; an empty bundle contributing nothing; every kind present; a repo with no bundles at all.
- `bundle_recency` with `FakeGitOps`: ordering by recency, the id-ascending tiebreak, and the no-git fallback marking itself as such.
- `bundle check` on a draft with an unresolved member, and on one overlapping an existing bundle.
- Every existing `test/system-*` and bundle test stays green.

## Work order

1. `adr.schema.json`, `factory.system.adr`, and migration of the two existing ADRs to frontmatter.
2. `adr:` member kind, scope kind, and Brief.
3. `bundle_coverage()` and the `coverage` CLI.
4. `bundle check --draft`.
5. `bundle_recency()` via the `GitOps` Protocol.
6. Author the bundle map for `cool_physical_ai_project` — agent drafts, verifies, and writes each bundle, escalating only on a trigger.
7. `docs/adr/0003-feature-bundle-map.md`, recording every cut and its rationale.
8. Wire `coverage --gate` into `.factory/factory.yaml`'s `gates.full`.

Steps 1–5 are TDD in pi-agent-factory. Step 6 is the authoring pass. Steps 1
(migration), 6, 7 and 8 land in the product repo.

## Out of scope

- Any browser or UI change. SP-B renders this.
- Removing `sr:` from `list_scopes` — SP-B, once bundles can carry navigation.
- Any requirement binding. Binding is per-bundle and on demand.
- Resolving the dangling `BR-002`. It stays a recorded known gap; SP-D restores the BR tier. Unlinking it here would destroy the only recorded business intent in the repo.
- The `system_*` write tools. SP-C.

## Accepted limitation

The gate proves every artifact sits in *some* bundle. Nothing detects an artifact
sitting in the *wrong* bundle, and newly authored artifacts arrive with no
mechanical rule to place them by. ADR-0003 is the mitigation: later placements
match against recorded reasoning rather than an invented taxonomy. This follows
from the ruling that an agent proposes the cuts, and is accepted, not solved.

The 2026-08-11 ruling that the agent auto-approves and escalates only on doubt
sharpens this limitation rather than changing it. A placement that is wrong but
confident now ships without a human seeing it, and is found later — when SP-B
renders the map, or when a reader opens a feature and finds a requirement that
does not belong. The mechanical triggers catch structural mistakes; nothing
catches a plausible-but-wrong cut. The compensating control is that the whole map
is recorded in ADR-0003 and reviewable in one pass at any time.
