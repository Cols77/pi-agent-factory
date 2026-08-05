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


def test_setup_refuses_when_the_port_is_already_serving(tmp_path):
    # Observed live: a second session's Next.js saw 3000 taken, fell back to 3001,
    # and its health check then went green against the FIRST session's app. Nothing
    # could tell "this port answers, but it isn't mine", so the session reported
    # healthy while pointed at someone else's server.
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    squatter = socket.socket()
    squatter.bind(("127.0.0.1", port))
    squatter.listen(1)
    try:
        svc = Service(
            name="web",
            cmd=f"{sys.executable} -m http.server {port}",
            health_url=url,
            ready_timeout=5.0,
        )
        pg = DevServerPlayground([svc], usecases=["u"], browse_url=url, project_root=tmp_path)
        with pytest.raises(RuntimeError, match="already"):
            pg.setup("u")
    finally:
        squatter.close()


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
    port_a = _free_port()
    up_url = f"http://127.0.0.1:{port_a}"  # a real server that DOES come up
    dead = f"http://127.0.0.1:{_free_port()}"  # nothing ever listens here
    svc = Service(
        name="web",
        cmd=f"{sys.executable} -m http.server {port_a}",
        health_url=dead,  # server starts, but its health check points elsewhere → unhealthy
        ready_timeout=1.0,
    )
    pg = DevServerPlayground([svc], usecases=["u"], browse_url=up_url, project_root=tmp_path)
    with pytest.raises(RuntimeError):
        pg.setup("u")
    # The started service must have been torn down by the except-cleanup path.
    time.sleep(0.5)
    assert wait_healthy(up_url, timeout=2) is False


def test_from_config(tmp_path):
    port = _free_port()
    params = {
        "browse_url": f"http://127.0.0.1:{port}",
        "usecases": ["a", "b"],
        "services": [{"name": "web", "cmd": "echo hi", "cwd": "sub"}],
    }
    pg = DevServerPlayground.from_config(params, tmp_path)
    assert pg.list_usecases() == ["a", "b"]
