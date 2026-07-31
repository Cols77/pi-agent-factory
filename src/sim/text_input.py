"""Text input dialog widget for pygame."""

from __future__ import annotations

import pygame

# Panel dimensions
PANEL_WIDTH = 600
PANEL_HEIGHT = 300
FONT_SIZE = 20


class TextInput:
    """A simple text input dialog overlay for pygame.

    Displays a modal dialog with a prompt, a text input field, and
    [Enter] save / [Esc] cancel hints. Handles keyboard input and
    draws itself onto the provided screen surface.

    Usage::

        dialog = TextInput(screen, "Enter description:")
        clock = pygame.time.Clock()
        while not dialog.is_done():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    ...
                dialog.handle_event(event)
            dialog.draw()
            pygame.display.flip()
            clock.tick(30)

        if not dialog.cancelled:
            text = dialog.text
    """

    def __init__(self, screen: pygame.Surface, prompt: str) -> None:
        self._screen = screen
        self._prompt = prompt
        self._text: str = ""
        self._done = False
        self._cancelled = False
        self._font = pygame.font.Font(None, FONT_SIZE)

    @property
    def text(self) -> str:
        """The text entered by the user so far."""
        return self._text

    @property
    def cancelled(self) -> bool:
        """True if the user pressed Escape to cancel."""
        return self._cancelled

    def handle_event(self, event: pygame.event.Event) -> None:
        """Process a single pygame event.

        Handles:
        - Return/Enter: confirm input
        - Escape: cancel
        - Backspace: delete last character
        - Printable characters: append to text (max 200 chars)
        """
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._done = True
            elif event.key == pygame.K_ESCAPE:
                self._cancelled = True
                self._done = True
            elif event.key == pygame.K_BACKSPACE:
                self._text = self._text[:-1]
            else:
                if len(self._text) < 200 and event.unicode.isprintable():
                    self._text += event.unicode

    def draw(self) -> None:
        """Draw the dialog overlay on the screen."""
        w, h = self._screen.get_size()
        panel_x = (w - PANEL_WIDTH) // 2
        panel_y = (h - PANEL_HEIGHT) // 2

        # Dim background
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self._screen.blit(overlay, (0, 0))

        # Panel background
        pygame.draw.rect(
            self._screen,
            (40, 40, 60),
            (panel_x, panel_y, PANEL_WIDTH, PANEL_HEIGHT),
            border_radius=8,
        )

        # Prompt text
        prompt_surf = self._font.render(self._prompt, True, (200, 200, 220))
        self._screen.blit(prompt_surf, (panel_x + 20, panel_y + 30))

        # Text input area
        input_rect = pygame.Rect(panel_x + 20, panel_y + 80, PANEL_WIDTH - 40, 40)
        pygame.draw.rect(self._screen, (60, 60, 80), input_rect, border_radius=4)
        pygame.draw.rect(self._screen, (100, 140, 255), input_rect, 2, border_radius=4)

        # Cursor blink
        display_text = self._text
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            display_text += "|"
        text_surf = self._font.render(display_text, True, (255, 255, 255))
        self._screen.blit(text_surf, (panel_x + 30, panel_y + 88))

        # Hint text
        hint = self._font.render("[Enter] save  [Esc] cancel", True, (150, 150, 180))
        self._screen.blit(hint, (panel_x + 20, panel_y + PANEL_HEIGHT - 40))

    def is_done(self) -> bool:
        """Return True if the dialog has been confirmed or cancelled."""
        return self._done