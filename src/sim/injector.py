"""EventInjector — handles keyboard events for the SimTestbench."""

from __future__ import annotations

import pygame


class EventInjector:
    """Handles keyboard events for the SimTestbench.

    Maps key presses to testbench actions (spawn, pause, reset, quit, etc.).
    """

    def __init__(self, testbench: object) -> None:
        self._tb = testbench

    def handle_key(self, key: int) -> None:
        """Dispatch a single KEYDOWN event to the appropriate testbench action."""
        if key == pygame.K_SPACE:
            self._tb.toggle_pause()
        elif key == pygame.K_s:
            self._tb.spawn_entity("shark")
        elif key == pygame.K_w:
            self._tb.spawn_entity("swimmer")
        elif key == pygame.K_f:
            self._tb.spawn_entity("surfer")
        elif key == pygame.K_r:
            self._tb.reset()
        elif key == pygame.K_ESCAPE:
            self._tb.quit()
        elif key == pygame.K_1:
            self._tb.set_speed(1.0)
        elif key == pygame.K_2:
            self._tb.set_speed(2.0)
        elif key == pygame.K_3:
            self._tb.set_speed(5.0)