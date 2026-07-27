from __future__ import annotations

import json
import re
from pathlib import Path

_COUNT = {
    kind: re.compile(rf"(\d+) {kind}")
    for kind in ("passed", "failed", "error", "errors", "skipped", "xfailed")
}
_FAIL_MARKER = re.compile(r"\bFAILED\b|\berror:|Traceback \(most recent call last\)")
_GATES = ("unit", "sim", "full")


def parse_gate_summary(log_text: str) -> dict | None:
    """Turn a gate log into {"ok", "summary"} using its pytest tally; fall back
    to a failure-marker scan for non-pytest gates. None when there's no signal."""
    counts = {}
    for kind, pat in _COUNT.items():
        m = list(pat.finditer(log_text))
        if m:
            counts[kind.rstrip("s") if kind == "errors" else kind] = int(m[-1].group(1))
    if any(k in counts for k in ("passed", "failed", "error", "skipped", "xfailed")):
        parts = []
        for kind in ("failed", "error", "passed", "skipped", "xfailed"):
            if counts.get(kind):
                parts.append(f"{counts[kind]} {kind}")
        ok = counts.get("passed", 0) > 0 and not counts.get("failed") and not counts.get("error")
        return {"ok": ok, "summary": ", ".join(parts)}
    if _FAIL_MARKER.search(log_text):
        return {"ok": False, "summary": "ran"}
    return None


def review_guide_path(repo_root: Path, session_id: str) -> Path:
    return repo_root / "sessions" / ".factory-transcripts" / session_id / "review-guide.json"


def read_validation(transcript_dir: Path) -> list[dict]:
    out: list[dict] = []
    for gate in _GATES:
        log = transcript_dir / f"{gate}-gate.log"
        if not log.exists():
            continue
        try:
            parsed = parse_gate_summary(log.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            parsed = None
        if parsed is not None:
            out.append({"gate": gate, **parsed})
    return out


def write_review_guide(path: Path, guide: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(guide, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # best-effort: the guide is a nicety, never block the run
