"""EventInjector — handles keyboard events for the SimTestbench."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from sim.testbench import SimTestbench


class EventInjector:
    """Handles keyboard events for the SimTestbench.

    Maps key presses to testbench actions (spawn, pause, reset, quit, etc.).
    """

    def __init__(self, testbench: SimTestbench) -> None:
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
        elif key == pygame.K_b:
            self._open_bug_capture()
        elif key == pygame.K_p:
            self._save_screenshot()

    def _save_screenshot(self) -> None:
        from datetime import datetime
        from pathlib import Path
        screenshots_dir = Path("screenshots")
        screenshots_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = screenshots_dir / f"{self._tb.scenario.name}_{ts}.png"
        pygame.image.save(self._tb.screen, str(path))
        print(f"Screenshot saved: {path}")

    def _open_bug_capture(self) -> None:
        from sim.text_input import TextInput
        from sim.bug_capture import capture_bug

        self._tb.pause()
        dialog = TextInput(self._tb.screen, "What went wrong?")
        clock = pygame.time.Clock()

        while not dialog.is_done():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                dialog.handle_event(event)

            # Redraw frame with dialog overlay
            self._tb._draw_frame()
            dialog.draw()
            pygame.display.flip()
            clock.tick(30)

        if not dialog.cancelled and dialog.text.strip():
            capture_bug(self._tb, dialog.text.strip())