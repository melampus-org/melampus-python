from intent import PRICE


@PRICE.instrument(path="wrapper:price")
def price(cents: int) -> int:
    return max(0, cents)
