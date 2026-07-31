from __future__ import annotations

_PATROL = "patrol"


def _trigger_time(frames: list[dict], trigger_label: str) -> float | None:
    for f in frames:
        for d in f.get("detections", []):
            if d.get("label") == trigger_label:
                return float(f["mission_clock"])
    return None


def trial_preempted(
    frames: list[dict], window: dict | None, trigger_label: str = "shark"
) -> bool:
    t0 = _trigger_time(frames, trigger_label)
    if t0 is None:
        return False
    within = None if window is None else float(window["within_s"])
    preempt_time: float | None = None
    for f in frames:
        clock = float(f["mission_clock"])
        if clock < t0:
            continue
        kind = f.get("active_directive", {}).get("kind")
        if kind is not None and kind != _PATROL:
            if within is None or clock - t0 <= within:
                preempt_time = clock
                break
    if preempt_time is None:
        return False
    # Resume: a later frame returns to patrol.
    return any(
        float(f["mission_clock"]) > preempt_time
        and f.get("active_directive", {}).get("kind") == _PATROL
        for f in frames
    )


def preemption_success_rate(
    trials: list[list[dict]], window: dict | None, trigger_label: str = "shark"
) -> float:
    if not trials:
        return 0.0
    passed = sum(1 for t in trials if trial_preempted(t, window, trigger_label))
    return passed / len(trials)
