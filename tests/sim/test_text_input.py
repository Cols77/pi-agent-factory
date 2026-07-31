"""Tests for the TextInput pygame dialog widget (headless, no display)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import pygame


@pytest.fixture(autouse=True)
def pygame_init():
    """Initialize pygame modules for headless tests."""
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def screen() -> pygame.Surface:
    """A minimal off-screen surface (no display needed)."""
    return pygame.Surface((640, 480))


def key_event(key: int, unicode: str = "") -> pygame.event.Event:
    """Build a synthetic KEYDOWN event."""
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode)


class TestTextInputWidget:
    def test_import(self):
        """TextInput imports cleanly."""
        from sim.text_input import TextInput

        assert True

    def test_style_constants(self):
        """Panel and font style constants are valid."""
        from sim.text_input import PANEL_WIDTH, PANEL_HEIGHT, FONT_SIZE

        assert PANEL_WIDTH > 0
        assert PANEL_HEIGHT > 0
        assert FONT_SIZE > 0

    def test_initial_state(self, screen):
        """A new dialog starts empty, not done, and not cancelled."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        assert dialog.text == ""
        assert dialog.cancelled is False
        assert dialog.is_done() is False

    def test_typing_appends_text(self, screen):
        """Printable characters are appended in order."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        for ch in "abc":
            dialog.handle_event(key_event(pygame.K_a, unicode=ch))
        assert dialog.text == "abc"

    def test_backspace_removes_last_char(self, screen):
        """Backspace deletes the last character."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        for ch in "hello":
            dialog.handle_event(key_event(pygame.K_a, unicode=ch))
        dialog.handle_event(key_event(pygame.K_BACKSPACE))
        assert dialog.text == "hell"
        dialog.handle_event(key_event(pygame.K_BACKSPACE))
        assert dialog.text == "hel"

    def test_backspace_on_empty_is_noop(self, screen):
        """Backspace on empty text does not crash."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        dialog.handle_event(key_event(pygame.K_BACKSPACE))
        assert dialog.text == ""

    def test_enter_confirms(self, screen):
        """Enter marks the dialog done without cancelling."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        for ch in "save":
            dialog.handle_event(key_event(pygame.K_a, unicode=ch))
        dialog.handle_event(key_event(pygame.K_RETURN))
        assert dialog.is_done() is True
        assert dialog.cancelled is False
        assert dialog.text == "save"

    def test_escape_cancels(self, screen):
        """Escape marks the dialog done and cancelled."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        for ch in "no":
            dialog.handle_event(key_event(pygame.K_a, unicode=ch))
        dialog.handle_event(key_event(pygame.K_ESCAPE))
        assert dialog.is_done() is True
        assert dialog.cancelled is True

    def test_caps_text_at_200_chars(self, screen):
        """Text input is capped at 200 characters."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        for _ in range(250):
            dialog.handle_event(key_event(pygame.K_a, unicode="x"))
        assert len(dialog.text) == 200

    def test_non_printable_unicode_ignored(self, screen):
        """Control characters are not appended."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        # 0x07 (bell) is not printable
        dialog.handle_event(key_event(pygame.K_a, unicode="\x07"))
        assert dialog.text == ""

    def test_missing_unicode_ignored(self, screen):
        """KEYDOWN events without unicode (e.g. special keys) are ignored."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        dialog.handle_event(key_event(pygame.K_UP))
        assert dialog.text == ""

    def test_draw_does_not_crash(self, screen):
        """Drawing the dialog on a surface does not raise."""
        from sim.text_input import TextInput

        dialog = TextInput(screen, "Prompt:")
        dialog.draw()
        assert True
