"""PerimeterSweepAlgorithm — traces water polygon perimeter at a fixed inward offset."""
from __future__ import annotations

import math

from drone.interfaces import WaterArea, NavContext, NavPlan, Pose


def _inset_polygon(vertices: list[tuple[float, float]], offset: float) -> list[tuple[float, float]]:
    """Inset a polygon by moving each edge inward along its normal."""
    n = len(vertices)
    if n < 3:
        return vertices[:]

    # Compute edge normals (inward-pointing for CCW polygon)
    edges: list[tuple[float, float, float, float, float, float]] = []  # (x1,y1,x2,y2,nx,ny)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-12:
            continue
        # Inward normal for CCW polygon: (-dy, dx) / length
        nx, ny = -dy / length, dx / length
        edges.append((x1, y1, x2, y2, nx, ny))

    if len(edges) < 3:
        return vertices[:]

    # Offset each edge
    offset_edges: list[tuple[float, float, float, float]] = []  # (ox1, oy1, ox2, oy2)
    for x1, y1, x2, y2, nx, ny in edges:
        offset_edges.append((x1 + nx * offset, y1 + ny * offset, x2 + nx * offset, y2 + ny * offset))

    # Intersect adjacent offset edges
    new_vertices: list[tuple[float, float]] = []
    m = len(offset_edges)
    for i in range(m):
        ox1, oy1, ox2, oy2 = offset_edges[i]
        px1, py1, px2, py2 = offset_edges[(i + 1) % m]

        # Line intersection
        d1x, d1y = ox2 - ox1, oy2 - oy1
        d2x, d2y = px2 - px1, py2 - py1

        denom = d1x * d2y - d1y * d2x
        if abs(denom) < 1e-12:
            # Parallel — use midpoint
            new_vertices.append(((ox2 + px1) / 2, (oy2 + py1) / 2))
        else:
            t = ((px1 - ox1) * d2y - (py1 - oy1) * d2x) / denom
            new_vertices.append((ox1 + t * d1x, oy1 + t * d1y))

    return new_vertices


def _distance_to_nearest_edge(px: float, py: float, vertices: list[tuple[float, float]]) -> float:
    """Distance from point to nearest edge of the polygon."""
    n = len(vertices)
    min_dist = float('inf')
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        # Point-to-segment distance
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-12:
            dist = math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
        else:
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
            proj_x, proj_y = x1 + t * dx, y1 + t * dy
            dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
        min_dist = min(min_dist, dist)
    return min_dist


def _ensure_ccw(vertices: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Ensure polygon vertices are in CCW order."""
    # Compute signed area
    n = len(vertices)
    area = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += (x2 - x1) * (y2 + y1)
    if area > 0:  # CW -> reverse
        return list(reversed(vertices))
    return vertices[:]


class PerimeterSweepAlgorithm:
    """Traces the water polygon perimeter at a fixed inward offset and constant altitude."""

    def __init__(
        self,
        altitude: float = 5.0,
        offset: float = 2.0,
        max_distance_from_shore: float | None = None,
    ) -> None:
        self._altitude = altitude
        self._offset = offset
        self._max_distance = max_distance_from_shore

    def plan(self, water: WaterArea, context: NavContext) -> NavPlan:
        """Generate a perimeter sweep plan.

        Produces waypoints inset from the water polygon boundary, ordered
        to start nearest the current pose, with the loop closed.
        """
        # Ensure CCW for consistent inset normals
        verts = _ensure_ccw(list(water.vertices))

        # Inset the polygon
        inset_verts = _inset_polygon(verts, self._offset)

        # Clip by max_distance_from_shore
        if self._max_distance is not None and len(inset_verts) >= 3:
            clipped = []
            for vx, vy in inset_verts:
                dist = _distance_to_nearest_edge(vx, vy, verts)
                if dist <= self._max_distance + self._offset:
                    clipped.append((vx, vy))
            inset_verts = clipped if len(clipped) >= 3 else inset_verts

        if len(inset_verts) < 3:
            # Degenerate — return single waypoint at centroid
            cx = sum(v[0] for v in verts) / len(verts)
            cy = sum(v[1] for v in verts) / len(verts)
            waypoints = [Pose(cx, cy, self._altitude, 0), Pose(cx, cy, self._altitude, 0)]
        else:
            # Order waypoints starting from vertex closest to current_pose
            cx, cy = context.current_pose.x, context.current_pose.y
            dists = [math.sqrt((vx - cx) ** 2 + (vy - cy) ** 2) for vx, vy in inset_verts]
            start_idx = dists.index(min(dists))
            # Reorder from start_idx, going CCW
            ordered = inset_verts[start_idx:] + inset_verts[:start_idx]

            # Create Pose waypoints
            waypoints = [Pose(vx, vy, self._altitude, 0) for vx, vy in ordered]
            # Close the loop
            waypoints.append(Pose(ordered[0][0], ordered[0][1], self._altitude, 0))

        return NavPlan(
            waypoints=waypoints,
            algorithm_name="perimeter_sweep",
            created_at=0.0,  # set by caller
        )