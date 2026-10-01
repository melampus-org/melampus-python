from melampus import Check, Contract

PRICE = Contract(
    "Return a nonnegative price in cents",
    (
        Check(
            "nonnegative",
            lambda value: type(value) is int and value >= 0,
            "Price is a nonnegative integer.",
        ),
    ),
)
CONTRACTS = {
    "wrapper:price": PRICE,
    "pricing:PricingService.price": PRICE,
    "pricing:price": PRICE,
}
