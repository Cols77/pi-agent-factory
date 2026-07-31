"""Pygame renderer for the simulation world."""

from __future__ import annotations

import math
from typing import Any

import pygame

from drone.interfaces import Pose, Detection
from sim.scenario import Scenario, Zone


# Colors
COLOR_SEA = (20, 80, 160)
COLOR_SEA_EDGE = (40, 120, 200)
COLOR_DRONE = (255, 255, 255)
COLOR_SWIMMER = (0, 150, 255)
COLOR_SURFER = (255, 180, 0)
COLOR_SHARK = (255, 50, 50)
COLOR_GRID = (40, 60, 80)
COLOR_EVENT_STAR = (255, 255, 0)
COLOR_EVENT_WARN = (255, 100, 100)


def _world_to_screen(
    world_x: float,
    world_y: float,
    offset_x: float,
    offset_y: float,
    scale: float,
    screen_w: int,
    screen_h: int,
) -> tuple[float, float]:
    """Convert world coordinates to screen pixel coordinates."""
    sx = screen_w / 2 + (world_x - offset_x) * scale
    sy = screen_h / 2 - (world_y - offset_y) * scale  # flip Y axis
    return sx, sy


class Renderer:
    """Pygame renderer for the simulation world.

    Draws the sea polygon, zones, waypoints, drone, detection entities,
    and event markers onto a pygame surface.
    """

    def __init__(self, screen: pygame.Surface, scenario: Scenario) -> None:
        self._screen = screen
        self._scenario = scenario
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0
        self._scale: float = 3.0  # pixels per meter
        self._pending_events: list[dict[str, Any]] = []  # events to show on screen

    def add_event(self, event_type: str, position: Pose, label: str) -> None:
        """Register an event to display as a fading marker on the world view."""
        self._pending_events.append(
            {
                "type": event_type,  # "shark_alert" or "warning"
                "position": position,
                "label": label,
                "created_at": pygame.time.get_ticks(),
            }
        )

    def set_view(self, center_x: float, center_y: float, scale: float) -> None:
        """Set the camera view center and zoom level."""
        self._offset_x = center_x
        self._offset_y = center_y
        self._scale = scale

    def draw_world(
        self,
        drone_pose: Pose,
        detections: list[Detection],
        waypoints: list[Pose] | None = None,
    ) -> None:
        """Draw the full world state onto the renderer's screen surface."""
        screen_w, screen_h = self._screen.get_size()

        # Background
        self._screen.fill((10, 10, 20))

        # Grid
        self._draw_grid()

        # Sea polygon
        verts = self._scenario.sea_polygon["vertices"]
        if verts:
            self._draw_polygon(verts, COLOR_SEA, COLOR_SEA_EDGE, 2)

        # Zones
        for zone in self._scenario.zones:
            self._draw_zone(zone)

        # Waypoints (nav plan)
        if waypoints:
            self._draw_waypoints(waypoints)

        # Event markers
        self._draw_event_markers()

        # Detections
        for det in detections:
            self._draw_detection(det, drone_pose)

        # Drone
        self._draw_drone(drone_pose)

    # ------------------------------------------------------------------
    # Internal drawing helpers
    # ------------------------------------------------------------------

    def _draw_grid(self) -> None:
        """Draw a background grid with 10-meter spacing."""
        screen_w, screen_h = self._screen.get_size()
        grid_size = 10  # meters
        step = grid_size * self._scale

        cx = screen_w / 2 - self._offset_x * self._scale
        cy = screen_h / 2 + self._offset_y * self._scale

        x_start = (cx % step) - step
        y_start = (cy % step) - step

        for x in range(int(x_start), screen_w + int(step), int(step)):
            pygame.draw.line(self._screen, COLOR_GRID, (x, 0), (x, screen_h), 1)
        for y in range(int(y_start), screen_h + int(step), int(step)):
            pygame.draw.line(self._screen, COLOR_GRID, (0, y), (screen_w, y), 1)

    def _draw_polygon(
        self,
        verts: list,
        fill_color: tuple[int, int, int],
        edge_color: tuple[int, int, int],
        edge_width: int,
    ) -> None:
        """Draw a filled polygon with an edge."""
        screen_poly: list[tuple[int, int]] = []
        for vx, vy in verts:
            sx, sy = _world_to_screen(
                float(vx),
                float(vy),
                self._offset_x,
                self._offset_y,
                self._scale,
                self._screen.get_width(),
                self._screen.get_height(),
            )
            screen_poly.append((int(sx), int(sy)))
        if len(screen_poly) >= 3:
            pygame.draw.polygon(self._screen, fill_color, screen_poly)
            pygame.draw.polygon(self._screen, edge_color, screen_poly, edge_width)

    def _draw_zone(self, zone: Zone) -> None:
        """Draw a zone polygon with alpha channel and a centered label."""
        rgba = zone.color
        color = (rgba[0], rgba[1], rgba[2])
        alpha = rgba[3] if len(rgba) > 3 else 80

        screen_poly: list[tuple[int, int]] = []
        for vx, vy in zone.polygon:
            sx, sy = _world_to_screen(
                float(vx),
                float(vy),
                self._offset_x,
                self._offset_y,
                self._scale,
                self._screen.get_width(),
                self._screen.get_height(),
            )
            screen_poly.append((int(sx), int(sy)))

        if len(screen_poly) >= 3:
            surf = pygame.Surface(self._screen.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(surf, (*color, alpha), screen_poly)
            pygame.draw.polygon(surf, (*color, 200), screen_poly, 2)
            self._screen.blit(surf, (0, 0))

            # Label
            cx = sum(p[0] for p in screen_poly) // len(screen_poly)
            cy = sum(p[1] for p in screen_poly) // len(screen_poly)
            font = pygame.font.Font(None, 18)
            label = font.render(zone.label.replace("_", " ").title(), True, (200, 200, 200))
            self._screen.blit(label, (cx - label.get_width() // 2, cy - label.get_height() // 2))

    def _draw_waypoints(self, waypoints: list[Pose]) -> None:
        """Draw a path of waypoints."""
        if len(waypoints) < 2:
            return
        screen_pts: list[tuple[int, int]] = []
        for wp in waypoints:
            sx, sy = _world_to_screen(
                wp.x,
                wp.y,
                self._offset_x,
                self._offset_y,
                self._scale,
                self._screen.get_width(),
                self._screen.get_height(),
            )
            screen_pts.append((int(sx), int(sy)))

        # Draw path
        pygame.draw.lines(self._screen, (100, 200, 255), False, screen_pts, 1)

        # Draw waypoint dots
        for i, (sx, sy) in enumerate(screen_pts):
            color = (150, 220, 255) if i > 0 else (0, 255, 100)
            pygame.draw.circle(self._screen, color, (sx, sy), 3)

    def _draw_drone(self, pose: Pose) -> None:
        """Draw the drone as a triangle pointing in its heading direction."""
        sx, sy = _world_to_screen(
            pose.x,
            pose.y,
            self._offset_x,
            self._offset_y,
            self._scale,
            self._screen.get_width(),
            self._screen.get_height(),
        )
        # Triangle pointing in heading direction
        heading_rad = math.radians(pose.heading)
        size = 10
        pts = [
            (
                sx + size * math.cos(heading_rad),
                sy - size * math.sin(heading_rad),
            ),
            (
                sx + size * 0.5 * math.cos(heading_rad + 2.5),
                sy - size * 0.5 * math.sin(heading_rad + 2.5),
            ),
            (
                sx + size * 0.5 * math.cos(heading_rad - 2.5),
                sy - size * 0.5 * math.sin(heading_rad - 2.5),
            ),
        ]
        pygame.draw.polygon(self._screen, COLOR_DRONE, pts)
        pygame.draw.circle(self._screen, (200, 200, 255), (int(sx), int(sy)), 12, 1)

    def _draw_detection(self, det: Detection, drone_pose: Pose) -> None:
        """Draw a detection entity as a colored circle with a label."""
        sx, sy = _world_to_screen(
            det.position.x,
            det.position.y,
            self._offset_x,
            self._offset_y,
            self._scale,
            self._screen.get_width(),
            self._screen.get_height(),
        )

        # Color by label
        label_lower = det.label.lower()
        if "shark" in label_lower:
            color = COLOR_SHARK
        elif "surf" in label_lower:
            color = COLOR_SURFER
        else:
            color = COLOR_SWIMMER

        # Size by confidence
        radius = max(4, int(8 * det.confidence))
        pygame.draw.circle(self._screen, color, (int(sx), int(sy)), radius)
        if det.confidence < 0.5:
            pygame.draw.circle(self._screen, (100, 100, 100), (int(sx), int(sy)), radius + 3, 1)

        # Label
        font = pygame.font.Font(None, 14)
        label = font.render(f"{det.label} {det.confidence:.2f}", True, (200, 200, 200))
        self._screen.blit(label, (sx - label.get_width() // 2, sy - radius - 16))

        # Range ring
        pygame.draw.circle(
            self._screen,
            (80, 80, 80),
            (int(sx), int(sy)),
            int(det.range * self._scale * 0.1),
            1,
        )

    def _draw_event_markers(self) -> None:
        """Draw fading event markers (5-second display duration)."""
        current_time = pygame.time.get_ticks()
        self._pending_events = [
            e
            for e in self._pending_events
            if current_time - e["created_at"] < 5000  # 5s display
        ]
        for event in self._pending_events:
            pos = event["position"]
            sx, sy = _world_to_screen(
                pos.x,
                pos.y,
                self._offset_x,
                self._offset_y,
                self._scale,
                self._screen.get_width(),
                self._screen.get_height(),
            )
            color = COLOR_EVENT_STAR if event["type"] == "shark_alert" else COLOR_EVENT_WARN
            font = pygame.font.Font(None, 20)
            text = font.render(event["label"], True, color)
            self._screen.blit(text, (sx - text.get_width() // 2, sy - 30))
            # Star icon
            pygame.draw.circle(self._screen, color, (int(sx), int(sy - 20)), 5)