from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from factory.orchestrator.roles import ROLE_SCOPE
from factory.orchestrator.types import AgentResult, AgentRole

_JSON_BLOCK = re.compile(r"```json\s*(.*?)```", re.DOTALL)


def _assistant_text_blocks(message: object) -> list[str]:
    """Extract text block contents from a message dict with role "assistant".
    Returns [] if message isn't an assistant message dict with a text-bearing
    content list. Shared by parse_pi_json and _has_json_events_without_text_field
    so both agree on exactly what "the text field" means for Pi's real v3
    event stream (see module docstring note below for the format itself)."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]


def parse_pi_json(stdout: str) -> dict:
    """Reconstruct assistant text from Pi's json event stream, return last ```json block.

    Pi's --mode json emits one "message_end" event per complete message
    (fired once, not per delta), shaped like:
      {"type": "message_end", "message": {"role": "assistant",
       "content": [{"type": "text", "text": "..."}], ...}}
    Live incremental deltas arrive separately as "message_update" events
    (see _extract_snippet) and are not used here, since message_end's
    content already carries each message's complete final text.
    """
    text_parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "message_end":
            text_parts.extend(_assistant_text_blocks(event.get("message")))
    full = "".join(text_parts)
    blocks = _JSON_BLOCK.findall(full)
    if not blocks:
        return {}
    try:
        return json.loads(blocks[-1])
    except json.JSONDecodeError:
        return {}


def _extract_snippet(line: str) -> str:
    """Extract the incremental text delta from a single line of Pi's json
    event stream, for live-snippet reporting as output streams in. Returns ""
    unless the line is a "message_update" event carrying a "text_delta"
    assistantMessageEvent, e.g.:
      {"type": "message_update",
       "assistantMessageEvent": {"type": "text_delta", "delta": "chunk"}, ...}
    Kept separate from parse_pi_json (which reads complete messages from
    message_end events, not deltas) so that function's tested behavior stays
    untouched."""
    line = line.strip()
    if not line:
        return ""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if not isinstance(event, dict) or event.get("type") != "message_update":
        return ""
    assistant_event = event.get("assistantMessageEvent")
    if not isinstance(assistant_event, dict) or assistant_event.get("type") != "text_delta":
        return ""
    delta = assistant_event.get("delta")
    return delta if isinstance(delta, str) else ""


def _has_json_events_without_text_field(stdout: str) -> bool:
    """Best-effort detector for final-review Finding 1+2: the event stream contains
    valid JSON objects, but none of them carry assistant text the way
    parse_pi_json expects (a "message_end" event with an assistant message's
    text content blocks). That's a strong signal that a JSON field-name
    assumption (e.g. Pi changed its event shape) is wrong, rather than the
    agent having genuinely said nothing.

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
            if event.get("type") == "message_end" and _assistant_text_blocks(event.get("message")):
                saw_text_field = True
    return saw_json_object and not saw_text_field


def parse_session_id(stdout: str) -> str | None:
    """Return the id from Pi's first `session` event, or None."""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "session":
            sid = event.get("id")
            return sid if isinstance(sid, str) else None
    return None


# Windows cmd.exe has an 8191-char command-line limit. Since pi is a .cmd
# wrapper, any invocation over this limit fails with ENOENT/"command line too long".
# Prompts beyond this threshold are written to a temp file and passed via
# pi's @file syntax instead of -p.
_CMDLINE_PROMPT_LIMIT = 4000  # chars — safe margin below 8191


def _build_command(
    prompt: str,
    extension_path: Path,
    provider: str | None,
    model: str | None,
    *,
    prompt_file: str | None = None,
) -> list[str]:
    """Build the `pi` invocation. If prompt_file is given, use @file syntax
    instead of -p to avoid Windows command-line length limits."""
    pi_bin = shutil.which("pi") or "pi"
    if prompt_file is not None:
        cmd = [pi_bin, "-p", f"@{prompt_file}", "--mode", "json", "--extension", str(extension_path)]
    else:
        cmd = [pi_bin, "-p", prompt, "--mode", "json", "--extension", str(extension_path)]
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
        # Use a temp file for long prompts to avoid Windows' command-line length limit
        prompt_file: str | None = None
        try:
            if len(prompt) > _CMDLINE_PROMPT_LIMIT:
                fd, prompt_file = tempfile.mkstemp(suffix=".md", prefix="pi_prompt_")
                os.write(fd, prompt.encode("utf-8"))
                os.close(fd)
            cmd = _build_command(
                prompt, self._extension_path, self._provider, self._model,
                prompt_file=prompt_file,
            )
            # stdin=DEVNULL: without this, Pi's CLI blocks forever in its own
            # readPipedStdin() waiting for stdin EOF whenever this process
            # inherits a long-lived open pipe (e.g. launchInteractiveReview's
            # human-review handshake keeps the orchestrator's own stdin open).
            proc = subprocess.Popen(
                cmd, cwd=self._repo_root, env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
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
        finally:
            if prompt_file is not None:
                try:
                    os.unlink(prompt_file)
                except OSError:
                    pass

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

        return AgentResult(ok=ok, output=output, raw=raw, session_id=parse_session_id(stdout))
