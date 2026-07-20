from __future__ import annotations

from pathlib import Path

import frontmatter


def load_skill_block(skills_dir: Path, name: str) -> str:
    """Read skills_dir/<name>/SKILL.md, strip frontmatter, wrap in the same
    <skill name="..." location="..."> block shape Pi's own native
    /skill:name expansion produces (see pi-coding-agent's
    AgentSession._expandSkillCommand) -- so both this Python-side injection
    and the TypeScript-side one in pi-ext/factory-watch/src/skill-prompt.ts
    hard-load skill content deterministically instead of relying on the
    model choosing to read it.

    Raises FileNotFoundError if the skill file doesn't exist -- a role
    naming a skill that isn't vendored is a hard configuration error, not
    something to silently degrade past.
    """
    path = skills_dir / name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"skill not found: {path}")
    post = frontmatter.load(str(path))
    body = post.content.strip()
    return f'<skill name="{name}" location="{path}">\n{body}\n</skill>'
