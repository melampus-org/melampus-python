from intent import PRICE


@PRICE.instrument(generator="example")
def price(cents: int) -> int:
    return min(10000, max(0, cents))
