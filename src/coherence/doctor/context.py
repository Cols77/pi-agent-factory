from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

from coherence.register.register import load_register

_SPECS = ("docs", "superpowers", "specs")
Scorer = Callable[..., bool]


class ScorerModuleError(ValueError):
    pass


def _load_scorers(module_name: str | None, project_root: Path) -> dict[str, Scorer]:
    """Import a target repository's scorer module and return its SCORERS mapping."""
    if not module_name:
        return {}
    src = project_root / "src"
    added = str(src) if src.is_dir() and str(src) not in sys.path else None
    if added:
        sys.path.insert(0, added)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ScorerModuleError(f"cannot import scorer module {module_name!r}: {exc}") from exc
    finally:
        if added:
            sys.path.remove(added)

    registry = getattr(module, "SCORERS", None)
    if not isinstance(registry, dict):
        raise ScorerModuleError(
            f"{module_name!r} must define a SCORERS dict of metric name -> callable"
        )
    return {str(k): v for k, v in registry.items()}


def _harness_inventory(project_root: Path) -> dict:
    """Which harnesses the project declares, and which metrics it implements."""
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return {"present": False, "harnesses": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    harnesses: dict[str, dict] = {}
    for name, spec in (data.get("harnesses") or {}).items():
        module = (spec or {}).get("scorers")
        try:
            metrics = sorted(_load_scorers(module, project_root))
            error = None
        except ScorerModuleError as exc:
            metrics, error = [], str(exc)
        harnesses[name] = {"scorers_module": module, "metrics": metrics, "error": error}
    return {"present": True, "harnesses": harnesses}


def gather_context(project_root: Path) -> dict:
    """Return the files, register state, and declared harness metrics in view."""
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
    return {"specs": specs, "requirements": requirements, "config": _harness_inventory(project_root)}


def format_context(ctx: dict) -> str:
    lines = [
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


__all__ = ["format_context", "gather_context"]

