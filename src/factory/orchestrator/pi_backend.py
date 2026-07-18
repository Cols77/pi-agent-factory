from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from factory.orchestrator.roles import ROLE_SCOPE
from factory.orchestrator.types import AgentResult, AgentRole

_JSON_BLOCK = re.compile(r"```json\s*(.*?)```", re.DOTALL)


def parse_pi_json(stdout: str) -> dict:
    """Reconstruct assistant text from Pi's json event stream, return last ```json block."""
    text_parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get("text"), str):
            text_parts.append(event["text"])
    full = "".join(text_parts)
    blocks = _JSON_BLOCK.findall(full)
    if not blocks:
        return {}
    try:
        return json.loads(blocks[-1])
    except json.JSONDecodeError:
        return {}


class PiAgentBackend:
    def __init__(self, repo_root: Path, extension_path: Path, model: str | None = None) -> None:
        self._repo_root = repo_root
        self._extension_path = extension_path
        self._model = model

    def run(self, role: AgentRole, prompt: str) -> AgentResult:
        scope = ROLE_SCOPE[role]
        env = {
            **os.environ,
            "PI_SCOPE_ALLOW": ",".join(scope.allow),
            "PI_SCOPE_BASH": scope.bash,
        }
        cmd = ["pi", "-p", prompt, "--mode", "json", "--extension", str(self._extension_path)]
        proc = subprocess.run(
            cmd, cwd=self._repo_root, env=env, capture_output=True, text=True
        )
        return AgentResult(ok=proc.returncode == 0, output=parse_pi_json(proc.stdout), raw=proc.stdout)
