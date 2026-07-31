"""DetectionSpawner — spawns entities from scenario rules and reports detections."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from drone.interfaces import Pose, Detection
from sim.scenario import Zone, SpawnerRule


@dataclass
class _Entity:
    """Internal representation of a spawned entity in the simulation world."""

    label: str
    position: Pose
    speed: float
    start_time: float


class DetectionSpawner:
    """Perception implementation that spawns entities from scenario rules.

    Implements the ``Perception`` protocol (``get_detections``).

    ``get_detections`` is a pure getter — it never mutates internal state.
    Call ``tick(dt)`` once per simulation step to advance the clock, move
    entities, and spawn entities whose start time has been reached.
    """

    def __init__(
        self,
        spawners: list[SpawnerRule],
        zones: list[Zone],
        sea_polygon: list[list[float]],
        max_sensor_range: float = 100.0,
        seed: int | None = None,
    ) -> None:
        self._zones = zones
        self._sea_polygon = sea_polygon
        self._max_sensor_range = max_sensor_range
        self._spawner_defs = spawners
        self._drone_pose = Pose(0, 0, 0, 0)
        self._entities: list[_Entity] = []
        self._clock: float = 0.0
        self._rng = random.Random(seed)

        # Pre-spawn entities whose start_time is <= 0
        for spawner in spawners:
            if spawner.start_time <= 0.0:
                for _ in range(spawner.count):
                    pos = self._random_position_in_pool(spawner.pool)
                    self._entities.append(
                        _Entity(
                            label=spawner.label,
                            position=pos,
                            speed=spawner.speed,
                            start_time=spawner.start_time,
                        )
                    )

    def set_drone_pose(self, pose: Pose) -> None:
        """Update the drone's current position."""
        self._drone_pose = pose

    # ── Public simulation API ─────────────────────────────────────────────

    def tick(self, dt: float) -> None:
        """Advance the simulation by ``dt`` seconds.

        Moves entities with a random walk and spawns entities whose
        ``start_time`` has been reached. This is the only method that
        mutates simulation state.
        """
        self._clock += dt
        self._move_entities(dt)
        self._spawn_pending_entities()

    def get_detections(self) -> list[Detection]:
        """Return a list of all detectable entities.

        Pure getter — no side effects. Implements ``Perception.get_detections``.
        """
        dets: list[Detection] = []
        for entity in self._entities:
            dx = entity.position.x - self._drone_pose.x
            dy = entity.position.y - self._drone_pose.y
            rng = math.sqrt(dx * dx + dy * dy)
            bearing = math.degrees(math.atan2(dy, dx)) % 360
            confidence = max(0.0, min(1.0, 1.0 - rng / self._max_sensor_range))

            dets.append(
                Detection(
                    label=entity.label,
                    confidence=confidence,
                    bearing=bearing,
                    range=rng,
                    position=entity.position,
                )
            )
        return dets

    def spawn_entity(self, label: str) -> None:
        """Spawn one additional entity of the given label (for keyboard injection)."""
        pool = "inside_polygon(sea_polygon)"
        speed = 1.0
        for s in self._spawner_defs:
            if s.label == label:
                pool = s.pool
                speed = s.speed
                break
        pos = self._random_position_in_pool(pool)
        self._entities.append(
            _Entity(
                label=label,
                position=pos,
                speed=speed,
                start_time=0.0,
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _move_entities(self, dt: float) -> None:
        """Move each entity with a simple random walk."""
        for entity in self._entities:
            if entity.speed <= 0.0:
                continue
            angle = self._rng.uniform(0, 2 * math.pi)
            step = entity.speed * dt
            nx = entity.position.x + math.cos(angle) * step
            ny = entity.position.y + math.sin(angle) * step
            entity.position = Pose(nx, ny, 0, 0)

    def _spawn_pending_entities(self) -> None:
        """Spawn entities whose start_time has been reached."""
        for spawner in self._spawner_defs:
            if spawner.start_time <= 0.0:
                continue  # already spawned in __init__
            already_spawned = any(e.label == spawner.label for e in self._entities)
            if not already_spawned and self._clock >= spawner.start_time:
                for _ in range(spawner.count):
                    pos = self._random_position_in_pool(spawner.pool)
                    self._entities.append(
                        _Entity(
                            label=spawner.label,
                            position=pos,
                            speed=spawner.speed,
                            start_time=spawner.start_time,
                        )
                    )

    def _resolve_pool_bounds(self, pool_expr: str) -> list[tuple[float, float]]:
        """Resolve a pool expression like ``inside_zone(id)`` or ``inside_polygon(sea_polygon)``
        to a list of polygon vertices."""
        if pool_expr.startswith("inside_zone("):
            zone_id = pool_expr[len("inside_zone(") : -1]
            for z in self._zones:
                if z.id == zone_id:
                    return [(p[0], p[1]) for p in z.polygon]
            return []
        if pool_expr.startswith("inside_polygon("):
            name = pool_expr[len("inside_polygon(") : -1]
            if name == "sea_polygon":
                return [(p[0], p[1]) for p in self._sea_polygon]
            return []
        return []

    def _random_position_in_pool(self, pool_expr: str) -> Pose:
        """Return a random (x, y, 0) position inside the given pool polygon."""
        bounds = self._resolve_pool_bounds(pool_expr)
        if not bounds:
            return Pose(0, 0, 0, 0)
        min_x = min(p[0] for p in bounds)
        max_x = max(p[0] for p in bounds)
        min_y = min(p[1] for p in bounds)
        max_y = max(p[1] for p in bounds)
        x = self._rng.uniform(min_x, max_x)
        y = self._rng.uniform(min_y, max_y)
        return Pose(x, y, 0, 0)
