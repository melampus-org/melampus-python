class PricingService:
    def __init__(self, fee: int = 0) -> None:
        self._fee = fee

    def price(self, cents: int) -> int:
        return max(0, cents) + self._fee
