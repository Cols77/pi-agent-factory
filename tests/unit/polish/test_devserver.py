import socket
import sys
import time

import pytest
from factory.polish.devserver import DevServerPlayground, Service, wait_healthy
from factory.polish.playground import Playground

pytestmark = pytest.mark.unit


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_is_a_playground(tmp_path):
    pg = DevServerPlayground([], ["u"], "http://x", project_root=tmp_path)
    assert isinstance(pg, Playground)
    assert pg.list_usecases() == ["u"]


def test_setup_starts_service_then_teardown_stops_it(tmp_path):
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    svc = Service(
        name="web",
        cmd=f"{sys.executable} -m http.server {port}",
        health_url=url,
        ready_timeout=15.0,
    )
    pg = DevServerPlayground([svc], usecases=["u"], browse_url=url, project_root=tmp_path)
    session = pg.setup("u")
    try:
        assert session.entrypoints == [url]
        assert wait_healthy(url, timeout=5)  # server is up
    finally:
        session.teardown()
    # After teardown the port should stop answering within a moment.
    time.sleep(0.5)
    assert wait_healthy(url, timeout=2) is False


def test_setup_raises_and_cleans_up_on_unhealthy(tmp_path):
    dead = f"http://127.0.0.1:{_free_port()}"  # nothing listening
    svc = Service(
        name="web",
        cmd=f'{sys.executable} -c "import time;time.sleep(30)"',
        health_url=dead,
        ready_timeout=1.0,
    )
    pg = DevServerPlayground([svc], usecases=["u"], browse_url=dead, project_root=tmp_path)
    with pytest.raises(RuntimeError):
        pg.setup("u")


def test_from_config(tmp_path):
    port = _free_port()
    params = {
        "browse_url": f"http://127.0.0.1:{port}",
        "usecases": ["a", "b"],
        "services": [{"name": "web", "cmd": "echo hi", "cwd": "sub"}],
    }
    pg = DevServerPlayground.from_config(params, tmp_path)
    assert pg.list_usecases() == ["a", "b"]
