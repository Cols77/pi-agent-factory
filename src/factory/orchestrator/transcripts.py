from __future__ import annotations

from pathlib import Path


def write_role_transcript(transcript_dir: Path, node: str, attempt: int, raw: str) -> Path:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"{node}-attempt{attempt}.log"
    path.write_text(raw, encoding="utf-8")
    return path
