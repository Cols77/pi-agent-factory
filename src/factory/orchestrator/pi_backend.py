from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
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


def _extract_snippet(line: str) -> str:
    """Extract the "text" field from a single line of Pi's json event stream,
    for live-snippet reporting as output streams in. Returns "" if the line
    isn't a JSON object with a string "text" field. Kept separate from
    parse_pi_json (which still processes the full accumulated stdout at the
    end, unchanged) so that function's tested behavior stays untouched."""
    line = line.strip()
    if not line:
        return ""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if isinstance(event, dict) and isinstance(event.get("text"), str):
        return event["text"]
    return ""


def _has_json_events_without_text_field(stdout: str) -> bool:
    """Best-effort detector for final-review Finding 1+2: the event stream contains
    valid JSON objects, but none of them carry a string "text" field the way
    parse_pi_json expects. That's a strong signal that a JSON field-name assumption
    (e.g. Pi renamed/never used "text" in this event shape) is wrong, rather than
    the agent having genuinely said nothing.

    Kept separate from parse_pi_json (not folded into it) so parse_pi_json's tested
    signature and behavior stay untouched, per the finding.

    Limits: this is a heuristic over line-delimited JSON, not a full understanding
    of Pi's event protocol. A stream that mixes text-bearing and non-text events in
    some other unexpected way, or non-JSON/binary stdout, is not guaranteed to be
    classified correctly — see the finding's "When You're in Over Your Head" note.
    """
    saw_json_object = False
    saw_text_field = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            saw_json_object = True
            if isinstance(event.get("text"), str):
                saw_text_field = True
    return saw_json_object and not saw_text_field


def _build_command(
    prompt: str,
    extension_path: Path,
    provider: str | None,
    model: str | None,
) -> list[str]:
    """Build the `pi` invocation. Pi defaults to the "google" provider when
    --provider/--model are omitted, so an explicit provider/model must be
    passed through to use anything else (e.g. openrouter)."""
    cmd = ["pi", "-p", prompt, "--mode", "json", "--extension", str(extension_path)]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    return cmd


class PiAgentBackend:
    def __init__(
        self,
        repo_root: Path,
        extension_path: Path,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._extension_path = extension_path
        self._provider = provider
        self._model = model

    def run(
        self, role: AgentRole, prompt: str, on_snippet: Callable[[str], None] | None = None
    ) -> AgentResult:
        scope = ROLE_SCOPE[role]
        env = {
            **os.environ,
            "PI_SCOPE_ALLOW": ",".join(scope.allow),
            "PI_SCOPE_BASH": scope.bash,
        }
        cmd = _build_command(prompt, self._extension_path, self._provider, self._model)
        proc = subprocess.Popen(
            cmd, cwd=self._repo_root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if on_snippet is not None:
                snippet = _extract_snippet(line)
                if snippet:
                    on_snippet(snippet[-200:])
        proc.wait()
        stdout = "".join(lines)

        output = parse_pi_json(stdout)
        ok = proc.returncode == 0
        raw = stdout

        # Finding 1+2 (final review): a zero exit code with non-empty stdout that
        # yields an empty parsed output is normally read as "the agent said
        # nothing". If the stdout actually contains valid JSON events that just
        # never carry a "text" field, that reading is wrong — parse_pi_json's
        # field-name assumption doesn't match this event stream. Force ok=False
        # and attach a distinct, diagnosable raw message instead of silently
        # looking identical to a genuinely empty response.
        if (
            ok
            and stdout.strip()
            and not output
            and _has_json_events_without_text_field(stdout)
        ):
            ok = False
            raw = (
                "pi_backend: possible field-name mismatch — subprocess exited 0 with "
                "non-empty stdout containing valid JSON events, but none had a string "
                '"text" field, so parse_pi_json extracted no output. This looks like an '
                "empty agent response but is more likely parse_pi_json's event-shape "
                "assumption being wrong for this stream. Raw stdout:\n" + stdout
            )

        return AgentResult(ok=ok, output=output, raw=raw)
