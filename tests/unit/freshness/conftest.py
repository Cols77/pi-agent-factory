"""Shared isolated Git seeds for the freshness integration tests."""

from __future__ import annotations

from collections.abc import Iterator
import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest


def _private_repo(seed: Path, tmp_path: Path) -> Path:
    """Copy an immutable seed into a test-owned repository."""
    repo = tmp_path / "repo"
    shutil.copytree(seed, repo)
    if not (repo / ".git").is_dir():
        raise AssertionError(f"seed copy is missing its own Git metadata: {repo}")
    return repo


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="session")
def deps_seed(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Build the common dependency repository once for this pytest session."""
    from tests.unit.freshness.test_deps import (
        _code,
        _code_digest,
        _commit_all,
        _diagram,
        _explainer,
        _goal,
        _run_with_deps,
        _sr,
        _sr_digest,
    )

    seed = tmp_path_factory.mktemp("freshness-deps-seed") / "repo"
    seed.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=seed, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=seed, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=seed, check=True)
    _sr(seed)
    _code(seed, "src/navigation/preemption.py")
    _goal(seed)
    c1 = _commit_all(seed, "baseline")
    _run_with_deps(
        seed,
        "RUN-20260816-0100",
        commit=c1,
        sr_ids=["SR-017"],
        goals=["GOAL-NAV-001"],
        files=["src/navigation/preemption.py"],
    )
    _diagram(seed, "DIAG-NAV-009", ["run:RUN-20260816-0100"])
    _explainer(
        seed,
        "NAV-PREEMPTION",
        explains=["SR-017"],
        sr_fps={"SR-017": _sr_digest(seed)},
        code_fps={"src/navigation/preemption.py": _code_digest(seed)},
    )
    _commit_all(seed, "evidence + diagram + explainer")
    before = _tree_digest(seed)
    yield seed
    assert _tree_digest(seed) == before


@pytest.fixture
def repo(tmp_path: Path, deps_seed: Path) -> Path:
    """Provide each dependency test a private copy of the session seed."""
    return _private_repo(deps_seed, tmp_path)


@pytest.fixture(scope="session")
def historical_seed(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Build the historical-preservation repository once per pytest session."""
    from tests.unit.freshness.test_historical_preservation import _seeded_repo

    seed = tmp_path_factory.mktemp("freshness-historical-seed") / "repo"
    seed.mkdir()
    _seeded_repo(seed)
    before = _tree_digest(seed)
    yield seed
    assert _tree_digest(seed) == before


@pytest.fixture
def historical_repo(tmp_path: Path, historical_seed: Path) -> Path:
    """Provide each historical test a private copy of its exact history seed."""
    return _private_repo(historical_seed, tmp_path)
