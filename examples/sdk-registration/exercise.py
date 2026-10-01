from registration import pricing, service
from wrapper import price

for cents in (-100, 0, 250):
    price(cents)
    service.price(cents)
    pricing.price(cents)
    pricing.label()  # Deliberately unconfigured; this call produces no Melampus check.
