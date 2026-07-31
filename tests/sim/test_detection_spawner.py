"""Tests for DetectionSpawner."""
from __future__ import annotations

import math

import pytest
from drone.interfaces import Pose, Detection
from sim.scenario import Zone, SpawnerRule

pytestmark = pytest.mark.unit


class TestDetectionSpawner:
    """DetectionSpawner should implement Perception protocol."""

    def test_returns_empty_when_no_spawners(self):
        from sim.detection_spawner import DetectionSpawner

        spawner = DetectionSpawner(
            spawners=[],
            zones=[],
            sea_polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        )
        spawner.set_drone_pose(Pose(5, 5, 5, 0))
        dets = spawner.get_detections()
        assert dets == []

    def test_spawner_returns_expected_count(self):
        from sim.detection_spawner import DetectionSpawner

        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                            count=3, start_time=0.0, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            max_sensor_range=200.0,
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        dets = spawner.get_detections()
        assert len(dets) == 3
        for d in dets:
            assert d.label == "swimmer"
            assert 0.0 <= d.confidence <= 1.0
            assert d.range > 0

    def test_confidence_decreases_with_distance(self):
        from sim.detection_spawner import DetectionSpawner

        # Use a fixed seed so the spawned shark position is deterministic
        # and far from the drone start pose (0, 0).
        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="shark", pool="inside_polygon(sea_polygon)",
                            count=1, start_time=0.0, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            max_sensor_range=100.0,
            seed=42,
        )
        # Drone far away -> low confidence
        spawner.set_drone_pose(Pose(0, 0, 5, 0))
        far_dets = spawner.get_detections()
        far_conf = far_dets[0].confidence
        assert far_conf < 0.5, "Shark should be far from origin"

        # Drone close -> high confidence
        shark_pos = far_dets[0].position
        spawner.set_drone_pose(Pose(shark_pos.x + 1, shark_pos.y, 5, 0))
        close_dets = spawner.get_detections()
        close_conf = close_dets[0].confidence

        assert close_conf > far_conf, "Confidence should increase as drone approaches"

    def test_spawn_entity_adds_one(self):
        from sim.detection_spawner import DetectionSpawner

        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                            count=1, start_time=0.0, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        dets = spawner.get_detections()
        assert len(dets) == 1
        spawner.spawn_entity("shark")
        dets = spawner.get_detections()
        assert len(dets) == 2
        assert dets[1].label == "shark"

    # ── Pure getter & tick semantics ──────────────────────────────────────

    def test_get_detections_has_no_side_effects(self):
        """get_detections() must be a pure getter: repeated calls must not
        advance the clock or move entities."""
        from sim.detection_spawner import DetectionSpawner

        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                            count=2, start_time=0.0, interval=0.0, speed=1.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            seed=7,
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        first = spawner.get_detections()
        second = spawner.get_detections()
        third = spawner.get_detections()

        pos_first = [(d.position.x, d.position.y) for d in first]
        pos_second = [(d.position.x, d.position.y) for d in second]
        pos_third = [(d.position.x, d.position.y) for d in third]
        assert pos_first == pos_second == pos_third

    def test_tick_moves_entities(self):
        """tick(dt) should advance the clock and move entities with speed > 0."""
        from sim.detection_spawner import DetectionSpawner

        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                            count=1, start_time=0.0, interval=0.0, speed=2.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            seed=3,
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        before = spawner.get_detections()[0].position
        spawner.tick(0.05)
        after = spawner.get_detections()[0].position
        assert (after.x, after.y) != (before.x, before.y)
        # Max step is speed * dt = 0.1m
        step = math.hypot(after.x - before.x, after.y - before.y)
        assert 0.0 < step <= 0.1

    def test_tick_spawns_entities_at_start_time(self):
        """Entities with start_time > 0 must only appear after tick() advances
        the clock past start_time, and must be spawned exactly once."""
        from sim.detection_spawner import DetectionSpawner

        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="shark", pool="inside_polygon(sea_polygon)",
                            count=2, start_time=0.5, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            seed=11,
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        assert spawner.get_detections() == []

        spawner.tick(0.2)  # clock = 0.2 < 0.5
        assert spawner.get_detections() == []

        spawner.tick(0.2)  # clock = 0.4 < 0.5
        assert spawner.get_detections() == []

        spawner.tick(0.2)  # clock = 0.6 >= 0.5 -> spawns
        dets = spawner.get_detections()
        assert len(dets) == 2
        assert all(d.label == "shark" for d in dets)

        # Spawning must happen exactly once.
        spawner.tick(0.2)  # clock = 0.8
        assert len(spawner.get_detections()) == 2

    def test_seed_makes_positions_deterministic(self):
        """Same seed -> same positions; different seed -> different positions."""
        from sim.detection_spawner import DetectionSpawner

        def build(seed: int):
            return DetectionSpawner(
                spawners=[
                    SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                                count=1, start_time=0.0, interval=0.0, speed=0.0),
                ],
                zones=[],
                sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
                seed=seed,
            )

        a = build(123).get_detections()[0].position
        b = build(123).get_detections()[0].position
        assert (a.x, a.y) == (b.x, b.y)

        c = build(456).get_detections()[0].position
        assert (c.x, c.y) != (a.x, a.y)