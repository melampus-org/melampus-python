import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.trace import StatusCode

from melampus import Check, Policy, instrumented


def test_declares_hashes_and_preserves_return(telemetry):
    tracer, exporter = telemetry
    secret = "private contract text"
    returned = {"private": "not exported"}

    @instrumented(
        intent=secret,
        assumptions=["private assumption"],
        checks=[Check("present", lambda r: "private" in r, secret)],
        tracer=tracer,
    )
    def function():
        return returned

    assert function() is returned
    span = exporter.get_finished_spans()[0]
    attrs = span.attributes
    assert attrs["code_artifact.intent.hash"] == hashlib.sha256(secret.encode()).hexdigest()
    assert attrs["code_artifact.check.results"] == ("passed",)
    assert attrs["code_artifact.check.ids"] == ("present",)
    assert attrs["code_artifact.check.contract_hashes"] == (
        hashlib.sha256(secret.encode()).hexdigest(),
    )
    assert len(attrs) == 9
    assert not span.events
    assert "private" not in json.dumps(dict(attrs))
    assert function.__name__ == "function"


def test_failures_and_errors_do_not_change_result(telemetry):
    tracer, exporter = telemetry

    def error(result):
        raise RuntimeError("secret")

    @instrumented(
        intent="check result",
        checks=[
            Check("fail", lambda r: False, "false"),
            Check("error", error, "raises"),
            Check("bad", lambda r: 1, "non-bool"),
        ],
        tracer=tracer,
    )
    def function():
        return 42

    assert function() == 42
    span = exporter.get_finished_spans()[0]
    assert span.attributes["code_artifact.check.results"] == ("failed", "error", "error")
    assert "secret" not in str(span.attributes)
    assert not span.events


@pytest.mark.parametrize("async_call", [False, True])
def test_application_exception_preserved_without_content(telemetry, async_call):
    tracer, exporter = telemetry
    original = ValueError("private exception")
    calls = []
    decorator = instrumented(
        intent="secret", checks=[Check("check", lambda r: calls.append(r), "secret")], tracer=tracer
    )

    def fail():
        raise original

    async def async_fail():
        raise original

    with pytest.raises(ValueError) as caught:
        asyncio.run(decorator(async_fail)()) if async_call else decorator(fail)()
    assert caught.value is original
    assert not calls
    span = exporter.get_finished_spans()[0]
    assert span.attributes["code_artifact.check.results"] == ("not_executed",)
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description is None
    assert not span.events


def test_async_checks_observe_awaited_result_and_parent(telemetry):
    tracer, exporter = telemetry

    @instrumented(
        intent="async", checks=[Check("positive", lambda r: r > 0, "positive")], tracer=tracer
    )
    async def child(value):
        await asyncio.sleep(0)
        return value

    with tracer.start_as_current_span("parent") as parent:
        assert asyncio.run(child(3)) == 3
    child_span = exporter.get_finished_spans()[0]
    assert child_span.parent.span_id == parent.get_span_context().span_id
    assert child_span.attributes["code_artifact.check.results"] == ("passed",)


def test_cancellation_propagates(telemetry):
    tracer, exporter = telemetry

    @instrumented(intent="cancel", tracer=tracer)
    async def cancelled():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled())
    assert not exporter.get_finished_spans()[0].events


def test_sampling_and_budget_do_not_drop_declarations(telemetry):
    tracer, exporter = telemetry
    calls = []
    policy = Policy(checks_per_second=1)

    @instrumented(
        intent="check",
        checks=[
            Check("zero", lambda r: calls.append(r), "skip", sample=0),
            Check("run", lambda r: True, "run"),
        ],
        policy=policy,
        tracer=tracer,
    )
    def function():
        return 7

    with patch("melampus.sdk.time.monotonic", return_value=100):
        function()
        function()
    assert not calls
    spans = exporter.get_finished_spans()
    assert spans[0].attributes["code_artifact.check.results"] == ("sampled_out", "passed")
    assert spans[1].attributes["code_artifact.check.results"] == ("sampled_out", "budget")
    assert (
        spans[0].attributes["code_artifact.intent.hash"]
        == spans[1].attributes["code_artifact.intent.hash"]
    )
    policy.configure(disabled_paths=[spans[0].attributes["code_artifact.function"]])
    function()
    assert exporter.get_finished_spans()[-1].attributes["code_artifact.check.results"] == (
        "disabled",
        "disabled",
    )


def test_budget_is_shared_thread_safe_and_resets():
    policy = Policy(10)
    with patch("melampus.sdk.time.monotonic", return_value=123):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: policy.admit("path", True), range(200)))
        assert results.count(None) == 10
        assert results.count("budget") == 190
    with patch("melampus.sdk.time.monotonic", return_value=124):
        assert policy.admit("path", True) is None


def test_fractional_sampling_distribution(telemetry):
    tracer, exporter = telemetry
    calls = []

    def check(value):
        calls.append(value)
        return True

    @instrumented(
        intent="sample", checks=[Check("check", check, "sample", sample=0.25)], tracer=tracer
    )
    def function():
        return 1

    for _ in range(2000):
        function()
    assert 375 < len(calls) < 625
    assert len(exporter.get_finished_spans()) == 2000


def test_nonrecording_span_skips_predicates():
    provider = TracerProvider(sampler=ALWAYS_OFF)
    calls = []

    @instrumented(
        intent="off",
        checks=[Check("x", lambda r: calls.append(r), "off")],
        tracer=provider.get_tracer("off"),
    )
    def function():
        return 1

    assert function() == 1
    assert not calls
    provider.shutdown()


@pytest.mark.parametrize("sample", [-1, 2, float("nan"), float("inf")])
def test_invalid_sample(sample):
    with pytest.raises(ValueError):
        Check("x", lambda r: True, "contract", sample=sample)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"intent": ""},
        {"intent": "x", "assumptions": "bad"},
        {"intent": "x", "generator": "bad\n"},
        {"intent": "x", "checks": [Check("a", bool, "c")] * 2},
    ],
)
def test_invalid_declarations(kwargs):
    with pytest.raises(ValueError):
        instrumented(**kwargs)


def test_capture_and_generator_functions_rejected():
    with pytest.raises(NotImplementedError):
        instrumented(intent="x", capture_content=True)

    def generator():
        yield 1

    with pytest.raises(TypeError):
        instrumented(intent="x")(generator)


@pytest.mark.parametrize("limit", [-1, 1.5, True])
def test_invalid_budget(limit):
    with pytest.raises(ValueError):
        Policy(limit)
