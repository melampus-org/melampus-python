from types import SimpleNamespace

from functions import label, price
from intent import PRICE
from service import PricingService

from melampus import instrument

service = instrument(
    PricingService(), namespace="pricing:PricingService", contracts={"price": PRICE}
)
pricing = instrument(
    SimpleNamespace(price=price, label=label), namespace="pricing", contracts={"price": PRICE}
)
