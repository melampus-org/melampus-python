"""Static assertions: registration and decorators retain ordinary callable types."""

from typing import assert_type

from melampus import Check, Contract, instrument

PRICE = Contract("nonnegative", (Check("nonnegative", lambda n: n >= 0, "nonnegative"),))


class PricingService:
    def price(self, cents: int, *, fee: int = 0) -> int:
        return max(0, cents) + fee

    async def async_price(self, cents: int) -> int:
        return self.price(cents)


service = instrument(
    PricingService(),
    namespace="pricing:PricingService",
    contracts={"price": PRICE, "async_price": PRICE},
)
assert_type(service, PricingService)
assert_type(service.price(10, fee=1), int)


async def async_usage() -> None:
    assert_type(await service.async_price(10), int)


@PRICE.instrument(path="pricing:price")
def price(cents: int) -> int:
    return max(0, cents)


assert_type(price(10), int)
