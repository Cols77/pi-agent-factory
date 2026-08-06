from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[3] / "src" / "factory"


def test_the_factory_ships_no_drone_metric_module():
    assert not (_SRC / "validation" / "metrics").exists()


def test_no_factory_source_mentions_the_drone_trigger_label():
    # Test fixtures may name a shark; the factory's own source may not. Metrics
    # score a product's behaviour, so they belong to the product's repository.
    offenders = [
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if "shark" in path.read_text(encoding="utf-8").lower()
    ]
    assert offenders == []
