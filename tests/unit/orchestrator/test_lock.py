import os

import pytest
from factory.orchestrator.lock import (
    AlreadyRunningError,
    acquire_lock,
    is_pid_alive,
    read_lock,
    remove_lock,
    write_lock,
)

pytestmark = pytest.mark.unit


def test_is_pid_alive_true_for_self():
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_false_for_unlikely_pid():
    assert is_pid_alive(999_999_999) is False


def test_write_and_read_lock_round_trip(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=12345, started_at="2026-07-20T10:00:00Z")
    info = read_lock(path)
    assert info is not None
    assert info.pid == 12345
    assert info.started_at == "2026-07-20T10:00:00Z"


def test_read_lock_none_when_missing(tmp_path):
    assert read_lock(tmp_path / "missing.lock") is None


def test_remove_lock_is_idempotent(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=1, started_at="x")
    remove_lock(path)
    assert not path.exists()
    remove_lock(path)  # must not raise on a second call


def test_acquire_lock_succeeds_when_no_existing_lock(tmp_path):
    path = tmp_path / "run.lock"
    acquire_lock(path, pid=os.getpid(), started_at="2026-07-20T10:00:00Z")
    assert read_lock(path).pid == os.getpid()


def test_acquire_lock_raises_when_live_process_holds_it(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=os.getpid(), started_at="2026-07-20T10:00:00Z")
    with pytest.raises(AlreadyRunningError):
        acquire_lock(path, pid=os.getpid() + 1, started_at="2026-07-20T10:05:00Z")


def test_acquire_lock_overwrites_stale_lock(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=999_999_999, started_at="2026-07-20T09:00:00Z")
    acquire_lock(path, pid=os.getpid(), started_at="2026-07-20T10:00:00Z")
    assert read_lock(path).pid == os.getpid()
