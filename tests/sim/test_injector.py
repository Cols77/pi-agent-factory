"""Tests for EventInjector keyboard dispatch."""

from __future__ import annotations

import pytest
import pygame

pytestmark = pytest.mark.unit


class TestEventInjectorBugCapture:
    def test_handle_key_b_dispatches_to_open_bug_capture(self):
        """Pressing B calls _open_bug_capture on the injector."""
        from sim.injector import EventInjector

        called = False

        class MockTestbench:
            def toggle_pause(self):
                pass

            def spawn_entity(self, label):
                pass

            def reset(self):
                pass

            def quit(self):
                pass

            def set_speed(self, mult):
                pass

        tb = MockTestbench()
        injector = EventInjector(tb)

        # Monkey-patch _open_bug_capture to verify it's called
        original_method = getattr(injector, "_open_bug_capture", None)
        if original_method is None:
            pytest.fail("EventInjector is missing _open_bug_capture method")

        def _mock_open():
            nonlocal called
            called = True

        injector._open_bug_capture = _mock_open
        injector.handle_key(pygame.K_b)
        assert called, "handle_key(K_b) should call _open_bug_capture"

    def test_injector_has_kb_handler(self):
        """EventInjector.handle_key handles K_b key."""
        from sim.injector import EventInjector

        # Verify the handle_key method recognises K_b
        import inspect
        source = inspect.getsource(EventInjector.handle_key)
        assert "K_b" in source, "handle_key should have a K_b branch"