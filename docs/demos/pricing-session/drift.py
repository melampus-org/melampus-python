from intent import PRICE


@PRICE.instrument(generator="example")
def price(cents: int) -> int:
    return cents
