from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from factory.orchestrator.roles import ROLE_SCOPE
from factory.orchestrator.types import AgentResult, AgentRole, InterruptionReason

# The real JSON the agent emits is always the LAST ```json block. A thinking
# block frequently quotes the prompt ("emit ONLY a fenced ```json block"), so
# parsing must anchor on the final occurrence rather than a forward findall,
# which a literal fragment could fool.
_JSON_START = "```json"

# Bounds on how long an agent subprocess may run before the orchestrator kills
# it, so a stalled or runaway agent can't hang the pipeline forever (the
# observed failure: a dev agent streamed 38MB over 35 turns and never
# returned, with no timeout, blocking the whole run and never releasing the
# lock). Overridable via env for ops tuning; a non-positive value disables a
# bound.
_DEFAULT_IDLE_TIMEOUT_S = float(os.environ.get("FACTORY_AGENT_IDLE_TIMEOUT_S", "300"))
_DEFAULT_TOTAL_TIMEOUT_S = float(os.environ.get("FACTORY_AGENT_TOTAL_TIMEOUT_S", "1200"))

# Recursion prevention for the subagent chain. A child pi process that could in
# turn spawn its own agents is a resource leak; the factory runs a fixed
# pipeline depth, and this env guard lets a child's extension see it is already
# a subagent and refuse to spawn a deeper one.
SUBAGENT_DEPTH_ENV = "PI_FACTORY_SUBAGENT_DEPTH"
_SUBAGENT_DEPTH_LIMIT = 2
# The command-line flag that would strip context files from a child -- the
# subagent contract must never use it (children receive the root AGENTS.md).
_NC_FLAGS = ("--no-context-files", "-nc")
_CONTEXT_ERROR_MARKERS = (
    "context length",
    "maximum context",
    "token limit",
    "prompt is too long",
)
_CONTEXT_STOP_REASONS = {"context_limit", "context_length", "max_context", "prompt_too_long"}


def classify_interruption(
    returncode: int | None,
    output: str,
    timed_out_reason: str | None = None,
) -> InterruptionReason | None:
    """Classify only explicit process/provider interruption signals.

    Assistant prose is deliberately excluded: a model discussing a "token limit"
    is not evidence that the provider stopped the process for one.
    """
    if timed_out_reason == "idle":
        return InterruptionReason.IDLE_TIMEOUT
    if timed_out_reason == "total":
        return InterruptionReason.TOTAL_TIMEOUT

    terminal_errors: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            terminal_errors.append(stripped)
            continue
        if not isinstance(event, dict):
            continue
        reason = event.get("reason", event.get("stop_reason"))
        if isinstance(reason, str) and reason.lower() in _CONTEXT_STOP_REASONS:
            return InterruptionReason.CONTEXT_LIMIT
        if event.get("type") in {"error", "agent_error", "provider_error"}:
            for key in ("error", "message", "detail"):
                value = event.get(key)
                if isinstance(value, str):
                    terminal_errors.append(value)
                elif isinstance(value, dict):
                    terminal_errors.extend(str(item) for item in value.values())
    if any(
        marker in message.lower()
        for message in terminal_errors
        for marker in _CONTEXT_ERROR_MARKERS
    ):
        return InterruptionReason.CONTEXT_LIMIT
    if returncode not in (None, 0):
        return InterruptionReason.PROCESS_EXIT
    return None


def _drain_lines(
    stream: Iterable[str],
    idle_timeout: float,
    total_timeout: float,
    on_timeout: Callable[[str], None],
    *,
    now: Callable[[], float] = time.monotonic,
) -> Iterator[str]:
    """Yield lines from *stream*, enforcing two bounds so a stalled or runaway
    agent can't hang the orchestrator forever:

      - idle_timeout: max seconds allowed between consecutive lines (a true
        stall -- the process is alive but producing nothing).
      - total_timeout: max total wall-clock seconds regardless of output (a
        runaway loop that keeps streaming, the observed failure mode).

    On the first breach, ``on_timeout(reason)`` is called once with "idle" or
    "total" and iteration stops. A daemon reader thread decouples the blocking
    pipe read from the timeout wait (Windows cannot ``select()`` on pipes). A
    non-positive timeout disables that particular bound.
    """
    q: queue.Queue = queue.Queue()
    sentinel = object()

    def _reader() -> None:
        try:
            for line in stream:
                q.put(line)
        finally:
            q.put(sentinel)

    threading.Thread(target=_reader, daemon=True).start()
    start = now()
    idle = idle_timeout if idle_timeout and idle_timeout > 0 else None
    total = total_timeout if total_timeout and total_timeout > 0 else None
    while True:
        if total is not None and (now() - start) >= total:
            on_timeout("total")
            return
        wait = idle
        if total is not None:
            remaining = total - (now() - start)
            wait = remaining if wait is None else min(wait, remaining)
        try:
            item = q.get(timeout=wait)
        except queue.Empty:
            # Woke without a line: attribute the breach to whichever bound tripped.
            on_timeout("total" if total is not None and (now() - start) >= total else "idle")
            return
        if item is sentinel:
            return
        yield item


def _assistant_text_blocks(message: object) -> list[str]:
    """Extract text from an assistant message's content blocks.

    Includes both "text" blocks (`{"type":"text","text":...}`) and "thinking"
    blocks (`{"type":"thinking","thinking":...}`). Some providers -- notably
    deepseek via OpenRouter's openai-completions API at a high thinking level --
    put the model's answer, INCLUDING the fenced ```json manifest the factory
    roles are required to emit, inside "thinking" blocks and never produce a
    plain "text" block. Reading only "text" blocks then extracts nothing and the
    stage rejects a perfectly good manifest. Shared by parse_pi_json and
    _has_json_events_without_text_field so both agree on what counts as content."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            out.append(block["text"])
        elif block.get("type") == "thinking" and isinstance(block.get("thinking"), str):
            out.append(block["thinking"])
    return out


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

    # The real JSON is the LAST ```json block the agent emits. A thinking block
    # frequently quotes the prompt ("emit ONLY a fenced ```json block"), which a
    # forward findall can mistake for the real block and swallow the actual
    # closing fence. Search backward from the end so the last ```json always
    # wins; extract to the next ``` fence after it.
    start = full.rfind(_JSON_START)
    if start < 0:
        return {}
    end = full.find("```", start + len(_JSON_START))
    if end < 0:
        return {}
    try:
        return json.loads(full[start + len(_JSON_START):end])
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


def _session_id_in_line(line: str) -> str | None:
    """If *line* is a Pi `session` event, return its id; else None."""
    line = line.strip()
    if not line:
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(event, dict) and event.get("type") == "session":
        sid = event.get("id")
        return sid if isinstance(sid, str) else None
    return None


def parse_session_id(stdout: str) -> str | None:
    """Return the id from Pi's first `session` event, or None."""
    for line in stdout.splitlines():
        sid = _session_id_in_line(line)
        if sid is not None:
            return sid
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
    # The subagent contract is: children run in the project root AND load the
    # root AGENTS.md. No child may pass a flag that strips context files.
    if any(flag in cmd for flag in _NC_FLAGS):
        raise ValueError(
            "pi_backend: refusing a child invocation that disables context files ("
            + ", ".join(_NC_FLAGS)
            + "): children must receive the root AGENTS.md bootstrap."
        )
    return cmd


class PiAgentBackend:
    def __init__(
        self,
        repo_root: Path,
        extension_path: Path,
        provider: str | None = None,
        model: str | None = None,
        idle_timeout_s: float = _DEFAULT_IDLE_TIMEOUT_S,
        total_timeout_s: float = _DEFAULT_TOTAL_TIMEOUT_S,
    ) -> None:
        self._repo_root = repo_root
        self._extension_path = extension_path
        self._provider = provider
        self._model = model
        self._idle_timeout_s = idle_timeout_s
        self._total_timeout_s = total_timeout_s

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        scope = ROLE_SCOPE[role]
        # Recursion bound: a child whose environment is already at the subagent
        # depth limit refuses to spawn yet another pi process. The orchestrator's
        # own per-node agents are sequential at depth 1; only an agent that tries
        # to spawn a sub-subagent inside a session would approach the limit.
        current_depth = int(os.environ.get(SUBAGENT_DEPTH_ENV, "0") or 0)
        if current_depth >= _SUBAGENT_DEPTH_LIMIT:
            return AgentResult(
                ok=False,
                output={},
                raw=(
                    "pi_backend: subagent recursion bound reached "
                    f"(depth {current_depth} >= {_SUBAGENT_DEPTH_LIMIT}); refusing to spawn a deeper child."
                ),
                session_id=None,
                interruption=None,
            )
        env = {
            **os.environ,
            "PI_SCOPE_ALLOW": ",".join(scope.allow),
            "PI_SCOPE_BASH": scope.bash,
            # Propagate the incrementing depth so a child extension can see it
            # is already a subagent and refuse deeper spawning.
            SUBAGENT_DEPTH_ENV: str(current_depth + 1),
        }
        # Use a temp file for long prompts to avoid Windows' command-line length limit
        prompt_file: str | None = None
        try:
            # A newline in an inline -p argument is fatal on Windows: pi is a
            # .cmd shim, so the argv goes through cmd.exe, which treats the
            # newline as a command separator -- everything after the first line
            # (including --mode json) is dropped, pi answers in prose, and the
            # JSON parser finds nothing. Route any multi-line prompt through the
            # @file path regardless of length. (Long role prompts already
            # exceeded the limit, which is why only short multi-line ones broke.)
            if len(prompt) > _CMDLINE_PROMPT_LIMIT or "\n" in prompt:
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
            captured_session_id: str | None = None
            timed_out_reason: str | None = None

            def _on_timeout(reason: str) -> None:
                nonlocal timed_out_reason
                timed_out_reason = reason
                # Kill the runaway/stalled agent so proc.wait() returns and the
                # run can end (and release its lock) instead of hanging forever.
                try:
                    proc.kill()
                except OSError:
                    pass

            for line in _drain_lines(
                proc.stdout, self._idle_timeout_s, self._total_timeout_s, _on_timeout
            ):
                lines.append(line)
                # Capture the pi session id as soon as it is emitted so
                # callers can surface it (e.g. to the dashboard) while the
                # agent is still running, not only after it exits.
                if captured_session_id is None:
                    sid = _session_id_in_line(line)
                    if sid is not None:
                        captured_session_id = sid
                        if on_session_id is not None:
                            on_session_id(sid)
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
        ok = proc.returncode == 0 and timed_out_reason is None
        raw = stdout

        # The agent was killed for exceeding a timeout: report the attempt as a
        # backend failure with a diagnosable reason, so the node treats it as a
        # failed attempt (retry, then escalate) instead of a silent empty result.
        if timed_out_reason is not None:
            raw = (
                f"pi_backend: agent killed after {timed_out_reason} timeout "
                f"(idle={self._idle_timeout_s}s, total={self._total_timeout_s}s) -- it "
                "stalled or ran away without finishing. Treating this attempt as failed.\n"
                "Partial stdout follows:\n" + stdout
            )
            return AgentResult(
                ok=False,
                output=output,
                raw=raw,
                session_id=parse_session_id(stdout),
                interruption=classify_interruption(proc.returncode, stdout, timed_out_reason),
            )

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

        return AgentResult(
            ok=ok,
            output=output,
            raw=raw,
            session_id=parse_session_id(stdout),
            interruption=classify_interruption(proc.returncode, stdout),
        )
