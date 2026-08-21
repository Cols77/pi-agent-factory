"""Ref normalisation and the label index projection.

The repository carries two live spellings for document refs:
`trace/model.py:86` builds `spec:<basename>`, `system/coverage.py:70` builds
`spec:<repo-relative-path>`. `bundles.py:203` already documents that both
denote one file. This module is the single place that resolves either
spelling -- and bare ids like `T-060` -- to one canonical form.

The browser never parses a ref. It looks one up here.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from substrate.evidence import read as evidence_manifests_module
from factory.requirements import register as register_module
from factory.system import adr as adr_module
from factory.system import bundles as bundles_module
from factory.system._claims import evidence_dir as _evidence_dir
from factory.trace import model as trace_model
from substrate.ledger import tasks as ledger_module

# Kinds whose identity is the file, not a symbol: their canonical ref uses
# the repo-relative POSIX path instead of the bare id. Every other kind
# `trace_model.load_nodes` emits (sr, br, task, feat, metric, goal, diag)
# canonicalises on its bare id -- there is no third category to branch on,
# so that's an unconditional `else`, not a fallback for an unhandled case.
_PATH_KINDS = frozenset({"spec", "plan"})


def _relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def canonical_ref(root: Path, node: trace_model.Node) -> str:
    if node.kind in _PATH_KINDS:
        # node.path is always absolute (trace_model.load_nodes globs from
        # `root`), so no join against `root` is needed here.
        return f"{node.kind}:{_relative_posix(root, node.path)}"
    return f"{node.kind}:{node.id}"


def build_alias_map(root: Path, nodes: list[trace_model.Node] | None = None) -> dict[str, str]:
    """Every non-canonical spelling encountered, mapped to its canonical ref.

    Includes the bare id, the `<kind>:<basename>` form the trace graph emits,
    and the canonical ref itself (so a lookup is one dict access either way).
    """
    if nodes is None:
        nodes = trace_model.load_nodes(root)
    aliases: dict[str, str] = {}
    for node in nodes:
        canonical = canonical_ref(root, node)
        aliases[canonical] = canonical
        aliases[node.id] = canonical
        if node.kind in _PATH_KINDS:
            # `_file_node` already sets id = "<kind>:<basename>"
            # (trace/model.py:86), so node.id is ALREADY the basename spelling.
            # Prefixing it again would mint junk keys like "spec:spec:foo.md".
            aliases[f"{node.kind}:{Path(node.path).name}"] = canonical
        else:
            aliases[f"{node.kind}:{node.id}"] = canonical
    return aliases


def normalize_ref(
    root: Path, raw: str, aliases: dict[str, str] | None = None
) -> str | None:
    """Resolve a raw ref or bare id to its canonical form, or None.

    Never guesses: an input with no recorded artifact behind it returns None
    so the renderer can say so plainly.
    """
    if aliases is None:
        aliases = build_alias_map(root)
    return aliases.get(raw.strip())


# Exactly the intersection of queries.py:74's _SCOPE_KINDS and
# system-bootstrap.ts:351's TABS_BY_KIND. `spec`/`plan` parse as nothing;
# `adr`/`diag`/`feat`/`metric`/`goal` parse as scopes but fall through to the
# bundle tab set and would render an error page. Neither gets a link.
_OPENABLE_KINDS = frozenset({"bundle", "sr", "task", "file"})

_HEADING_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _scope_href(ref: str, kind: str) -> str | None:
    if kind not in _OPENABLE_KINDS:
        return None
    return "/system?scope=" + quote(ref, safe="")


def _first_paragraph(body: str) -> str | None:
    """First non-heading paragraph of `body`. A helper for section extraction
    only -- it is never a description source on its own (Global Constraint 2:
    a lead paragraph is not a named field). See `_named_description`."""
    for block in body.split("\n\n"):
        text = block.strip()
        if text and not text.startswith("#"):
            return " ".join(text.split())
    return None


def _section_paragraph(body: str, heading: str) -> str | None:
    """First paragraph of the first section whose heading matches, case-insensitively."""
    matches = list(_HEADING_SECTION.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1).strip().lower() != heading.lower():
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        return _first_paragraph(body[match.end():end])
    return None


# Checked in this order for every spec/plan. Measured against this repo: a raw
# lead-paragraph fallback produced the SAME boilerplate text for every one of
# 53 plans (the "For agentic workers" skill banner) and the Date/Status
# metadata block for specs -- text that explains nothing and is identical
# across artifacts, and not a named field to begin with (Global Constraint 2).
# Removed; named sources only.
_NAMED_SECTIONS = ("Purpose", "Goal", "Problem", "Overview", "Summary")

# A plan's "**Goal:** <text>" label line -- not a `##` section, so
# `_section_paragraph` cannot see it; checked only for plans.
_GOAL_LABEL = re.compile(r"^\*\*Goal:\*\*\s*(.+?)\s*$", re.MULTILINE)


def _named_description(body: str, kind: str) -> tuple[str | None, str | None]:
    """A description from one named field, or `(None, None)`.

    Never a lead paragraph: "no description recorded" is an honest, actionable
    state the browser can turn into a next step, not something to paper over
    with prose the document never declared as its description.
    """
    for heading in _NAMED_SECTIONS:
        found = _section_paragraph(body, heading)
        if found:
            return found, heading.lower()
    if kind == "plan":
        match = _GOAL_LABEL.search(body)
        if match:
            return " ".join(match.group(1).split()), "goal"
    return None, None


def _changed_file_paths(root: Path) -> list[str]:
    """The bounded, recorded set of paths a `file:` entry can cover.

    There are no file nodes in the trace graph (`trace_model.load_nodes`
    emits none), so files cannot be discovered by walking the graph the way
    every other kind is. The one recorded, bounded source of file paths is
    every evidence manifest's `implementation.changed_files` -- exactly what
    `query_traversal`'s `files` step (`queries.py:1624-1631`) and
    `renderChangedFiles`/`renderReversePath`'s changed-file chips both read.
    Scanning every manifest once (not per-task) is still bounded -- by the
    number of recorded runs, not an unbounded repository walk -- and is a
    strict superset of what any single traversal could ever surface, since a
    traversal's files are themselves drawn from a subset of these same
    manifests.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for manifest in evidence_manifests_module.list_run_manifests(_evidence_dir(root)):
        changed = manifest.get("implementation", {}).get("changed_files")
        if not changed:
            continue
        for path in changed:
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def build_labels(root: Path) -> dict:
    """The label index: every known ref with its title and recorded description.

    Composes existing loaders only. Never synthesises text: a description is
    verbatim from one named field, or it is None.
    """
    degraded: list[str] = []
    nodes = trace_model.load_nodes(root)
    aliases = build_alias_map(root, nodes)
    labels: dict[str, dict] = {}

    requirements = {}
    try:
        requirements = {r.id: r for r in register_module.load_register(root / "requirements")}
    except Exception as exc:  # a missing register must not sink the index
        degraded.append(f"requirements register unavailable: {exc}")

    tasks = {}
    try:
        tasks = {t.id: t for t in ledger_module.load_tasks(root / "tasks")}
    except Exception as exc:
        degraded.append(f"task ledger unavailable: {exc}")

    adrs = {}
    try:
        adrs = adr_module.load_adrs(root)
    except Exception as exc:
        degraded.append(f"adrs unavailable: {exc}")

    for node in nodes:
        ref = canonical_ref(root, node)
        description: str | None = None
        source: str | None = None
        status: str | None = None
        relations: dict[str, list[str]] = {}

        # The deferral reason lives on the trace node, not on Requirement
        # (trace/model.py:34,48). Requirement has no trace_deferred attribute.
        deferral_reason = node.deferred

        if node.kind == "sr" and node.id in requirements:
            req = requirements[node.id]
            description, source = req.statement.strip(), "statement"
        elif node.kind == "task" and node.id in tasks:
            task = tasks[node.id]
            status = task.status
            satisfies = [aliases.get(s, s) for s in task.satisfies]
            if satisfies:
                relations["satisfies"] = satisfies
            if task.source_plan:
                # `Task.source_plan` (substrate/ledger/tasks.py:23) is recorded as the bare
                # repo-relative path, with no `plan:` prefix -- unlike
                # `satisfies`'s bare SR ids, which are already aliased keys.
                # Prefixing it is not parsing a ref (there is nothing to
                # split or infer); it is building the one candidate key the
                # alias map might resolve, the same normalization
                # `queries.py`'s `_file_ref` performs for file paths.
                plan_ref = f"plan:{task.source_plan}"
                relations["source_plan"] = [aliases.get(plan_ref, plan_ref)]
        elif node.kind in _PATH_KINDS:
            # node.path is always absolute (trace_model.load_nodes globs from
            # `root`); see labels.py's canonical_ref for the same rule.
            # One unreadable document must degrade only this entry, never
            # sink the whole index (~124 documents read here on this repo).
            try:
                body = node.path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                degraded.append(f"{ref}: unreadable ({exc})")
            else:
                description, source = _named_description(body, node.kind)

        labels[ref] = {
            "ref": ref,
            "id": node.id,
            "kind": node.kind,
            "title": node.title,
            "description": description,
            "description_source": source,
            "deferral_reason": deferral_reason,
            "status": status,
            "relations": relations,
            "path": _relative_posix(root, node.path),
            "scope_href": _scope_href(ref, node.kind),
        }

    # ADRs are NOT in the trace graph (trace/model.py:102 emits no adr nodes),
    # so they are added from their own loader. Without this the label index
    # contains zero ADR entries and every `design` hop in the traversal spine
    # renders as "not in the label index".
    for adr_id, doc in adrs.items():
        ref = f"adr:{adr_id}"
        found = None
        if doc.path.exists():
            try:
                body = doc.path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                degraded.append(f"{ref}: unreadable ({exc})")
            else:
                found = _section_paragraph(body, "Decision")
        labels[ref] = {
            "ref": ref, "id": adr_id, "kind": "adr", "title": doc.title or adr_id,
            "description": found,
            "description_source": "decision" if found else None,
            "deferral_reason": None, "status": doc.status, "relations": {},
            "path": _relative_posix(root, doc.path),
            "scope_href": _scope_href(ref, "adr"),
        }
        aliases[ref] = ref
        aliases[adr_id] = ref

    for bundle in bundles_module.list_bundles(root / "bundles"):
        ref = f"bundle:{bundle.id}"
        labels[ref] = {
            "ref": ref, "id": bundle.id, "kind": "bundle", "title": bundle.label,
            "description": bundle.description,
            "description_source": "description" if bundle.description else None,
            "deferral_reason": None, "status": None, "relations": {},
            "path": str(bundle.citation.path),
            "scope_href": _scope_href(ref, "bundle"),
        }
        aliases[ref] = ref
        aliases[bundle.id] = ref

    # `file:` entries: there are no file nodes in the trace graph, so files
    # are added from the one bounded, recorded source available -- every
    # evidence manifest's changed_files (see `_changed_file_paths`). A file
    # has no recorded title or description of its own; the path IS its
    # identity, so `title` is the path and `description` stays None (never
    # invented) -- `file_entry`'s own contract.
    #
    # Two alias spellings are recorded per file, because the two render
    # sites that resolve a file ref disagree on which spelling they pass:
    # `queries.py`'s `_file_ref` prefixes traversal files as `file:<path>`,
    # while `renderChangedFiles`/`renderReversePath` pass the RAW path (that
    # field is `system_claim.changed_files` / the reverse-walk `file` field,
    # both frozen response schemas this feature does not touch). Aliasing
    # both spellings to the same canonical ref is what makes `refChip`
    # resolve either one without the browser ever parsing or prefixing.
    for path in _changed_file_paths(root):
        entry = file_entry(root, path)
        ref = entry["ref"]
        labels[ref] = entry
        aliases[ref] = ref
        if path in aliases and aliases[path] != ref:
            degraded.append(f"alias collision: {path!r} already resolves to {aliases[path]}")
        else:
            aliases[path] = ref

    return {"labels": labels, "aliases": aliases, "degraded": degraded}


def file_entry(root: Path, relative_path: str) -> dict:
    """A label entry for a repo path. The path is the identity -- nothing is
    invented, and `description` is always None."""
    ref = f"file:{relative_path}"
    return {
        "ref": ref, "id": relative_path.rsplit("/", 1)[-1], "kind": "file",
        "title": relative_path, "description": None, "description_source": None,
        "deferral_reason": None, "status": None, "relations": {},
        "path": relative_path, "scope_href": _scope_href(ref, "file"),
    }
