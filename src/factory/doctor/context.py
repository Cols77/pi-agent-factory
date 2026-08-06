from __future__ import annotations

from pathlib import Path

import yaml

from factory.requirements.register import load_register
from factory.validation.scorer_registry import ScorerModuleError, load_scorers

_SPECS = ("docs", "superpowers", "specs")


def _harness_inventory(project_root: Path) -> dict:
    """Which harnesses the project declares, and which metrics it has implemented.

    Read from the raw YAML rather than load_config: this only needs the scorer
    names, and building playground/harness objects would do more work and fail
    for unrelated reasons.
    """
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return {"present": False, "harnesses": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    harnesses: dict[str, dict] = {}
    for name, spec in (data.get("harnesses") or {}).items():
        module = (spec or {}).get("scorers")
        try:
            metrics = sorted(load_scorers(module, project_root))
            error = None
        except ScorerModuleError as exc:
            # A project that cannot load its scorers still has a register worth
            # reading. Report the reason instead of failing the whole command.
            metrics, error = [], str(exc)
        harnesses[name] = {"scorers_module": module, "metrics": metrics, "error": error}
    return {"present": True, "harnesses": harnesses}


def gather_context(project_root: Path) -> dict:
    """The agent's field of view: what it cannot cheaply derive for itself.

    Deliberately does NOT summarise, rank, filter or excerpt the specs -- the
    agent reads those with its own tools. A heuristic that decided which prose
    reached the agent would cap what it can find.
    """
    specs_dir = project_root.joinpath(*_SPECS)
    specs = (
        [p.relative_to(project_root).as_posix() for p in sorted(specs_dir.glob("*.md"))]
        if specs_dir.is_dir()
        else []
    )
    requirements: list[dict] = []
    for req in load_register(project_root / "requirements"):
        b = req.binding
        requirements.append(
            {
                "id": req.id,
                "title": req.title,
                "statement": req.statement,
                "domain": req.domain,
                "source": req.source,
                "state": "proposed" if b is None else "active",
                "binding": None
                if b is None
                else {
                    "harness": b.harness,
                    "experiment": b.experiment,
                    "metric": b.metric,
                    "assert": b.assert_expr,
                },
            }
        )
    return {
        "specs": specs,
        "requirements": requirements,
        "config": _harness_inventory(project_root),
    }


def format_context(ctx: dict) -> str:
    lines = [
        # ASCII only: this is printed to a console, and cp1252 cannot encode an
        # em dash. Comments and docs may use one; CLI output may not.
        f"Specs ({len(ctx['specs'])}) -- read these files yourself; this command does not",
        "summarise, rank or excerpt them:",
        *[f"  {p}" for p in ctx["specs"]],
        "",
        f"Register ({len(ctx['requirements'])}):",
    ]
    for req in ctx["requirements"]:
        lines.append(f"  {req['id']}  [{req['state']}]  {req['title']}")
        lines.append(f"      {req['statement']}")
        lines.append(f"      source: {req['source'] or '(none)'}")
        if req["binding"]:
            b = req["binding"]
            lines.append(f"      binding: {b['harness']}/{b['experiment']} {b['metric']}")
    if not ctx["requirements"]:
        lines.append("  (empty)")
    lines.append("")
    config = ctx["config"]
    if not config["present"]:
        lines.append("No .factory/factory.yaml -- no harness is declared and no metric is")
        lines.append("implemented. Requirements can still be proposed and accepted.")
        return "\n".join(lines)
    lines.append("Declared harnesses:")
    for name, info in config["harnesses"].items():
        detail = info["error"] or (", ".join(info["metrics"]) or "(no metrics implemented)")
        lines.append(f"  {name}  scorers={info['scorers_module'] or '(none)'}  -> {detail}")
    return "\n".join(lines)
