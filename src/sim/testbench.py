"""SimTestbench — main orchestrator for the interactive simulation testbench.

Wraps a ``MissionLoop`` with a ``DetectionSpawner``, renders the world with
pygame, handles keyboard input via ``EventInjector``, and records mission
traces with ``Recorder``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pygame

from drone.interfaces import Directive, Pose, PriorityRule, WaterArea, NavContext
from drone.fake_flight_controller import FakeFlightController
from drone.mission.loop import MissionLoop
from drone.mission.fake_agent import FakeAgent
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm

from sim.scenario import Scenario
from sim.detection_spawner import DetectionSpawner
from sim.renderer import Renderer
from sim.hud import HUD
from sim.recorder import Recorder
from sim.injector import EventInjector


class SimTestbench:
    """Main testbench orchestrator.

    Runs a ``MissionLoop`` with a ``DetectionSpawner``, renders with pygame,
    and handles interactive controls.

    Usage::

        tb = SimTestbench("scenarios/my_scenario.yaml")
        tb.run()
    """

    SCREEN_WIDTH = 1280
    SCREEN_HEIGHT = 800

    def __init__(self, scenario_path: str | Path) -> None:
        self._scenario = Scenario.load(scenario_path)
        self._clock = pygame.time.Clock()
        self._running = False
        self._paused = False
        self._speed_mult = 1.0
        self._event_log: list[str] = []
        self._detection_summary: dict[str, int] = {}
        self._dt = 0.05  # fixed timestep (seconds)

        # Pygame init
        pygame.init()
        self._screen = pygame.display.set_mode(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
            pygame.RESIZABLE,
        )
        pygame.display.set_caption(f"Sim Testbench — {self._scenario.name}")

        # Build simulation components
        self._build_simulation()

        # Build rendering
        self._renderer = Renderer(self._screen, self._scenario)
        self._hud = HUD()
        self._recorder = Recorder(record_interval=1.0)
        self._injector = EventInjector(self)

        # Center view on sea polygon centroid
        verts = self._scenario.sea_polygon.get("vertices", [])
        if verts:
            cx = sum(v[0] for v in verts) / len(verts)
            cy = sum(v[1] for v in verts) / len(verts)
            self._renderer.set_view(cx, cy, 3.0)

    # ── Public API ───────────────────────────────────────────────────────

    def run(self) -> None:
        """Run the main event loop until the user quits."""
        self._running = True

        while self._running:
            self._handle_events()

            if not self._paused:
                # Run simulation tick(s) according to speed multiplier
                for _ in range(int(self._speed_mult)):
                    self._tick_simulation(self._dt)

            self._draw_frame()
            self._clock.tick(60)

        pygame.quit()

    def pause(self) -> None:
        """Pause the simulation."""
        self._paused = True

    def resume(self) -> None:
        """Resume the simulation."""
        self._paused = False

    def toggle_pause(self) -> None:
        """Toggle between paused and running."""
        self._paused = not self._paused

    def set_speed(self, mult: float) -> None:
        """Set the simulation speed multiplier (1×, 2×, 5×, etc.)."""
        self._speed_mult = mult

    def spawn_entity(self, label: str) -> None:
        """Manually spawn one entity of the given label."""
        self._spawner.spawn_entity(label)
        self._event_log.append(f"SPAWNED {label} (manual)")

    def reset(self) -> None:
        """Reset the simulation to its initial state."""
        self._build_simulation()
        self._event_log.clear()
        self._detection_summary.clear()
        self._paused = False

    def quit(self) -> None:
        """Signal the main loop to exit."""
        self._running = False

    @property
    def scenario(self) -> Scenario:
        return self._scenario

    @property
    def fc(self) -> FakeFlightController:
        return self._fc

    @property
    def screen(self) -> pygame.Surface:
        return self._screen

    # ── Internal: simulation construction ────────────────────────────────

    def _build_simulation(self) -> None:
        """Build (or rebuild) the simulation components: FC, spawner, agent, loop."""
        nav = self._scenario.navigation
        sea_verts_tuples = [(v[0], v[1]) for v in self._scenario.sea_polygon["vertices"]]
        sea_verts = [[v[0], v[1]] for v in self._scenario.sea_polygon["vertices"]]

        # Flight controller
        self._fc = FakeFlightController()

        # Detection spawner
        self._spawner = DetectionSpawner(
            spawners=self._scenario.detections["spawners"],
            zones=self._scenario.zones,
            sea_polygon=sea_verts,
        )

        # Navigation algorithm — build an initial perimeter sweep plan
        algo = PerimeterSweepAlgorithm(
            altitude=nav.get("altitude", 5.0),
            offset=nav.get("offset", 2.0),
            max_distance_from_shore=nav.get("max_distance_from_shore"),
        )
        water = WaterArea(vertices=sea_verts_tuples)
        context = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        initial_plan = algo.plan(water, context)

        # Agent — FakeAgent with scripted directives
        agent = FakeAgent(
            responses=[
                Directive(kind="update_nav", args={"nav_plan": initial_plan}),
            ]
            + [Directive(kind="continue") for _ in range(2000)]
        )

        # Priority rules from scenario
        priority_rules = None
        if self._scenario.priority_rules:
            priority_rules = [
                PriorityRule(
                    label=r["label"],
                    min_confidence=r["min_confidence"],
                    reason_template=r["reason"],
                )
                for r in self._scenario.priority_rules
            ]

        # Mission loop
        self._loop = MissionLoop(
            fc=self._fc,
            perception=self._spawner,
            agent=agent,
            priority_rules=priority_rules,
            heartbeat_interval=3.0,
            dt=self._dt,
        )
        self._loop.start(self._scenario.description)

    # ── Internal: per-frame simulation step ──────────────────────────────

    def _tick_simulation(self, dt: float) -> None:
        """Advance the simulation by one tick of ``dt`` seconds.

        Order:
        1. Advance detection spawner (clock, entity movement, spawning).
        2. Advance mission loop tick (sequencer drives FC toward waypoint).
        3. Update spawner with the new drone pose.
        4. Check for priority events (shark alerts, etc.).
        5. Run agent heartbeat if interval elapsed.
        6. Auto-land if battery critical.
        7. Record frame, update event log, update detection summary.
        """
        if self._loop is None:
            return

        # 1. Advance detection spawner simulation
        self._spawner.tick(dt)

        # 2. Advance mission loop tick (moves the drone via sequencer)
        self._loop._tick_advance()

        # 3. Update spawner with the new drone pose
        pose = self._fc.get_pose()
        self._spawner.set_drone_pose(pose)

        # 4. Check for priority events
        self._loop._handle_priority_events()

        # 5. Agent heartbeat
        self._loop._handle_heartbeat()

        # 6. Battery critical check
        self._loop._handle_battery_critical()

        # 7. Record frame
        wp_status: dict[str, Any] = {}
        if self._loop._sequencer is not None:
            wp_status = self._loop._sequencer.status()
        self._recorder.record(
            mission_clock=self._loop._state.mission_clock if self._loop._state else 0.0,
            drone_pose=pose,
            detections=self._spawner.get_detections(),
            active_directive=None,
            waypoint_status=wp_status,
        )

        # Update event log from mission state
        if self._loop._state is not None and self._loop._state.action_log:
            last_action = self._loop._state.action_log[-1]
            timestamp, description = last_action
            self._event_log.append(f"[{timestamp:.1f}s] {description}")

        # Update detection summary
        dets = self._spawner.get_detections()
        summary: dict[str, int] = {}
        for d in dets:
            summary[d.label] = summary.get(d.label, 0) + 1
        self._detection_summary = summary

        # Check for loop termination
        if self._loop._state is not None:
            if self._loop._state.mission_clock >= self._scenario.max_duration:
                self._paused = True
                self._event_log.append("MISSION COMPLETE — max duration reached")

        if self._fc.get_battery() < 0.1:
            self._paused = True
            self._event_log.append("MISSION COMPLETE — battery critical")

    # ── Internal: event handling ─────────────────────────────────────────

    def _handle_events(self) -> None:
        """Process all pending pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN:
                self._injector.handle_key(event.key)

    # ── Internal: drawing ────────────────────────────────────────────────

    def _draw_frame(self) -> None:
        """Draw the current world state, HUD, and pause overlay."""
        pose = self._fc.get_pose()
        dets = self._spawner.get_detections()

        # Get waypoints for rendering
        waypoints = None
        if self._loop._sequencer is not None and self._loop._sequencer._plan is not None:
            waypoints = self._loop._sequencer._plan.waypoints

        # Draw world
        self._renderer.draw_world(pose, dets, waypoints)

        # Draw HUD
        nav_status = "no plan"
        if self._loop._sequencer is not None:
            s = self._loop._sequencer.status()
            if s["plan_name"]:
                nav_status = f"{s['plan_name']} ({s['completed']}/{s['total']} waypoints)"

        self._hud.draw(
            screen=self._screen,
            mission_name=self._scenario.name,
            mission_clock=self._loop._state.mission_clock if self._loop._state else 0.0,
            speed_mult=self._speed_mult,
            fps=self._clock.get_fps(),
            nav_status=nav_status,
            battery=self._fc.get_battery(),
            detection_summary=self._detection_summary,
            event_log=self._event_log,
        )

        # Pause overlay
        if self._paused:
            w, h = self._screen.get_size()
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            self._screen.blit(overlay, (0, 0))
            font = pygame.font.Font(None, 48)
            pause_text = font.render("PAUSED", True, (255, 255, 255))
            self._screen.blit(
                pause_text,
                (
                    w // 2 - pause_text.get_width() // 2,
                    h // 2 - pause_text.get_height() // 2,
                ),
            )

        pygame.display.flip()