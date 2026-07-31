"""Heads-up display overlay for the simulation testbench."""

from __future__ import annotations

import pygame


class HUD:
    """Heads-up display overlay for the simulation testbench.

    Draws mission info, nav status, battery, detection summary,
    event log, and controls hint onto a semi-transparent panel.
    """

    BG_COLOR = (0, 0, 0, 140)
    TEXT_COLOR = (220, 220, 240)
    HIGHLIGHT_COLOR = (100, 200, 255)
    WARN_COLOR = (255, 150, 100)

    def __init__(self, font_size: int = 18) -> None:
        self._font = pygame.font.Font(None, font_size)

    def draw(
        self,
        screen: pygame.Surface,
        mission_name: str,
        mission_clock: float,
        speed_mult: float,
        fps: float,
        nav_status: str,
        battery: float,
        detection_summary: dict[str, int],
        event_log: list[str],
        controls_hint: str = "[S] shark  [W] swimmer  [F] surfer  [B] bug  [Esc] quit",
    ) -> None:
        """Draw the HUD panel onto the screen surface."""
        w, _ = screen.get_size()

        # Background panel (right side)
        panel_w = 320
        panel_surf = pygame.Surface((panel_w, 600), pygame.SRCALPHA)
        panel_surf.fill(self.BG_COLOR)

        y = 10
        lines: list[tuple[str, tuple[int, int, int]]] = []

        # Mission info
        lines.append((f"MISSION: {mission_name}", self.HIGHLIGHT_COLOR))
        lines.append((f"TIME: {mission_clock:06.1f}s  SPEED: {speed_mult}×  FPS: {fps:.0f}", self.TEXT_COLOR))
        lines.append(("", self.TEXT_COLOR))

        # Nav status
        lines.append((f"NAV: {nav_status}", self.TEXT_COLOR))
        battery_color = self.WARN_COLOR if battery < 0.2 else self.TEXT_COLOR
        lines.append((f"BATTERY: {battery * 100:.0f}%", battery_color))
        lines.append(("", self.TEXT_COLOR))

        # Detections
        lines.append(("DETECTIONS:", self.HIGHLIGHT_COLOR))
        if detection_summary:
            for label, count in detection_summary.items():
                lines.append((f"  ● {count} {label}(s)", self.TEXT_COLOR))
        else:
            lines.append(("  (none)", self.TEXT_COLOR))
        lines.append(("", self.TEXT_COLOR))

        # Event log (last 5)
        lines.append(("EVENTS:", self.HIGHLIGHT_COLOR))
        if event_log:
            for entry in event_log[-5:]:
                color = self.WARN_COLOR if "shark" in entry.lower() else self.TEXT_COLOR
                lines.append((f"  • {entry[:50]}", color))
        else:
            lines.append(("  (none)", self.TEXT_COLOR))
        lines.append(("", self.TEXT_COLOR))

        # Controls hint
        lines.append((controls_hint, (150, 150, 180)))

        # Render all lines
        for text, color in lines:
            if text == "":
                y += 8
                continue
            surf = self._font.render(text, True, color)
            panel_surf.blit(surf, (10, y))
            y += 22

        screen.blit(panel_surf, (w - panel_w - 10, 10))