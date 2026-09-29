"""Behavioral tests equivalent to the reviewed Melampus pricing claims."""

import pytest
from pricing import price


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (-1, 0),
        (0, 0),
        (1200, 1200),
        (10000, 10000),
        (12000, 10000),
    ],
)
def test_price_is_bounded(cents: int, expected: int) -> None:
    result = price(cents)
    assert type(result) is int
    assert result == expected
