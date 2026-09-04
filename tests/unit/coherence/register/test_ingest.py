from __future__ import annotations

import json

import pytest

from coherence.register.claims import ClaimsConfig
from coherence.register.ingest import DivergedRangeError, ingest, ingest_range
from factory.orchestrator.git_ops import SubprocessGitOps

pytestmark = pytest.mark.unit


@pytest.mark.sr("SR-054")
def test_a_claimed_commit_is_ingested_with_its_changed_files(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/a.py", "x = 1\n", "feat: a\n\nSR: SR-050")
    head = SubprocessGitOps().head_commit(git_repo)
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, ClaimsConfig())
    assert len(commits) == 1
    assert commits[0].sr_ids == ("SR-050",)
    assert commits[0].changed_files == ("src/a.py",)


@pytest.mark.sr("SR-054")
def test_a_multi_sr_commit_attributes_its_files_to_every_named_sr(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/b.py", "y = 1\n", "feat: b\n\nSR: SR-050, SR-023")
    head = SubprocessGitOps().head_commit(git_repo)
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, ClaimsConfig())
    assert commits[0].sr_ids == ("SR-050", "SR-023")


@pytest.mark.sr("SR-054")
def test_an_exempt_path_is_recorded_with_the_glob_that_exempted_it(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("docs/x.md", "hi\n", "docs: x")
    head = SubprocessGitOps().head_commit(git_repo)
    config = ClaimsConfig(exempt=("docs/**",))
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, config)
    assert commits[0].exempted == (("docs/x.md", "docs/**"),)
    assert commits[0].sr_ids == ()


@pytest.mark.sr("SR-054")
def test_a_start_commit_that_is_not_an_ancestor_of_head_raises(git_repo, commit_file):
    commit_file("src/c.py", "z = 1\n", "feat: c\n\nSR: SR-050")
    head = SubprocessGitOps().head_commit(git_repo)
    with pytest.raises(DivergedRangeError):
        ingest_range(git_repo, SubprocessGitOps(), "0" * 40, head, ClaimsConfig())


@pytest.mark.sr("SR-054")
def test_ingest_writes_a_manifest_carrying_the_commits(git_repo, commit_file):
    commit_file("src/d.py", "d = 1\n", "feat: d\n\nSR: SR-050")
    path = ingest(git_repo)
    assert path is not None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert [c["sha"] for c in manifest["commits"]]
    assert "src/d.py" in manifest["implementation"]["changed_files"]


@pytest.mark.sr("SR-054")
def test_a_second_ingest_of_the_same_range_writes_nothing(git_repo, commit_file):
    commit_file("src/e.py", "e = 1\n", "feat: e\n\nSR: SR-050")
    assert ingest(git_repo) is not None
    assert ingest(git_repo) is None


@pytest.mark.sr("SR-054")
def test_an_ingest_manifest_records_no_task_rather_than_inventing_one(git_repo, commit_file):
    commit_file("src/f.py", "f = 1\n", "feat: f\n\nSR: SR-050")
    written = ingest(git_repo)
    assert written is not None
    manifest = json.loads(written.read_text(encoding="utf-8"))
    assert "task_id" not in manifest
    assert "task" not in manifest["inputs"]
