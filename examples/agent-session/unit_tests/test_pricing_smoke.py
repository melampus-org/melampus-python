"""A common fast unit test: one representative input and expected output."""

from pricing import price


def test_typical_price() -> None:
    assert price(1200) == 1200
