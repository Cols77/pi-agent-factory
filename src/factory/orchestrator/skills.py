from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.paths import factory_skills_dir

# Re-exported: role skills ship with the FACTORY, not with the repo being worked
# on, so they resolve from factory.paths whenever the target project has none.
__all__ = ["factory_skills_dir", "load_skill_block"]


def load_skill_block(skills_dir: Path, name: str) -> str:
    """Read <name>/SKILL.md, strip frontmatter, wrap in the same
    <skill name="..." location="..."> block shape Pi's own native
    /skill:name expansion produces (see pi-coding-agent's
    AgentSession._expandSkillCommand) -- so both this Python-side injection
    and the TypeScript-side one in pi-ext/factory-watch/src/skill-prompt.ts
    hard-load skill content deterministically instead of relying on the
    model choosing to read it.

    Looks in *skills_dir* first, then falls back to the factory's own skills.
    A project MAY vendor its own copy of a skill (roles.py) and that wins; but
    resolving ONLY from the target repo meant factory-run could never run
    against a project that hadn't vendored the whole set -- which is every
    project except the factory itself.

    Raises FileNotFoundError, naming both locations, if neither has it -- a role
    naming a skill that isn't vendored anywhere is a hard configuration error,
    not something to silently degrade past.
    """
    path = skills_dir / name / "SKILL.md"
    if not path.exists():
        fallback = factory_skills_dir() / name / "SKILL.md"
        if not fallback.exists():
            raise FileNotFoundError(
                f"skill not found: {path} (nor in the factory's own skills: {fallback})"
            )
        path = fallback
    post = frontmatter.load(str(path))
    body = post.content.strip()
    return f'<skill name="{name}" location="{path}">\n{body}\n</skill>'
