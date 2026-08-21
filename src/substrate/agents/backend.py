from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from substrate.agents.model import AgentResult, InterruptionReason, ScopeLike

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

# Liveness-aware idle (T-029): a silent subprocess is not immediately killed. A
# quiet-but-working agent (long plan-authoring burst, model "thinking", a child
# writing deliverables while saying nothing) must not be mistaken for a stalled
# one. A live keeper counts consecutive silent idle windows; output lines and a
# file-write heartbeat reset that count, and only after *more than* the grace
# budget of silent windows does an idle kill fire. Grace is kept below the
# total/idle ratio so a genuine stall is killed by the idle bound (reachable)
# rather than always running up to the total runaway ceiling. Mirrors the TS
# SUBAGENT_IDLE_GRACE_BREACHES / SUBAGENT_TIMEOUT_MS in
# pi-ext/factory-watch/src/subagent-tool.ts.
_IDLE_GRACE_BREACHES = 2
# Depth of the file-heartbeat probe (bounds recursion to stay cheap).
_LIVENESS_DEPTH = 4
# Deliverable directories probed for a fresh write; a file written under any of
# these since the last live signal keeps a silent child alive. Missing dirs are
# simply ignored by the probe.
_DEFAULT_LIVENESS_DIRS = ("docs", "plans", "tasks", "requirements", ".pi")

# Process-tree teardown (PART-2a of T-029): once a kill fires, the child gets
# SIGTERM first and its process group is given up to _KILL_GRACE_TOTAL_S to
# exit (grace-polled every _KILL_GRACE_STEP_S) before an escalated SIGKILL.
# Kept small so teardown itself is never the hang it exists to break.
_KILL_GRACE_STEP_S = 0.25
_KILL_GRACE_TOTAL_S = 2.0
# Bounded post-SIGKILL poll: after the grace budget, escalation polls the
# group at most this many steps so an unreapable/zombie group cannot spin
# teardown forever (T-029: teardown must never be the hang it exists to break).
_KILL_POLL_BUDGET = 8
# Resolved with a fallback because SIGKILL purely/SIGTERM are not defined on
# Windows; the tree-kill path is POSIX-only, but the module must still import
# there. getattr (not direct access) keeps pyright's Windows stubs quiet.
_SIG_TERM = getattr(signal, "SIGTERM", 15)
_SIG_KILL = getattr(signal, "SIGKILL", 9)

# Transient spawn retry (PART-2b of T-029): a launch that fails to START the
# process at all (missing `pi` bin / FileNotFoundError-ENOENT, or a one-off race)
# is retried a bounded number of times with a small backoff before the spawn is
# reported as failed. NEVER retried: a child that started and then stalled or
# timed out -- that failure is a timeout kill handled by _on_timeout and must
# stay one-shot. Overridable via env for ops tuning.
_SPAWN_RETRIES = int(os.environ.get("FACTORY_AGENT_SPAWN_RETRIES", "2"))
_SPAWN_BACKOFF_S = float(os.environ.get("FACTORY_AGENT_SPAWN_BACKOFF_S", "0.25"))

# Output hard-cap (PART-2b of T-029): a pathological child streaming output
# unboundedly must not be allowed to flood memory. Two ceilings coexist:
#   _MAX_OUTPUT_TOTAL_CHARS     - the whole run's cumulative stdout ceiling.
#                                 Exceeding it marks the run as truncated (a
#                                 short note is attached to the returned raw).
#   _MAX_OUTPUT_RETAINED_CHARS - a rolling window that keeps only the TAIL of
#                                 the stream (the final manifest-bearing segment
#                                 must survive so parse_pi_json still reads the
#                                 last ```json block). A non-positive value
#                                 disables its bound, mirroring the timeouts.
_MAX_OUTPUT_TOTAL_CHARS = int(
    os.environ.get("FACTORY_AGENT_OUTPUT_TOTAL_CAP_CHARS", "2000000")
)
_MAX_OUTPUT_RETAINED_CHARS = int(
    os.environ.get("FACTORY_AGENT_OUTPUT_RETAINED_CAP_CHARS", "1000000")
)
# A single pathological event line must never be retained whole, or it defeats
# both the total and retained caps (mirrors the TS MAX_EVENT_LINE_CHARS guard:
# an overlong line is truncated to this width, keeping the tail so a trailing
# manifest-bearing fragment survives).
_MAX_OUTPUT_LINE_CAP_CHARS = int(
    os.environ.get("FACTORY_AGENT_OUTPUT_LINE_CAP_CHARS", "100000")
)


_T = TypeVar("_T")


def _retry_launch(
    factory: Callable[[], _T],
    *,
    retries: int = _SPAWN_RETRIES,
    delay: float = _SPAWN_BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
) -> _T:
    """Run *factory* (a Popen launcher) up to *retries*+1 times, sleeping
    *delay* between failures, returning the first success. Only launch
    failures -- ``OSError`` raised by the call itself, i.e. the process never
    started -- are retried. After the budget is exhausted the last error is
    re-raised so the caller reports a genuinely-failed spawn; a process that
    started is never relaunched by this helper (the retry budget is exactly
    *retries* follow-ups to an initial attempt, never more).
    """
    last_error: OSError | None = None
    for attempt in range(max(0, retries) + 1):
        try:
            return factory()
        except OSError as error:
            last_error = error
            if attempt < retries:
                sleep(delay)
    assert last_error is not None
    raise last_error


def _retain_line_capped(
    retained: list[str],
    retained_chars: int,
    limit: int,
    line: str,
    line_cap: int = _MAX_OUTPUT_LINE_CAP_CHARS,
) -> int:
    """Append *line* to the rolling retention tail, dropping the OLDEST lines
    once total retained chars exceed *limit*.

    Two guards keep a pathological child from flooding memory:
      - a single oversized *line* (over *line_cap*) is truncated to its tail and
        kept with a marker, so one giant event cannot be retained whole and
        multiplied across the cumulative counters;
      - the rolling window drops the OLDEST full lines once aggregate retained
        chars exceed *limit*, always keeping the newest line (the final
        manifest-bearing segment must survive for parse_pi_json).
    A non-positive *limit* disables dropping (unbounded). Returns the updated
    retained-chars count.
    """
    if line_cap > 0 and len(line) > line_cap:
        retained.append("<snip>" + line[-line_cap:])
        retained_chars += line_cap + len("<snip>")
    else:
        retained.append(line)
        retained_chars += len(line)
    if limit > 0:
        while retained_chars > limit and len(retained) > 1:
            dropped = retained.pop(0)
            retained_chars -= len(dropped)
    return retained_chars


def _output_truncated_note(total_chars: int) -> str:
    """Short one-line note attached when a run's cumulative stdout exceeds the
    hard cap (so the retained tail is not mistaken for the whole stream)."""
    return (
        "pi_backend: subprocess output truncated at the hard cap "
        f"({_MAX_OUTPUT_TOTAL_CHARS} total chars; emitted {total_chars}). "
        f"Keeping only the trailing {_MAX_OUTPUT_RETAINED_CHARS} chars as "
        "raw."
    )


class _IdleKeeper:
    """Pure strike/breach keeper over consecutive silent idle windows.

    Mirrors the TS contract of ``createIdleKeeper``: ``note_live()`` resets the
    breach count; ``on_elapsed(probe_result)`` resets it when a liveness probe
    reports fresh file progress, otherwise increments, and only returns
    "kill" once the breach count *exceeds* the grace budget. The caller owns
    the idle-window cadence; this class owns no timer. The clock is injectable
    (default ``time.monotonic``) for deterministic tests.
    """

    def __init__(
        self,
        grace: int = _IDLE_GRACE_BREACHES,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._grace = max(1, grace)
        self._now = now
        self._breaches = 0
        self._since = now()

    def note_live(self) -> None:
        """Record liveness (any child output); reset the breach count."""
        self._breaches = 0
        self._since = self._now()

    def on_elapsed(self, probe_result: bool = False) -> str:
        """A full idle window elapsed. Returns "keep-running" or "kill"."""
        t = self._now()
        if probe_result:
            # File-heartbeat: the child is still writing deliverables.
            self._breaches = 0
            self._since = t
            return "keep-running"
        self._breaches += 1
        # Kill once MORE than grace silent windows have elapsed (grace windows
        # are permitted; the breach count is the incident count, so it must
        # exceed grace).
        if self._breaches > self._grace:
            return "kill"
        return "keep-running"

    @property
    def breaches(self) -> int:
        return self._breaches

    @property
    def since(self) -> float:
        return self._since


def _probe_dir(directory: str, since_seconds: float, depth: int) -> bool:
    """Best-effort mtime probe over one directory tree (depth-bounded)."""
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return False  # missing/unreadable dir -> no signal
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            st = entry.stat()
        except OSError:
            continue  # transient stat race -> try next
        if st.st_mtime > since_seconds:
            return True
        if entry.is_dir() and depth > 0 and _probe_dir(entry.path, since_seconds, depth - 1):
            return True
    return False


def _probe_file_heartbeat(
    dirs: Iterable[str],
    since_seconds: float,
    max_depth: int = _LIVENESS_DEPTH,
) -> bool:
    """True when any file under any of *dirs* has an mtime newer than
    *since_seconds* (a fresh deliverable write). Early-returns on first hit and
    ignores missing dirs; mirrors ``probeFileHeartbeat`` in subagent-tool.ts.
    """
    for directory in dirs:
        if directory and _probe_dir(directory, since_seconds, max_depth):
            return True
    return False

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
    idle_grace: int = _IDLE_GRACE_BREACHES,
    liveness_root: str | os.PathLike[str] | None = None,
    liveness_dirs: Iterable[str] = _DEFAULT_LIVENESS_DIRS,
    liveness_probe: Callable[[float], object] | None = None,
    wall_clock: Callable[[], float] = time.time,
) -> Iterator[str]:
    """Yield lines from *stream*, enforcing two bounds so a stalled or runaway
    agent can't hang the orchestrator forever:

      - idle_timeout: max seconds between consecutive lines; a silent window
        only grades as a probation incident (see *idle_grace*), so a
        quiet-but-writing child is not killed immediately.
      - total_timeout: max total wall-clock seconds regardless of output (a
        runaway loop that keeps streaming, the observed failure mode).

    The idle bound is liveness-aware (T-029): output lines and a fresh
    deliverable-file write (probed under *liveness_root* + *liveness_dirs*, or a
    fully injected ``liveness_probe``) reset the breach counter; only when it
    exceeds *idle_grace* consecutive silent windows does ``on_timeout("idle")``
    fire. The total bound is untouched and still kills a runaway. On timeout,
    ``on_timeout(reason)`` is called once with "idle" or "total" and iteration
    stops. A daemon reader thread decouples the blocking pipe read from the
    timeout wait (Windows cannot ``select()`` on pipes). A non-positive timeout
    disables that particular bound.
    """
    keeper = _IdleKeeper(grace=idle_grace, now=now)
    # Watermark in the file-mtime clock domain (usually wall-clock): advanced
    # every time the child emits output so a deliverable written after that
    # counts as an alive signal. Kept separate from ``keeper.since`` (which uses
    # the injectable *now* clock) so a real filesystem probe still compares
    # against genuine mtimes.
    probe_since = wall_clock()

    def _probe(since: float) -> bool:
        if liveness_probe is not None:
            return bool(liveness_probe(since))
        if liveness_root is None:
            return False
        watch = [os.fspath(Path(liveness_root) / name) for name in liveness_dirs]
        return _probe_file_heartbeat(watch, since)

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
            # A silent window elapsed. The total bound is the hard runaway
            # ceiling; a silent window alone never kills. Idle is
            # liveness-aware: a fresh file write resets the breach, and only
            # once the grace budget of silent windows is exceeded does an idle
            # kill fire.
            if total is not None and (now() - start) >= total:
                on_timeout("total")
                return
            heartbeat = _probe(probe_since)
            if keeper.on_elapsed(heartbeat) == "kill":
                on_timeout("idle")
                return
            if heartbeat:
                probe_since = wall_clock()
            continue
        if item is sentinel:
            return
        keeper.note_live()
        probe_since = wall_clock()
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


def _pid_is_alive(pid: int) -> bool:
    """POSIX liveness probe: os.kill(pid, 0) delivers no signal but raises if
    the pid is gone. Any error (missing, no-permission) reads as dead/unreachable.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


def _child_reaped(proc: object) -> bool:
    """True only once the O/S has *reaped* the direct child (its pid is no
    longer a live zombie). ``proc.poll()`` reaps a finished direct child on
    POSIX, so a non-None returncode means the leader is gone. This matters
    because ``os.kill(pid, 0)`` on a zombie SUCCEEDS -- a reaped-unaware alive
    probe would spin forever after a TERM/SIGKILL, turning teardown into the
    exact hang T-029 exists to break.
    """
    poll = getattr(proc, "poll", None)
    if callable(poll):
        try:
            return poll() is not None
        except (OSError, ValueError):
            return False
    return False


def _kill_process_tree(
    proc: object,
    *,
    grace_step: float = _KILL_GRACE_STEP_S,
    grace_total: float = _KILL_GRACE_TOTAL_S,
    sleep: Callable[[float], None] = time.sleep,
    alive: Callable[[int], bool] | None = None,
    killpg: Callable[[int, int], None] | None = None,
    poll_budget: int = _KILL_POLL_BUDGET,
) -> None:
    """Kill *proc*'s ENTIRE subprocess tree, not just the direct child.

    A child pi may spawn grandchildren (shell, other tools) that outlive a
    single direct ``proc.kill()``, leaking processes. On POSIX the child is
    launched as a process-group leader (start_new_session=True in PiAgentBackend
    .run), so the whole tree shares the group id == child pid: send SIGTERM to
    the group, give it *grace_total* to exit (probed every *grace_step*), then
    escalate to SIGKILL and poll (bounded by *poll_budget*) until the group is
    gone. Windows has no killpg semantics, so it falls back to direct
    ``proc.kill()``.

    Every teardown knob (sleep, alive probe, group kill) is injectable so the
    helper is unit-testable without real processes. An OSError from any cull
    step is swallowed -- a failed teardown must never break the run -- mirroring
    the prior ``try: proc.kill() except OSError: pass`` semantics. The default
    ``alive`` probe reaps the leader first (``_child_reaped``), and the post-
    SIGKILL poll is bounded, so a zombie leader cannot spin teardown forever
    (T-029: teardown must never itself be the hang it exists to break).
    """
    raw_pid = getattr(proc, "pid", None)
    try:
        pid = int(raw_pid) if raw_pid is not None else 0
    except (TypeError, ValueError):
        pid = 0
    kill = getattr(proc, "kill", None)
    # The leader is the direct child on this host, so the default exit probe
    # reaps it first (a zombie leader reads as dead) and only then falls back
    # to the group-liveness probe. An explicitly injected ``alive`` wins.
    if alive is None:

        def _alive_reaped(pid: int) -> bool:
            # True ONLY while the process is genuinely running: the child has
            # NOT been reaped (proc.poll() is None -> not a zombie) AND the pid
            # is still reachable. This is the boolean the callers consume as
            # "still alive" -- do not invert it (a reaped child or a dead pid
            # must read as dead, or the SIGKILL escalation never fires).
            return not _child_reaped(proc) and _pid_is_alive(pid)

        alive = _alive_reaped
    try:
        if pid <= 0 or sys.platform != "posix":
            # No usable group (no leader pid), or a platform without killpg:
            # best-effort direct kill.
            if callable(kill):
                kill()
            return
        group_kill = killpg if killpg is not None else os.killpg
        # POSIX: signal the whole group. TERM raises if the group never
        # existed (already exited) -- nothing left to cull.
        try:
            group_kill(pid, _SIG_TERM)
        except (ProcessLookupError, OSError):
            return
        elapsed = 0.0
        while elapsed < grace_total and alive(pid):
            sleep(grace_step)
            elapsed += grace_step
        if alive(pid):
            # Still alive after the TERM grace budget: escalate to a hard kill,
            # then poll (bounded) until the group is actually gone.
            try:
                group_kill(pid, _SIG_KILL)
            except (ProcessLookupError, OSError):
                pass
            for _ in range(poll_budget):
                if not alive(pid):
                    return
                sleep(grace_step)
    except OSError:
        # A stale/dead group or transient cull failure: never let teardown
        # raise back into the orchestrator's timeout/run path.
        pass


class PiAgentBackend:
    def __init__(
        self,
        repo_root: Path,
        extension_path: Path,
        scope_for: Callable[[str], ScopeLike],
        provider: str | None = None,
        model: str | None = None,
        idle_timeout_s: float = _DEFAULT_IDLE_TIMEOUT_S,
        total_timeout_s: float = _DEFAULT_TOTAL_TIMEOUT_S,
        idle_grace: int = _IDLE_GRACE_BREACHES,
        liveness_root: Path | None = None,
        liveness_dirs: Iterable[str] = _DEFAULT_LIVENESS_DIRS,
        liveness_probe: Callable[[float], object] | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._extension_path = extension_path
        # Injected role -> scope lookup (ScopeLike: .allow / .bash). substrate
        # never imports a role catalogue -- the caller (typically
        # factory.orchestrator.pi_backend) supplies this, e.g.
        # ``lambda role: ROLE_SCOPE[AgentRole(role)]``.
        self._scope_for = scope_for
        self._provider = provider
        self._model = model
        self._idle_timeout_s = idle_timeout_s
        self._total_timeout_s = total_timeout_s
        self._idle_grace = max(1, idle_grace)
        # Liveness-aware idle: deliverables written under these dirs reset the
        # silent-window breach, so a quiet-but-writing child isn't killed mid-
        # deliverable (T-029). Default root is the repo_root; None disables the
        # file probe (a fault-injected liveness_probe opts out of it too).
        self._liveness_root = repo_root if liveness_root is None else liveness_root
        self._liveness_dirs = tuple(liveness_dirs)
        self._liveness_probe = liveness_probe

    def run(
        self,
        role: str,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        scope = self._scope_for(role)
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
            # stdin=DEVNULL: without it, Pi's CLI blocks forever in its own
            # readPipedStdin() waiting for stdin EOF whenever this process
            # inherits a long-lived open pipe (e.g. launchInteractiveReview's
            # human-review handshake keeps the orchestrator's own stdin open).
            # On POSIX the child is additionally launched as a process-group
            # leader (start_new_session=True) so a tree-kill can kill the
            # whole group (grandchildren included), not just this pid. Windows
            # has no group semantics, so Popen is left default there.
            #
            # The launch itself is wrapped in a bounded transient retry
            # (PART-2b of T-029): only a failure to START the process (Popen
            # raising, e.g. a missing `pi` bin) is retried; a child that started
            # and then stalled/timed out is a kill on the *other* path and must
            # never be relaunched here.
            def _launch() -> subprocess.Popen[str]:
                if sys.platform != "posix":
                    return subprocess.Popen(
                        cmd, cwd=self._repo_root, env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace",
                    )
                return subprocess.Popen(
                    cmd, cwd=self._repo_root, env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    start_new_session=True,
                )

            proc = _retry_launch(_launch, retries=_SPAWN_RETRIES, delay=_SPAWN_BACKOFF_S)
            assert proc.stdout is not None
            captured_session_id: str | None = None
            timed_out_reason: str | None = None
            # Output caps (PART-2b): retain only a bounded rolling TAIL of the
            # stream so a flooding child can't blow up memory, and count the
            # cumulative chars so an over-budget run is flagged as truncated.
            retained_lines: list[str] = []
            retained_chars = 0
            total_output_chars = 0

            def _on_timeout(reason: str) -> None:
                nonlocal timed_out_reason
                timed_out_reason = reason
                # Kill the runaway/stalled agent AND its whole process tree
                # (grandchild shells/tools) so proc.wait() returns once the
                # direct child exits and the run can end (and release its
                # lock) instead of hanging forever -- and so teardown doesn't
                # leak descendants.
                try:
                    _kill_process_tree(proc)
                except OSError:
                    pass

            for line in _drain_lines(
                proc.stdout,
                self._idle_timeout_s,
                self._total_timeout_s,
                _on_timeout,
                idle_grace=self._idle_grace,
                liveness_root=self._liveness_root,
                liveness_dirs=self._liveness_dirs,
                liveness_probe=self._liveness_probe,
            ):
                total_output_chars += len(line)
                retained_chars = _retain_line_capped(
                    retained_lines, retained_chars,
                    _MAX_OUTPUT_RETAINED_CHARS,
                    line,
                )
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
            stdout = "".join(retained_lines)
            # If the whole run's output exceeded the hard total cap, mark it so
            # the retained tail is not mistaken for the full stream. Prepending
            # the note (before the tail) leaves parsing anchored on the LAST
            # ```json block and leaves the ok/interruption classification
            # untouched.
            if _MAX_OUTPUT_TOTAL_CHARS > 0 and total_output_chars > _MAX_OUTPUT_TOTAL_CHARS:
                stdout = _output_truncated_note(total_output_chars) + "\n" + stdout
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
