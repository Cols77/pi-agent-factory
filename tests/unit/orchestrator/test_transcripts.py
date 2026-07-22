from __future__ import annotations

import pytest
from factory.orchestrator.transcripts import write_role_transcript

pytestmark = pytest.mark.unit


def test_writes_transcript_to_the_expected_path(tmp_path):
    path = write_role_transcript(tmp_path, "dev", 2, "raw agent output")
    assert path == tmp_path / "dev-attempt2.log"
    assert path.read_text(encoding="utf-8") == "raw agent output"


def test_creates_intermediate_directories(tmp_path):
    target = tmp_path / "nested" / "dir"
    write_role_transcript(target, "review", 1, "x")
    assert target.is_dir()


def test_separate_attempts_do_not_overwrite_each_other(tmp_path):
    write_role_transcript(tmp_path, "dev", 1, "first attempt")
    write_role_transcript(tmp_path, "dev", 2, "second attempt")
    assert (tmp_path / "dev-attempt1.log").read_text(encoding="utf-8") == "first attempt"
    assert (tmp_path / "dev-attempt2.log").read_text(encoding="utf-8") == "second attempt"
