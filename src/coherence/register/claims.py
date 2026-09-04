"""Commit-claim parsing and exemption policy (SR-054).

Pure module: parses the ``SR:`` commit trailer, loads
``.factory/trace-claims.yaml``, and classifies paths against exemption globs.
It reads no git and writes nothing -- ``coherence.register.ingest`` is the only
module that touches git.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

TRAILER_KEY = "SR"
CONFIG_RELPATH = (".factory", "trace-claims.yaml")

_TRAILER_RE = re.compile(rf"^{TRAILER_KEY}:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_SR_ID_RE = re.compile(r"^SR-\d+$")


@dataclass(frozen=True)
class ClaimsConfig:
    """``.factory/trace-claims.yaml``, or the empty default when absent."""

    epoch: str | None = None
    exempt: tuple[str, ...] = ()


def parse_sr_trailer(message: str) -> tuple[str, ...]:
    """Ids from every ``SR:`` trailer line, in declaration order, deduplicated.

    Only a line whose first characters are ``SR:`` counts -- a mention of an id
    inside prose is not a claim.
    """
    ids: list[str] = []
    for raw in _TRAILER_RE.findall(message):
        for chunk in raw.split(","):
            token = chunk.strip()
            if token and token not in ids:
                ids.append(token)
    return tuple(ids)


def invalid_ids(ids: Sequence[str]) -> tuple[str, ...]:
    """The subset of ``ids`` that are not shaped like a register id."""
    return tuple(i for i in ids if not _SR_ID_RE.match(i))


def glob_match(pattern: str, path: str) -> bool:
    """Match a repo-relative POSIX path against a glob.

    Written explicitly because Python 3.12 has no ``PurePosixPath.full_match``
    and ``fnmatch`` does not distinguish ``**`` from ``*``. ``**`` crosses
    separators; ``*`` and ``?`` do not.
    """
    out: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            if pattern.startswith("/", i):
                i += 1
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    out.append("$")
    return re.match("".join(out), path) is not None


def exempting_glob(config: ClaimsConfig, path: str) -> str | None:
    """The first configured glob that exempts ``path``, else None."""
    for pattern in config.exempt:
        if glob_match(pattern, path):
            return pattern
    return None


def load_claims_config(root: Path) -> ClaimsConfig:
    """Read ``.factory/trace-claims.yaml``; an absent or unreadable file is the
    empty default, so a repository that has not adopted claims still works."""
    path = root.joinpath(*CONFIG_RELPATH)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ClaimsConfig()
    if not isinstance(raw, dict):
        return ClaimsConfig()
    epoch = raw.get("epoch")
    exempt = raw.get("exempt") or []
    return ClaimsConfig(
        epoch=str(epoch) if isinstance(epoch, str) and epoch.strip() else None,
        exempt=tuple(str(p) for p in exempt if isinstance(p, str)),
    )


def registered_ids(root: Path) -> frozenset[str]:
    """Every SR id with a file in ``requirements/``.

    Reads the register's own naming convention rather than parsing frontmatter:
    the commit-time check must stay cheap enough to run on every commit, and an
    id's *existence* is a filename question.
    """
    return frozenset(
        p.stem for p in (root / "requirements").glob("SR-*.md") if _SR_ID_RE.match(p.stem)
    )


def check_commit(
    root: Path,
    message: str,
    staged: Sequence[str],
    *,
    config: ClaimsConfig | None = None,
) -> tuple[str, ...]:
    """Error strings for one commit; empty means it passes.

    Three checks, in order: every staged path exempt (passes outright); a
    trailer present; every id it names shaped like an id and present in the
    register. Only the non-exempt paths are ever named in an error -- a mixed
    commit is asked about its non-exempt half, not its documentation.

    This is fast feedback, not the enforcement: hooks are per-clone, never
    cloned with the repository, and ``--no-verify`` bypasses them by design.
    Enforcement lives at ingestion time, where the commits already exist.
    """
    cfg = config if config is not None else load_claims_config(root)
    unexempt = [path for path in staged if exempting_glob(cfg, path) is None]
    if not unexempt:
        return ()
    ids = parse_sr_trailer(message)
    if not ids:
        listed = ", ".join(sorted(unexempt)[:5])
        return (
            f"commit changes non-exempt paths ({listed}) but declares no "
            f"'{TRAILER_KEY}:' trailer; add '{TRAILER_KEY}: SR-0xx' or exempt "
            f"the path in {'/'.join(CONFIG_RELPATH)}",
        )
    malformed = invalid_ids(ids)
    if malformed:
        return (
            f"malformed requirement id(s) in {TRAILER_KEY}: trailer: "
            f"{', '.join(malformed)}",
        )
    unknown = tuple(i for i in ids if i not in registered_ids(root))
    if unknown:
        return (
            f"{TRAILER_KEY}: trailer names unregistered requirement(s): "
            f"{', '.join(unknown)}",
        )
    return ()


def _hook_main(argv: Sequence[str]) -> int:
    """``python -m coherence.register.claims hook <msg-file>``.

    The commit-msg hook's only logic, so exactly one trailer parser exists in
    the codebase rather than one here and one in shell.
    """
    import subprocess

    if len(argv) < 2 or argv[0] != "hook":
        print("usage: python -m coherence.register.claims hook <msg-file>")
        return 2
    root = Path.cwd()
    try:
        message = Path(argv[1]).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"commit-claim: cannot read commit message file: {exc}")
        return 2
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    errors = check_commit(root, message, staged)
    for error in errors:
        print(f"commit-claim: {error}")
    return 1 if errors else 0


__all__ = [
    "CONFIG_RELPATH",
    "TRAILER_KEY",
    "ClaimsConfig",
    "check_commit",
    "exempting_glob",
    "glob_match",
    "invalid_ids",
    "load_claims_config",
    "parse_sr_trailer",
    "registered_ids",
]


if __name__ == "__main__":  # pragma: no cover - process entry point
    import sys

    sys.exit(_hook_main(sys.argv[1:]))
