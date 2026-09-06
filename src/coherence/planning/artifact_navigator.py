"""Read-only resolution of a feature's already-drafted artifact graph.

Planning should start from what the repository already says, not from a blank
prompt. Given ``FEAT-NNN`` this walks the graph the frontmatter already encodes
-- feature -> requirements -> authority spec -> implementation plan -> bundle --
and reports each artifact's content **verbatim** alongside whether it exists yet.

Nothing here paraphrases, summarizes, or interprets. A model reading this output
is reading the repository's own words, so seeded intent cannot drift from the
drafted record. Missing artifacts are reported as missing, never as an error:
"not drafted yet" is the normal state early in a feature's life.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

FEATURE_ID = re.compile(r"^FEAT-\d{3}$")
REQUIREMENT_ID = re.compile(r"^SR-\d{3}$")
_STATUS_NOTE = re.compile(r"^>\s*Status:\s*(.+)$", re.MULTILINE)


def _frontmatter(path: Path) -> tuple[dict[str, Any], str, str | None]:
    """Return `(frontmatter, body, error)`.

    `error` is `None` when the file was read and any frontmatter block present
    parsed to a mapping (an absent block or a block that parses to something
    else, such as a bare scalar or list, is not itself an error -- there is
    simply nothing declared). `error` carries a message when the file could
    not be read or its frontmatter block could not be parsed as YAML at all,
    so a caller can distinguish "nothing declared" from "declaration lost".
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {}, "", f"could not read {path}: {exc}"
    if not text.startswith("---\n"):
        return {}, text, None
    _, _, remainder = text.partition("---\n")
    raw, separator, body = remainder.partition("\n---")
    if not separator:
        return {}, text, None
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return {}, body, f"frontmatter in {path} is not valid YAML: {exc}"
    return (loaded if isinstance(loaded, dict) else {}), body, None


def _artifact(project_root: Path, relative: str | None) -> dict[str, Any]:
    if not relative or not isinstance(relative, str):
        return {"path": None, "present": False}
    return {"path": relative, "present": (project_root / relative).is_file()}


def _requirement(project_root: Path, requirement_id: str) -> dict[str, Any]:
    relative = f"requirements/{requirement_id}.md"
    path = project_root / relative
    if not path.is_file():
        return {
            "id": requirement_id,
            "path": relative,
            "present": False,
            "title": None,
            "statement": None,
            "status_note": None,
            "acceptance": [],
            "frontmatter_error": None,
        }
    meta, body, error = _frontmatter(path)
    note = _STATUS_NOTE.search(body)
    acceptance = meta.get("acceptance")
    return {
        "id": requirement_id,
        "path": relative,
        "present": True,
        "title": meta.get("title"),
        "statement": meta.get("statement"),
        "status_note": note.group(1).strip() if note else None,
        "acceptance": acceptance if isinstance(acceptance, list) else [],
        "frontmatter_error": error,
    }


def resolve_feature_context(project_root: Path, feature_id: str) -> dict[str, Any]:
    """Resolve everything already drafted for `feature_id`, verbatim."""
    if not isinstance(feature_id, str) or FEATURE_ID.fullmatch(feature_id) is None:
        raise ValueError("feature_id must look like FEAT-NNN")

    relative = f"docs/features/{feature_id}.md"
    path = project_root / relative
    context: dict[str, Any] = {
        "schema": 1,
        "feature_id": feature_id,
        "feature_path": relative,
        "present": path.is_file(),
        "title": None,
        "description": None,
        "status": None,
        "requirements": [],
        "authority_spec": {"path": None, "present": False},
        "implementation_plan": {"path": None, "present": False},
        "bundle": _artifact(project_root, f"bundles/{feature_id}.json"),
        "missing": [],
        "frontmatter_error": None,
    }
    if not context["present"]:
        context["missing"] = [relative]
        return context

    meta, _, error = _frontmatter(path)
    context["frontmatter_error"] = error
    if error is not None:
        # The declaration itself could not be read back. Reporting empty
        # requirements/authority_spec/etc. here would read as "this feature
        # declares none of that", which is false -- it declares something we
        # failed to parse. Stop before fabricating an empty-but-valid graph.
        return context
    context["title"] = meta.get("title")
    context["description"] = meta.get("description")
    context["status"] = meta.get("status")
    context["authority_spec"] = _artifact(project_root, meta.get("authority_spec"))
    context["implementation_plan"] = _artifact(project_root, meta.get("implementation_plan"))

    declared = meta.get("requirements")
    for requirement_id in declared if isinstance(declared, list) else []:
        if isinstance(requirement_id, str) and REQUIREMENT_ID.fullmatch(requirement_id):
            context["requirements"].append(_requirement(project_root, requirement_id))

    context["missing"] = [
        item["path"]
        for item in (
            *context["requirements"],
            context["authority_spec"],
            context["implementation_plan"],
            context["bundle"],
        )
        if item["path"] and not item["present"]
    ]
    return context


def seed_prompt(context: dict[str, Any]) -> str:
    """Compose the capture seed from the feature's own words, never a paraphrase."""
    if not context.get("present"):
        raise ValueError(f"{context['feature_id']} has no drafted feature document")
    if context.get("frontmatter_error"):
        raise ValueError(
            f"{context['feature_id']}'s frontmatter could not be parsed: "
            f"{context['frontmatter_error']}"
        )
    return (
        f"Plan {context['feature_id']} ({context['title']}): {context['description']} "
        f"[source: {context['feature_path']}]"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-plan-navigate")
    parser.add_argument("feature_id")
    parser.add_argument("--project-root", default=".", type=Path)
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    try:
        context = resolve_feature_context(Path(args.project_root), args.feature_id)
    except ValueError as exc:
        print(json.dumps({"schema": 1, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(context, indent=2, ensure_ascii=False))
    return 0


__all__ = ["FEATURE_ID", "main", "resolve_feature_context", "seed_prompt"]


if __name__ == "__main__":
    raise SystemExit(main())
