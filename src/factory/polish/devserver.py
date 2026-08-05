from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from factory.polish.playground import PlaygroundSession


@dataclass(frozen=True)
class Service:
    name: str
    cmd: str
    cwd: str | None = None
    health_url: str | None = None
    ready_timeout: float = 30.0


def wait_healthy(url: str, timeout: float = 30.0, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # local dev URL only, never user-supplied
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True  # any <500 response ⇒ up; 5xx is treated as "not ready yet"
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True  # server answered (even 4xx) ⇒ up
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(interval)
    return False


def port_in_use(url: str) -> bool:
    """True if something is already listening on *url*'s host:port."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        # On Windows with shell=True, use taskkill with /T to kill the tree
        if sys.platform == "win32" and proc.pid is not None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    timeout=5,
                    capture_output=True,
                    check=False,
                )
                proc.wait(timeout=2)
                return
            except (subprocess.TimeoutExpired, OSError):
                pass
        # Fallback: terminate then kill
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except OSError:
        pass


class DevServerPlayground:
    """Config-driven playground: launch a project's dev services, wait for each to
    be healthy, open the browser at ``browse_url``, and stop everything on teardown.
    Nothing here is project-specific — services/ports/commands come from config."""

    def __init__(
        self,
        services: list[Service],
        usecases: list[str],
        browse_url: str,
        *,
        project_root: Path,
    ) -> None:
        self._services = services
        self._usecases = usecases
        self._browse_url = browse_url
        self._root = project_root

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> DevServerPlayground:
        services = [Service(**s) for s in params.get("services", [])]
        return cls(
            services,
            params.get("usecases", []),
            params["browse_url"],
            project_root=project_root,
        )

    def list_usecases(self) -> list[str]:
        return list(self._usecases)

    def setup(self, usecase: str) -> PlaygroundSession:
        # Pre-flight, before starting anything: a health check cannot tell whose
        # server answered. If someone else already owns the port (another polish
        # session, or a hand-started dev server), ours would either fail to bind
        # or silently drift to another port while the check went green against
        # THEIR app -- a session reporting healthy while pointed at the wrong
        # thing. Refuse loudly instead.
        for svc in self._services:
            if svc.health_url and port_in_use(svc.health_url):
                raise RuntimeError(
                    f"service {svc.name!r}: {svc.health_url} is already being served. "
                    "Stop the other dev server or polish session first -- health "
                    "checks cannot tell whose server answered, so continuing would "
                    "report green against the wrong app."
                )

        procs: list[subprocess.Popen] = []

        def _teardown() -> None:
            for p in reversed(procs):
                _kill(p)

        try:
            for svc in self._services:
                cwd = self._root / svc.cwd if svc.cwd else self._root
                procs.append(subprocess.Popen(svc.cmd, shell=True, cwd=str(cwd)))
                if svc.health_url and not wait_healthy(svc.health_url, svc.ready_timeout):
                    raise RuntimeError(
                        f"service {svc.name!r} never became healthy at {svc.health_url}"
                    )
            return PlaygroundSession(
                entrypoints=[self._browse_url],
                describe=f"Use case '{usecase}': {len(self._services)} service(s) up; browse {self._browse_url}.",
                on_teardown=_teardown,
            )
        except BaseException:
            _teardown()  # clean up partially-started services on any failure/interrupt
            raise
