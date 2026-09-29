from intent import PRICE


@PRICE.instrument(generator="example")
def price(cents: int) -> int:
    return max(0, min(int(cents), 10000))
