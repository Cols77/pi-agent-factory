"""Basic smoke tests for SimTestbench, EventInjector, and __main__."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestSimTestbenchImport:
    """SimTestbench should import cleanly."""

    def test_import_testbench(self):
        from sim.testbench import SimTestbench

        assert SimTestbench is not None

    def test_import_injector(self):
        from sim.injector import EventInjector

        assert EventInjector is not None

    def test_import_main(self):
        from sim.__main__ import main

        assert main is not None


class TestEventInjectorKeyHandling:
    """EventInjector should dispatch key events to the correct testbench methods."""

    @pytest.fixture
    def mock_tb(self):
        """A minimal mock object implementing the SimTestbench interface."""
        import types

        tb = types.SimpleNamespace()
        tb.toggle_pause = lambda: None
        tb.spawn_entity = lambda label: None
        tb.reset = lambda: None
        tb.quit = lambda: None
        tb.set_speed = lambda mult: None
        return tb

    def test_space_toggles_pause(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.toggle_pause = lambda: calls.append("toggle_pause")

        injector.handle_key(pygame.K_SPACE)

        assert calls == ["toggle_pause"]

    def test_s_spawns_shark(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.spawn_entity = lambda label: calls.append(("spawn_entity", label))

        injector.handle_key(pygame.K_s)

        assert calls == [("spawn_entity", "shark")]

    def test_w_spawns_swimmer(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.spawn_entity = lambda label: calls.append(("spawn_entity", label))

        injector.handle_key(pygame.K_w)

        assert calls == [("spawn_entity", "swimmer")]

    def test_f_spawns_surfer(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.spawn_entity = lambda label: calls.append(("spawn_entity", label))

        injector.handle_key(pygame.K_f)

        assert calls == [("spawn_entity", "surfer")]

    def test_r_resets(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.reset = lambda: calls.append("reset")

        injector.handle_key(pygame.K_r)

        assert calls == ["reset"]

    def test_escape_quits(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.quit = lambda: calls.append("quit")

        injector.handle_key(pygame.K_ESCAPE)

        assert calls == ["quit"]

    def test_1_sets_speed_1x(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.set_speed = lambda mult: calls.append(("set_speed", mult))

        injector.handle_key(pygame.K_1)

        assert calls == [("set_speed", 1.0)]

    def test_2_sets_speed_2x(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.set_speed = lambda mult: calls.append(("set_speed", mult))

        injector.handle_key(pygame.K_2)

        assert calls == [("set_speed", 2.0)]

    def test_3_sets_speed_5x(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.set_speed = lambda mult: calls.append(("set_speed", mult))

        injector.handle_key(pygame.K_3)

        assert calls == [("set_speed", 5.0)]

    def test_unknown_key_does_nothing(self, mock_tb):
        from sim.injector import EventInjector
        import pygame

        injector = EventInjector(mock_tb)
        calls = []
        mock_tb.toggle_pause = lambda: calls.append("toggle_pause")
        mock_tb.spawn_entity = lambda label: calls.append(("spawn_entity", label))
        mock_tb.reset = lambda: calls.append("reset")
        mock_tb.quit = lambda: calls.append("quit")
        mock_tb.set_speed = lambda mult: calls.append(("set_speed", mult))

        # Press an unmapped key (F1)
        injector.handle_key(pygame.K_F1)

        assert calls == [], "Unknown key should not trigger any action"


class TestMainCli:
    """Test the __main__.py CLI entry point."""

    def test_main_returns_1_when_no_args(self):
        """Without args, main() should return 1 and print usage."""
        from sim.__main__ import main
        import sys

        old_argv = sys.argv
        try:
            sys.argv = ["sim"]
            result = main()
            assert result == 1
        finally:
            sys.argv = old_argv

    def test_main_returns_1_when_file_not_found(self):
        """With a nonexistent file, main() should return 1."""
        from sim.__main__ import main
        import sys

        old_argv = sys.argv
        try:
            sys.argv = ["sim", "/nonexistent/scenario.yaml"]
            result = main()
            assert result == 1
        finally:
            sys.argv = old_argv