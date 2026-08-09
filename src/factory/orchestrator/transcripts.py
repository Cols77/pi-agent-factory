from __future__ import annotations

import json
from pathlib import Path

# Pi streams a `message_update` per chunk, and each one carries the WHOLE
# message so far rather than a delta. Persisting them makes a transcript grow
# with the square of message length: one real context-gather run wrote 21,278
# update records across 26 messages (818 per message), 666MB of a 671MB log,
# for a session whose durable content was a few hundred KB.
#
# `message_end` carries the final content, so dropping the updates loses
# nothing that can be read back later. Only the intermediate snapshots go.
_STREAMING_ONLY_RECORDS = frozenset({"message_update"})


def _is_streaming_noise(line: str) -> bool:
    """True for a record whose content is superseded by a later one.

    Anything that is not pi's JSONL -- a traceback, a non-pi backend's output,
    a partial line from a crash -- is never noise: it is kept verbatim, because
    the transcript is the only place it exists.
    """
    stripped = line.strip()
    if not stripped.startswith("{"):
        return False
    try:
        record = json.loads(stripped)
    except ValueError:
        return False
    return isinstance(record, dict) and record.get("type") in _STREAMING_ONLY_RECORDS


def write_role_transcript(transcript_dir: Path, node: str, attempt: int, raw: str) -> Path:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"{node}-attempt{attempt}.log"
    kept = [line for line in raw.splitlines(keepends=True) if not _is_streaming_noise(line)]
    path.write_text("".join(kept), encoding="utf-8")
    return path
