"""Presentation router: resolve semantic intents to adapter targets (§22-§24).

``resolve_intent`` classifies an artifact (feat:/sr:/goal:/metric:/diag:/file,
a raw path, or a RUN id) into a concrete adapter + target behind a level, then
``dispatch`` records the action. The router never shells out with unvalidated
user strings (paths are traversal-guarded) and never re-derives what an adapter
owns. Producing the JSON the pi-ext tool consumes is ``present``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from coherence.presentation import browser as browser_module
from coherence.presentation import ide as ide_module
from coherence.presentation import sim as sim_module
from coherence.presentation.level import Facts, Level, decide
from coherence.navigate.queries import ScopeKindError, parse_scope_ref
from coherence.navigate.snapshots import resolve_navigation_snapshot

#: Kinds resolved to the SCC browser by the adapter (file/diag/sim are separate).
_BROWSER_KINDS = ("bundle", "sr", "task", "adr", "feat", "metric", "goal")


@dataclass(frozen=True)
class ResolvedIntent:
    """The outcome of classifying one presentation request."""

    artifact: str
    focus: str | None
    level: Level
    adapter: str | None  # "ide" | "browser" | "sim" | None
    target: str | None
    note: str
    snapshot_freshness: str | None = None
    snapshot_ref: str | None = None
    resolver_cmd: str | None = None


def _focus_line(focus: str | None) -> int | None:
    """A numeric focus string (spec §22 ``line``) -> line number, else None."""
    if not focus:
        return None
    return int(focus) if str(focus).isdigit() else None


def _resolve_scope(repo_root: Path, artifact: str, focus: str | None, level: Level) -> ResolvedIntent:
    kind = artifact.partition(":")[0]
    identifier = artifact[len(f"{kind}:"):]
    if kind == "file":
        abs_path, reason = ide_module.resolve_repo_file(repo_root, identifier)
        if abs_path is None:
            return ResolvedIntent(artifact, focus, level, None, None, reason or "file could not be resolved")
        line = _focus_line(focus)
        target = ide_module.build_ide_uri(abs_path, line)
        line_txt = f" line {line}" if line else ""
        return ResolvedIntent(artifact, focus, level, "ide", target, f"IDE: {abs_path}{line_txt}")
    if kind == "diag":
        res = browser_module.resolve_diagram(repo_root, identifier, artifact)
        return ResolvedIntent(artifact, focus, level, "browser", res["target"], res["note"])
    res = browser_module.resolve_browser(repo_root, kind, identifier, artifact)
    return ResolvedIntent(artifact, focus, level, "browser", res["target"], res["note"])


def resolve_intent(
    repo_root: Path,
    artifact: str,
    focus: str | None = None,
    *,
    level: Level | None = None,
    facts: Facts | None = None,
) -> ResolvedIntent:
    """Classify a presentation request into level + adapter + target.

    The level defaults to ``decide(facts)`` (INSPECT with no facts); callers
    may pass an explicit ``level`` to override. Malformed scope refs and
    unrecognized artifacts fall through to file-path handling; anything that
    cannot resolve to a reachable target yields ``adapter=None/target=None``
    with a diagnostic note — never a shell/URI call.
    """
    artifact = (artifact or "").strip()
    if not artifact:
        raise ValueError("present requires a non-empty artifact")
    chosen = level if level is not None else decide(facts if facts is not None else Facts())

    try:
        scope = parse_scope_ref(artifact)
    except ScopeKindError:
        scope = None
    if scope is not None and scope.kind in _BROWSER_KINDS + ("file", "diag"):
        snapshot = resolve_navigation_snapshot(repo_root, artifact)
        if snapshot.freshness == "stale":
            return ResolvedIntent(
                artifact,
                focus,
                chosen,
                None,
                None,
                "navigation input is stale; resolve the snapshot before presenting it",
                snapshot_freshness=snapshot.freshness,
                snapshot_ref=snapshot.ref,
                resolver_cmd=snapshot.resolver_cmd,
            )
        return _resolve_scope(repo_root, artifact, focus, chosen)

    if artifact.lower().startswith("catchup:"):
        # Inc 7 Task 3: /catchup presents the deterministic delta through the
        # SCC Catch-me-up view (a browser scope the docs server understands).
        identifier = artifact[len("catchup:"):]
        if not identifier:
            return ResolvedIntent(artifact, focus, chosen, None, None, "catchup requires a feature id")
        return ResolvedIntent(
            artifact,
            focus,
            chosen,
            "browser",
            f"system?scope={artifact}",
            "Catch-me-up view (Inc 7): deterministic 'since your last review' delta.",
        )

    if artifact.startswith("RUN-") or artifact.lower().startswith("run:"):
        res = sim_module.resolve_sim(repo_root, artifact, focus)
        return ResolvedIntent(artifact, focus, chosen, "sim", res["target"], res["note"])

    abs_path, reason = ide_module.resolve_repo_file(repo_root, artifact)
    if abs_path is None:
        return ResolvedIntent(artifact, focus, chosen, None, None, reason or "file could not be resolved")
    line = _focus_line(focus)
    target = ide_module.build_ide_uri(abs_path, line)
    line_txt = f" line {line}" if line else ""
    return ResolvedIntent(artifact, focus, chosen, "ide", target, f"IDE: {abs_path}{line_txt}")


def dispatch(level: Level, intent: ResolvedIntent) -> dict:
    """Record the human-facing action implied by ``(level, intent)``.

    INSPECT never opens anything (spec §23). PRESENT/REVIEW name the single
    interface (or review context) to open; if the artifact resolved to no
    reachable adapter, they record that nothing can be opened. The pi-ext
    caller / Inc 6 performs the actual open from the returned target.
    """
    reachable = intent.adapter is not None and intent.target is not None
    if level is Level.INSPECT:
        resolution = "INSPECT — no application focus change."
        if reachable:
            resolution += f" (present on demand: {intent.adapter}: {intent.target})"
    elif level is Level.PRESENT:
        resolution = (
            f"PRESENT — open {intent.adapter}: {intent.target}"
            if reachable
            else "PRESENT requested but no reachable adapter target; nothing opened."
        )
    else:  # REVIEW
        resolution = (
            f"REVIEW — establish multi-artifact review context; open {intent.adapter}: {intent.target}"
            if reachable
            else "REVIEW requested but no reachable adapter target; nothing opened."
        )
    result = {
        "artifact": intent.artifact,
        "focus": intent.focus,
        "level": level.value,
        "intent": {"artifact": intent.artifact, "focus": intent.focus},
        "resolution": resolution,
        "adapter": intent.adapter,
        "target": intent.target,
        "note": intent.note,
    }
    if intent.snapshot_freshness is not None:
        result["snapshot"] = {
            "ref": intent.snapshot_ref,
            "freshness": intent.snapshot_freshness,
            "resolver": intent.resolver_cmd,
        }
    return result


def present(
    repo_root: Path,
    artifact: str,
    focus: str | None = None,
    *,
    level: Level | None = None,
    facts: Facts | None = None,
) -> dict:
    """Resolve and dispatch one presentation request; returns the action JSON."""
    intent = resolve_intent(repo_root, artifact, focus, level=level, facts=facts)
    return dispatch(intent.level, intent)
