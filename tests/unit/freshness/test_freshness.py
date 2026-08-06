from __future__ import annotations

import os
import subprocess

import pytest

from factory.freshness.evaluate import compare_dependencies
from factory.freshness.fingerprint import (
    fingerprint_file,
    fingerprint_git_tree,
    fingerprint_tool,
    fingerprint_value,
)
from factory.freshness.model import DependencyFingerprint, FreshnessSeverity

pytestmark = pytest.mark.unit


def test_file_fingerprint_uses_content_not_mtime(tmp_path):
    path = tmp_path / "task.md"
    path.write_text("same", encoding="utf-8")
    before = fingerprint_file("task:T-001", path, tmp_path)
    os.utime(path, (1_700_000_000, 1_700_000_000))
    after = fingerprint_file("task:T-001", path, tmp_path)
    assert before == after
    assert before.source == "task.md"


def test_missing_file_has_explicit_fingerprint(tmp_path):
    value = fingerprint_file("requirement:SR-001", tmp_path / "gone.md", tmp_path)
    assert value.digest == "missing"


def test_value_and_tool_fingerprints_are_deterministic():
    assert fingerprint_value("config", {"b": 2, "a": 1}) == fingerprint_value(
        "config", {"a": 1, "b": 2}
    )
    assert fingerprint_tool("validator", "v1").digest.startswith("sha256:")


def test_git_tree_fingerprint_identifies_committed_tree(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    value = fingerprint_git_tree(tmp_path)
    assert value.digest.startswith("git-tree:")
    assert len(value.digest.split(":", 1)[1]) == 40


def fp(name: str, digest: str) -> DependencyFingerprint:
    return DependencyFingerprint(name, "file", digest, name)


def test_compare_reports_changed_missing_and_added_dependencies_in_name_order():
    report = compare_dependencies(
        [fp("a", "old"), fp("b", "same"), fp("c", "gone")],
        [fp("a", "new"), fp("b", "same"), fp("c", "missing"), fp("d", "added")],
        subject="T-001",
        severity_for=lambda name: FreshnessSeverity.BLOCKING if name == "a" else FreshnessSeverity.WARNING,
    )
    assert [(issue.dependency, issue.code) for issue in report.issues] == [
        ("a", "dependency_changed"),
        ("c", "dependency_missing"),
        ("d", "dependency_added"),
    ]
    assert report.ok is False
    assert report.to_dict()["issues"][0]["severity"] == "blocking"


def test_warning_only_report_is_ok():
    report = compare_dependencies(
        [fp("a", "old")],
        [fp("a", "new")],
        subject="T-001",
        severity_for=lambda _name: FreshnessSeverity.WARNING,
    )
    assert report.ok is True
