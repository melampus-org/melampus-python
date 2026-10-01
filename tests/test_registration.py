import asyncio
import inspect
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace

import pytest

from melampus import Check, Contract, Policy, instrument, instrumented

PRICE = Contract("Return a nonnegative price", (Check("nonnegative", lambda n: n >= 0, "n >= 0"),))


class Base:
    def price(self, cents: int, *, fee: int = 0) -> int:
        """Price with instance state."""
        return max(0, cents) + self._fee + fee


@dataclass
class Service(Base):
    _fee: int = 2

    def quote(self, cents: int) -> int:
        return self.price(cents)

    async def async_price(self, cents: int) -> int:
        await asyncio.sleep(0)
        return self.price(cents)


def attrs(exporter):
    return [span.attributes for span in exporter.get_finished_spans()]


def test_inherited_method_binding_signature_identity_and_unhashable_target(telemetry):
    tracer, exporter = telemetry
    service, other = Service(), Service(5)
    original = service.price
    returned = instrument(
        service, namespace="pricing:Service", contracts={"price": PRICE}, tracer=tracer
    )
    assert returned is service
    assert inspect.signature(service.price) == inspect.signature(original)
    assert service.price.__name__ == original.__name__
    assert service.price.__doc__ == original.__doc__
    assert service.price(-10, fee=3) == 5
    assert original(-10) == 2  # captured bound method bypasses
    assert other.price(-10) == 5  # no class mutation
    assert Base.price(service, -10) == 2  # direct class call bypasses
    assert "price" not in Service.__dict__ and "price" not in vars(other)
    assert len(attrs(exporter)) == 1
    assert attrs(exporter)[0]["code_artifact.function"] == "pricing:Service.price"
    assert attrs(exporter)[0]["code_artifact.check.results"] == ("passed",)
    with pytest.raises(TypeError, match="already instrumented"):
        instrument(service, namespace="pricing", contracts={"price": PRICE})


def test_async_methods_and_internal_calls_use_registered_instance(telemetry):
    tracer, exporter = telemetry
    service = instrument(
        Service(),
        namespace="pricing:Service",
        contracts={"price": PRICE, "async_price": PRICE},
        tracer=tracer,
    )
    assert inspect.iscoroutinefunction(service.async_price)
    assert asyncio.run(service.async_price(-10)) == 2
    assert service.quote(-10) == 2
    assert [a["code_artifact.function"] for a in attrs(exporter)] == [
        "pricing:Service.price",
        "pricing:Service.async_price",
        "pricing:Service.price",
    ]


@pytest.mark.parametrize("kind", [SimpleNamespace, lambda: ModuleType("pricing")])
def test_own_functions_modules_captured_references_and_omitted_methods(telemetry, kind):
    tracer, exporter = telemetry
    target = kind()
    target.price = lambda cents: max(0, cents)
    target.label = lambda: "cents"
    original = target.price
    instrument(target, namespace="pricing", contracts={"price": PRICE}, tracer=tracer)
    assert target.price(-10) == 0 and target.label() == "cents"
    assert original(-10) == 0
    assert len(attrs(exporter)) == 1
    assert attrs(exporter)[0]["code_artifact.function"] == "pricing:price"


def test_policy_uses_explicit_registered_path(telemetry):
    tracer, exporter = telemetry
    policy = Policy(disabled_paths=["pricing:Service.price"])
    instrument(
        Service(),
        namespace="pricing:Service",
        contracts={"price": PRICE},
        policy=policy,
        tracer=tracer,
    ).price(1)
    assert attrs(exporter)[0]["code_artifact.check.results"] == ("disabled",)


def test_failure_and_async_exception_cancel_preserve_application_behavior(telemetry):
    tracer, exporter = telemetry
    original = ValueError("private exception")

    class Broken:
        def price(self):
            return -1

        async def fail(self):
            raise original

        async def cancel(self):
            raise asyncio.CancelledError()

    target = instrument(
        Broken(),
        namespace="pricing:Broken",
        contracts={k: PRICE for k in ("price", "fail", "cancel")},
        tracer=tracer,
    )
    assert target.price() == -1
    with pytest.raises(ValueError) as caught:
        asyncio.run(target.fail())
    assert caught.value is original
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(target.cancel())
    assert attrs(exporter)[0]["code_artifact.check.results"] == ("failed",)
    assert all(not s.events for s in exporter.get_finished_spans())


def test_descriptors_are_never_evaluated_and_validation_is_atomic():
    touched = []

    class Properties(Service):
        @property
        def secret(self):
            touched.append(True)
            raise AssertionError("property evaluated")

        @staticmethod
        def static():
            return 0

        @classmethod
        def class_method(cls):
            return 0

    for key in ("secret", "static", "class_method", "missing"):
        target = Properties()
        with pytest.raises(TypeError):
            instrument(target, namespace="pricing", contracts={"price": PRICE, key: PRICE})
        assert "price" not in vars(target)
        # A failed plan has not marked the object as registered.
        instrument(target, namespace="pricing", contracts={"price": PRICE})
    assert not touched


def test_shadowed_data_and_dictionary_descriptors_are_rejected_without_execution():
    touched = []

    class Shadow(Service):
        @property
        def price(self):
            touched.append(True)
            return lambda: 0

    target = Shadow()
    vars(target)["price"] = lambda: 0
    with pytest.raises(TypeError, match="unsupported descriptor"):
        instrument(target, namespace="pricing", contracts={"price": PRICE})

    class Dictionary:
        @property
        def __dict__(self):
            touched.append(True)
            return {}

    with pytest.raises(TypeError, match="custom __dict__"):
        instrument(Dictionary(), namespace="pricing", contracts={"price": PRICE})
    assert not touched


@pytest.mark.parametrize("namespace", ["", ":", "a:", ":b", "a:b:c", "a\n", "x" * 256, None])
def test_invalid_namespace_or_derived_path(namespace):
    target = Service()
    with pytest.raises(ValueError):
        instrument(target, namespace=namespace, contracts={"price": PRICE})
    assert "price" not in vars(target)


@pytest.mark.parametrize(
    "contracts", [{}, {"missing": PRICE}, {"price": "bad"}, {"_private": PRICE}, {1: PRICE}, []]
)
def test_invalid_contract_maps(contracts):
    with pytest.raises(TypeError):
        instrument(Service(), namespace="pricing", contracts=contracts)


def test_unsupported_targets_and_nested_wrappers():
    class Slots:
        __slots__ = ()

    class Dynamic:
        def __getattr__(self, key):
            raise AssertionError("lookup invoked")

    class Frozen:
        def __setattr__(self, key, value):
            raise AssertionError("setter invoked")

    for target in (None, {}, [], Service, lambda: 0, Slots(), Dynamic(), Frozen()):
        with pytest.raises(TypeError):
            instrument(target, namespace="pricing", contracts={"price": PRICE})

    wrapped = SimpleNamespace(price=PRICE.instrument()(lambda: 0))
    with pytest.raises(TypeError, match="already instrumented"):
        instrument(wrapped, namespace="pricing", contracts={"price": PRICE})

    def generator():
        yield 1

    async def async_generator():
        yield 1

    for function in (generator, async_generator, 1, object()):
        with pytest.raises(TypeError):
            instrument(
                SimpleNamespace(price=function), namespace="pricing", contracts={"price": PRICE}
            )


def test_explicit_decorator_path_and_nonrecording_behavior(telemetry):
    tracer, exporter = telemetry
    price = PRICE.instrument(path="pricing:price")(lambda: 0)
    assert price() == 0  # API-only default provider is non-recording in this process
    assert not attrs(exporter)
    price = instrumented(
        intent=PRICE.intent, checks=PRICE.checks, tracer=tracer, path="pricing:price"
    )(lambda: 0)
    assert price() == 0
    assert attrs(exporter)[0]["code_artifact.function"] == "pricing:price"


@pytest.mark.parametrize("path", ["", "pricing", "a:", ":b", "a:b:c", "a:b\n", "a:" + "b" * 255, 1])
def test_explicit_path_is_validated(path):
    with pytest.raises(ValueError):
        instrumented(intent="price", path=path)
