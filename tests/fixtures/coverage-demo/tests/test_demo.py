from demo.feature import preempt


def test_preempt_on_detection() -> None:
    assert preempt(True) is True
