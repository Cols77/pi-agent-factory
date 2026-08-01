"""Matplotlib post-mission report generator.

Produces a three-panel PNG figure from a simulation trace:
1. Top-down trajectory + detections map
2. Detection timeline
3. Confidence vs range scatter
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from sim.recorder import Recorder


def generate_report(
    recorder: Recorder,
    output_path: str | Path,
    mission_name: str = "mission",
    sea_polygon: list[list[float]] | None = None,
    zones: list[dict] | None = None,
) -> None:
    """Generate a three-panel matplotlib report figure from a mission trace.

    Args:
        recorder: A Recorder with recorded frames.
        output_path: Path to save the PNG figure.
        mission_name: Label for the figure title.
        sea_polygon: Optional list of [x, y] vertices for the sea boundary.
        zones: Optional list of dicts with ``polygon`` and ``label`` keys.
    """
    trace = recorder.trace()
    if not trace:
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(
        f"Mission: {mission_name}  |  Duration: {trace[-1].mission_clock:.1f}s",
        fontsize=14,
        fontweight="bold",
    )

    # ── Panel 1: Top-down trajectory & detections ──────────────────────
    ax1 = axes[0]
    ax1.set_title("Trajectory & Detections")
    ax1.set_xlabel("X (m)")
    ax1.set_ylabel("Y (m)")
    ax1.grid(True, alpha=0.3)

    # Sea polygon
    if sea_polygon:
        verts = [(v[0], v[1]) for v in sea_polygon]
        poly = MplPolygon(
            verts, fill=True, alpha=0.1, color="blue", ec="blue", lw=1
        )
        ax1.add_patch(poly)

    # Zones
    if zones:
        for z in zones:
            zv = [(p[0], p[1]) for p in z.get("polygon", [])]
            if zv:
                zp = MplPolygon(
                    zv,
                    fill=True,
                    alpha=0.15,
                    color="green",
                    ec="green",
                    lw=1,
                    ls="--",
                )
                ax1.add_patch(zp)

    # Trajectory
    xs = [f.drone_pose.x for f in trace]
    ys = [f.drone_pose.y for f in trace]
    ax1.plot(xs, ys, "b-", alpha=0.7, lw=1.5, label="Trajectory")
    ax1.scatter(
        xs[0], ys[0], c="green", s=80, marker="o", label="Start", zorder=5
    )
    ax1.scatter(
        xs[-1], ys[-1], c="red", s=80, marker="x", label="End", zorder=5
    )

    # Detection markers
    for frame in trace:
        for det in frame.detections:
            if "shark" in det.label.lower():
                color = "red"
            elif "surf" in det.label.lower():
                color = "orange"
            else:
                color = "blue"
            ax1.scatter(
                det.position.x,
                det.position.y,
                c=color,
                s=30 * det.confidence,
                alpha=0.6,
                marker="o",
            )

    ax1.set_aspect("equal")
    ax1.legend(fontsize=8)

    # ── Panel 2: Detection timeline ────────────────────────────────────
    ax2 = axes[1]
    ax2.set_title("Detection Timeline")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Detection label")

    # Group detections by label
    labels_seen: dict[str, list[tuple[float, float]]] = {}
    for frame in trace:
        t = frame.mission_clock
        for det in frame.detections:
            labels_seen.setdefault(det.label, []).append((t, det.confidence))

    label_colors = {"shark": "red", "swimmer": "blue", "surfer": "orange"}
    for i, (label, points) in enumerate(labels_seen.items()):
        if not points:
            continue
        times = [p[0] for p in points]
        confs = [p[1] for p in points]
        color = label_colors.get(label, "gray")
        ax2.scatter(
            times,
            [i] * len(times),
            c=confs,
            cmap="RdYlGn",
            s=40,
            vmin=0,
            vmax=1,
            alpha=0.8,
        )

    ax2.set_yticks(range(len(labels_seen)))
    ax2.set_yticklabels(labels_seen.keys())

    # ── Panel 3: Confidence vs Range ───────────────────────────────────
    ax3 = axes[2]
    ax3.set_title("Confidence vs Range")
    ax3.set_xlabel("Range (m)")
    ax3.set_ylabel("Confidence")

    for frame in trace:
        for det in frame.detections:
            color = label_colors.get(det.label, "gray")
            ax3.scatter(det.range, det.confidence, c=color, alpha=0.5, s=20)

    ax3.grid(True, alpha=0.3)
    ax3.set_xlim(0, None)
    ax3.set_ylim(0, 1.1)

    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)