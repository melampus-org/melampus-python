"""Exercise the actual entry point; the SDK carries the assertions."""

from pricing import price

for cents in (-1, 0, 1200, 10000, 12000):
    price(cents)
