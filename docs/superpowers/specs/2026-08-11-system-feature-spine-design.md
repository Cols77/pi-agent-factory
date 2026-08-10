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
- ADRs carry **no frontmatter**. `docs/adr/0001-*.md` is `# ADR-0001: <title>`, a bare `Status: Accepted` line, then `## Decision` and `## Consequences`. There is no machine-readable id.
- `orchestrator/git_ops.py:71` defines a `GitOps` Protocol with `SubprocessGitOps` and `FakeGitOps`. Recency reuses that pattern rather than adding new subprocess plumbing.

## Decisions

| Decision | Ruling | Rationale |
|---|---|---|
| ADR metadata | **Parse the existing convention.** H1 → title, first `Status:` line → status, each `##` section → one recorded claim. | Adding frontmatter would make the factory dictate the product repo's ADR format, and impose ceremony on a document written to be read by humans. Every parsed value is recorded text read verbatim, so nothing is inferred. |
| ADR parse failure | **Degrade visibly.** A missing H1 or `Status:` line yields a `missing`/`n/a` claim, never a guess. | Same discipline as the rest of the navigator. A strict parse whose failure is loud beats a lenient one that invents. |
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
                           bundle_coverage()          <- new
factory.system.adr         parse_adr()                <- new module
factory.system.ordering    bundle_recency()           <- new module, uses GitOps
factory.system.queries     _SCOPE_KINDS +adr, list_scopes +adr, adr brief
factory.system.cli         `coverage`, `bundle check` <- new subcommands

cool_physical_ai_project   bundles/*.json             <- the map
                           docs/adr/0003-feature-bundle-map.md
                           .factory/factory.yaml      <- one gate line
```

### `factory.system.bundles`

`_parse_member_ref` (`bundles.py:49`) gains `adr:<stem>` → `docs/adr/<stem>.md`.
The existing behaviour is preserved exactly: an unresolvable member records a
reason (`bundles.py:114`) and never drops the bundle.

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

def bundle_coverage(repo_root: Path) -> Coverage: ...
```

A pure function over existing loaders. No persisted index, no cache — projections
are computed on demand, as everywhere else in the navigator.

### `factory.system.adr`

```python
@dataclass(frozen=True)
class AdrDocument:
    stem: str
    title: str | None                  # H1, or None
    status: str | None                 # first "Status:" line, or None
    sections: list[tuple[str, str]]    # (## heading, body), in file order

def parse_adr(path: Path) -> AdrDocument: ...
```

`None` fields become `missing` claims with `n/a` freshness in the brief, never a
substituted default.

### `factory.system.ordering`

```python
def bundle_recency(
    repo_root: Path, bundles: list[Bundle], git: GitOps
) -> dict[str, str | None]: ...
```

Returns an ISO timestamp per bundle id — the most recent commit touching any
member artifact path — or `None` when unknown. Ordering is recency descending,
then bundle id ascending. The tiebreak is deterministic and never random,
mirroring `propose.py:129`.

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

## Error handling

| Condition | Behaviour |
|---|---|
| Member ref unresolvable | Existing behaviour: reason recorded, bundle kept (`bundles.py:114`). |
| ADR file missing or unreadable | Brief degrades visibly for that scope only. |
| ADR missing H1 or `Status:` | That claim is `missing`/`n/a`. The rest of the document still renders. |
| Git unavailable or not a repo | All recency `null`, order falls back to id ascending, stated in the payload. |
| Bundle id ≠ filename stem | Existing `BundleIdMismatchError`. Unchanged. |
| Empty bundle | Legal. Rendered as explicitly empty. |

Consistent with the navigator's standing rule: missing or corrupt evidence
degrades one scope, never the whole surface.

## Testing

TDD, `pytest`, against tmp fixtures and `FakeGitOps`. `pyproject.toml` sets
`addopts = "-m unit"`, so integration commands must pass
`-m 'unit or integration'` or they collect nothing and exit green.

- `_parse_member_ref` accepts `adr:<stem>`, rejects `adr:` with an empty identifier, stays case-sensitive.
- `parse_adr` on: a well-formed ADR; one missing its H1; one missing `Status:`; one with no `##` sections; an unreadable file.
- `bundle_coverage` with: an artifact in two bundles counted once; an empty bundle contributing nothing; every kind present; a repo with no bundles at all.
- `bundle_recency` with `FakeGitOps`: ordering by recency, the id-ascending tiebreak, and the no-git fallback marking itself as such.
- `bundle check` on a draft with an unresolved member, and on one overlapping an existing bundle.
- Every existing `test/system-*` and bundle test stays green.

## Work order

1. `adr:` member kind, scope kind, and Brief.
2. `bundle_coverage()` and the `coverage` CLI.
3. `bundle check --draft`.
4. `bundle_recency()` via the `GitOps` Protocol.
5. Author the bundle map for `cool_physical_ai_project` — one bundle at a time, agent drafts with a recommendation, human rules.
6. `docs/adr/0003-feature-bundle-map.md`, recording the cuts and the rulings.
7. Wire `coverage --gate` into `.factory/factory.yaml`'s `gates.full`.

Steps 1–4 are TDD in pi-agent-factory. Step 5 is the conversation loop. Steps 6–7
land in the product repo.

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
