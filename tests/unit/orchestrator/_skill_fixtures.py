from __future__ import annotations

from pathlib import Path

SKILL_NAMES = [
    "verification-before-completion",
    "context-completeness-audit",
    "test-driven-development",
    "systematic-debugging",
    "receiving-code-review",
    "kb-lookup",
    "code-documentation",
    "requesting-code-review",
    "coding-principles",
    "session-report",
]


def write_skill_stubs(root: Path) -> None:
    """Write minimal SKILL.md stub files under root/.pi/skills/<name>/ for
    every skill the currently-invoked roles (context-gatherer/dev/review)
    need, at the real repo's .pi/skills/ layout. Used by any test that
    exercises compose_prompt, directly or via run_dev/run_review/run_task/
    run_next, now that skill loading is hard-required rather than optional.
    """
    for name in SKILL_NAMES:
        skill_dir = root / ".pi" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: stub for tests\n---\n\nStub content for {name}.\n",
            encoding="utf-8",
        )
