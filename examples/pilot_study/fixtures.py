from pathlib import Path

STYLES = ("wrapper", "class", "module")
ORDERS = (
    ("wrapper", "class", "module"),
    ("wrapper", "module", "class"),
    ("class", "wrapper", "module"),
    ("class", "module", "wrapper"),
    ("module", "wrapper", "class"),
    ("module", "class", "wrapper"),
)


def namespace(style: str) -> str:
    return "pilot:PricingService" if style == "class" else "pilot"


def path_for(style: str, method: str) -> str:
    return f"{namespace(style)}{'.' if style == 'class' else ':'}{method}"


def business(style: str) -> str:
    if style == "class":
        return """class PricingService:
    def price(self, cents: int) -> int:
        return max(0, cents)

    def discount(self, cents: int) -> int:
        return max(0, cents) * 9 // 10

    def label(self) -> str:
        return "cents"
"""
    return """def price(cents: int) -> int:
    return max(0, cents)


def discount(cents: int) -> int:
    return max(0, cents) * 9 // 10


def label() -> str:
    return "cents"
"""


def entry(style: str) -> str:
    if style == "class":
        return "from business import PricingService\n\napi = PricingService()\n"
    return "from types import SimpleNamespace\nfrom business import price, discount, label\n\napi = SimpleNamespace(price=price, discount=discount, label=label)\n"


def reviewed(style: str, second: bool) -> dict[str, str]:
    registry = repr(path_for(style, "price")) + ": PRICE"
    if second:
        registry += ", " + repr(path_for(style, "discount")) + ": DISCOUNT"
    return {
        "intent.py": """from melampus import Check, Contract

PRICE = Contract("Return a nonnegative price", (Check("nonnegative", lambda n: type(n) is int and n >= 0, "Price is a nonnegative integer"),))
DISCOUNT = Contract("Return a nonnegative integer discounted price", (Check("integer", lambda n: type(n) is int and n >= 0, "Discount is a nonnegative integer"),))
CONTRACTS = {"""
        + registry
        + "}\n",
        "exercise.py": """from entry import api

for cents in (-100, 0, 250):
    api.price(cents)
    api.discount(cents)
    api.label()
""",
        "melampus.toml": 'contracts = "intent"\nprobe = "exercise.py"\nwatch = ["business.py", "entry.py"]\ntimeout = 5\n',
    }


def install_reviewed(root: Path, style: str, second: bool) -> None:
    for name, content in reviewed(style, second).items():
        (root / name).write_text(content)


def solution(root: Path, style: str, second: bool) -> None:
    """Reference solution used only by synthetic collection checks."""
    imports = "from intent import PRICE" + (", DISCOUNT" if second else "") + "\n"
    if style == "wrapper":
        source = business(style).replace(
            "def price(", '@PRICE.instrument(path="pilot:price")\ndef price('
        )
        if second:
            source = source.replace(
                "def discount(", '@DISCOUNT.instrument(path="pilot:discount")\ndef discount('
            )
        (root / "business.py").write_text(imports + "\n" + source)
    else:
        source = entry(style)
        target = (
            "PricingService()"
            if style == "class"
            else "SimpleNamespace(price=price, discount=discount, label=label)"
        )
        source = source.replace(
            "api = " + target,
            "from melampus import instrument\n"
            + imports
            + "\napi = instrument("
            + target
            + f", namespace={namespace(style)!r}, contracts={{'price': PRICE"
            + (", 'discount': DISCOUNT" if second else "")
            + "})",
        )
        (root / "entry.py").write_text(source)


def seed_drift(root: Path) -> None:
    file = root / "business.py"
    source = file.read_text()
    if "return max(0, cents)" not in source:
        raise ValueError("Restore the original price expression before the drift task.")
    file.write_text(source.replace("return max(0, cents)", "return min(0, cents)", 1))


def coverage_questions(style: str) -> list[dict[str, str]]:
    boundary = {
        "class": "new PricingService().price(-100) on an UNREGISTERED instance",
        "module": "calling price imported directly from business.py before registration",
        "wrapper": "calling the raw implementation via __wrapped__ instead of the wrapper",
    }
    return [
        {
            "id": "registered",
            "prompt": "api.price(-100), after integration, with a recording tracer",
            "expected": "covered",
        },
        {
            "id": "omitted",
            "prompt": "api.label(), which has no configured contract",
            "expected": "uncovered",
        },
        {
            "id": "captured",
            "prompt": "Calling a raw price reference captured BEFORE wrapping",
            "expected": "uncovered",
        },
        {"id": "boundary", "prompt": boundary[style], "expected": "uncovered"},
        {
            "id": "missing",
            "prompt": "Required price AND discount, but only price is exercised. Gate?",
            "expected": "incomplete",
        },
        {
            "id": "aggregate",
            "prompt": "Price fails once and passes later in the same scenario. Gate?",
            "expected": "drift",
        },
    ]
