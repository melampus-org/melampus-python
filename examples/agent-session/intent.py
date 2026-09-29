"""Review these claims once before the agent starts implementing them."""

from melampus import Check, Contract

PRICE = Contract(
    intent="Return a nonnegative integer price in cents, capped at 10000 cents.",
    checks=(
        Check("integer_cents", lambda value: type(value) is int, "Price uses integer cents."),
        Check("nonnegative", lambda value: value >= 0, "Price is never negative."),
        Check("capped", lambda value: value <= 10000, "Price never exceeds 10000 cents."),
    ),
)

CONTRACTS = {"pricing:price": PRICE}
