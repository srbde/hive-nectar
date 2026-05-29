import pytest

from nectar.asciichart import AsciiChart


@pytest.fixture
def curve():
    return [1.2, 4.3, 2.0, -1.3, 6.4, 0.0]


def test_plot(curve):
    ac = AsciiChart(height=3, width=3)
    assert len(ac.canvas) == 0
    ret = ac.plot(curve, return_str=True)
    ac.plot(curve, return_str=False)
    assert len(ret) > 0
    ac.clear_data()
    assert len(ac.canvas) == 0


def test_plot2(curve):
    ac = AsciiChart(height=3, width=3)
    ac.clear_data()
    ac.adapt_on_series(curve)
    assert ac.maximum == max(curve)
    assert ac.minimum == min(curve)
    assert ac.n == len(curve)
    ac.new_chart()
    ac.add_axis()
    ac.add_curve(curve)
