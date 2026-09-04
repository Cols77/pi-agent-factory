from __future__ import annotations

import json
import subprocess

import pytest

from coherence.register.claims import ClaimsConfig
from coherence.register.ingest import DivergedRangeError, ingest, ingest_range
from factory.orchestrator.git_ops import SubprocessGitOps

pytestmark = pytest.mark.unit


@pytest.mark.sr("SR-049")
def test_a_claimed_commit_is_ingested_with_its_changed_files(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/a.py", "x = 1\n", "feat: a\n\nSR: SR-050")
    head = SubprocessGitOps().head_commit(git_repo)
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, ClaimsConfig())
    assert len(commits) == 1
    assert commits[0].sr_ids == ("SR-050",)
    assert commits[0].changed_files == ("src/a.py",)


@pytest.mark.sr("SR-049")
def test_a_multi_sr_commit_attributes_its_files_to_every_named_sr(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/b.py", "y = 1\n", "feat: b\n\nSR: SR-050, SR-023")
    head = SubprocessGitOps().head_commit(git_repo)
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, ClaimsConfig())
    assert commits[0].sr_ids == ("SR-050", "SR-023")


@pytest.mark.sr("SR-049")
def test_an_exempt_path_is_recorded_with_the_glob_that_exempted_it(git_repo, commit_file):
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("docs/x.md", "hi\n", "docs: x")
    head = SubprocessGitOps().head_commit(git_repo)
    config = ClaimsConfig(exempt=("docs/**",))
    commits = ingest_range(git_repo, SubprocessGitOps(), base, head, config)
    assert commits[0].exempted == (("docs/x.md", "docs/**"),)
    assert commits[0].sr_ids == ()


@pytest.mark.sr("SR-049")
def test_a_start_commit_that_is_not_an_ancestor_of_head_raises(git_repo, commit_file):
    commit_file("src/c.py", "z = 1\n", "feat: c\n\nSR: SR-050")
    head = SubprocessGitOps().head_commit(git_repo)
    with pytest.raises(DivergedRangeError):
        ingest_range(git_repo, SubprocessGitOps(), "0" * 40, head, ClaimsConfig())


@pytest.mark.sr("SR-049")
def test_ingest_writes_a_manifest_carrying_the_commits(git_repo, commit_file):
    commit_file("src/d.py", "d = 1\n", "feat: d\n\nSR: SR-050")
    path = ingest(git_repo)
    assert path is not None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert [c["sha"] for c in manifest["commits"]]
    assert "src/d.py" in manifest["implementation"]["changed_files"]


@pytest.mark.sr("SR-049")
def test_a_second_ingest_of_the_same_range_writes_nothing(git_repo, commit_file):
    commit_file("src/e.py", "e = 1\n", "feat: e\n\nSR: SR-050")
    assert ingest(git_repo) is not None
    assert ingest(git_repo) is None


@pytest.mark.sr("SR-049")
def test_an_ingested_manifest_survives_a_squash_of_the_commits_it_recorded(
    git_repo, commit_file
):
    """The load-bearing test of the checkpoint model.

    Commits are an input consumed once, never a durable ledger: after
    ingestion the manifest is authoritative and the commits no longer matter.
    That is the whole reason no workflow has to be forbidden -- so it is
    asserted directly, against a real squash that destroys the ingested shas.
    """
    base = SubprocessGitOps().head_commit(git_repo)
    commit_file("src/g.py", "g = 1\n", "feat: g\n\nSR: SR-050")
    commit_file("src/h.py", "h = 1\n", "feat: h\n\nSR: SR-050")
    written = ingest(git_repo)
    assert written is not None
    before = json.loads(written.read_text(encoding="utf-8"))
    assert len(before["commits"]) == 2

    subprocess.run(["git", "reset", "--soft", base], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feat: g and h squashed\n\nSR: SR-050"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    after = json.loads(written.read_text(encoding="utf-8"))
    assert after == before, "the manifest is immutable; a squash cannot touch it"
    squashed_out = {c["sha"] for c in before["commits"]}
    for sha in squashed_out:
        assert (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                cwd=git_repo,
                capture_output=True,
            ).returncode
            != 0
        ), "the fixture must actually have orphaned the ingested commits"
    assert {p for c in after["commits"] for p in c["changed_files"]} == {"src/g.py", "src/h.py"}


@pytest.mark.sr("SR-049")
def test_the_epoch_wins_over_an_earlier_recorded_checkpoint(git_repo, commit_file):
    """At adoption the evidence store already holds manifests whose result
    commits predate every trailer in the repository. Resuming from the newest
    of those would re-walk the whole pre-adoption history -- recording dozens
    of unclaimed commits and, worse, unioning their paths into the manifest's
    own `changed_files`, which is what the register-wide `unaccounted` review
    reads. The epoch is the floor that stops it: no claim is expected at or
    before that commit, so ingestion never starts earlier than it.
    """
    commit_file("src/pre.py", "p = 1\n", "feat: pre-adoption")
    first = ingest(git_repo)
    assert first is not None, "the fixture needs a recorded checkpoint to override"

    commit_file("src/skipped.py", "s = 1\n", "feat: also pre-adoption")
    epoch = commit_file("src/epoch.py", "e = 1\n", "chore: adoption point")
    commit_file("src/claimed.py", "c = 1\n", "feat: claimed\n\nSR: SR-050")

    (git_repo / ".factory").mkdir(exist_ok=True)
    (git_repo / ".factory" / "trace-claims.yaml").write_text(
        f'epoch: "{epoch}"\nexempt: []\n', encoding="utf-8"
    )

    written = ingest(git_repo)
    assert written is not None
    manifest = json.loads(written.read_text(encoding="utf-8"))
    assert manifest["start_commit"] == epoch
    assert [c["subject"] for c in manifest["commits"]] == ["feat: claimed"]
    assert "src/skipped.py" not in manifest["implementation"]["changed_files"]


@pytest.mark.sr("SR-049")
def test_a_checkpoint_past_the_epoch_is_not_dragged_back_to_it(git_repo, commit_file):
    """The epoch is a floor, not an anchor. Once ingestion has checkpointed
    past it, resuming from the epoch again would re-ingest everything between
    -- so the recorded checkpoint wins as soon as it is at or beyond it."""
    epoch = commit_file("src/base.py", "b = 1\n", "chore: adoption point")
    (git_repo / ".factory").mkdir(exist_ok=True)
    (git_repo / ".factory" / "trace-claims.yaml").write_text(
        f'epoch: "{epoch}"\nexempt: []\n', encoding="utf-8"
    )
    commit_file("src/first.py", "f = 1\n", "feat: first\n\nSR: SR-050")
    assert ingest(git_repo) is not None

    commit_file("src/second.py", "s = 1\n", "feat: second\n\nSR: SR-050")
    written = ingest(git_repo)
    assert written is not None
    manifest = json.loads(written.read_text(encoding="utf-8"))
    assert [c["subject"] for c in manifest["commits"]] == ["feat: second"]


@pytest.mark.sr("SR-049")
def test_an_ingest_manifest_records_no_task_rather_than_inventing_one(git_repo, commit_file):
    commit_file("src/f.py", "f = 1\n", "feat: f\n\nSR: SR-050")
    written = ingest(git_repo)
    assert written is not None
    manifest = json.loads(written.read_text(encoding="utf-8"))
    assert "task_id" not in manifest
    assert "task" not in manifest["inputs"]
