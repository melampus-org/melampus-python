"""Small OTel API-only instrumentation; applications own export configuration."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from . import _semconv as sc

P = ParamSpec("P")
R = TypeVar("R")
SCHEMA_VERSION = "0.1.0"
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
MAX_CHECKS = 16


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Check:
    """A pure synchronous predicate over a function's successful return value."""

    id: str
    predicate: Callable[[Any], bool]
    contract: str
    sample: float = 1.0

    def __post_init__(self) -> None:
        if not IDENTIFIER.fullmatch(self.id):
            raise ValueError("check id must be 1–64 ASCII identifier characters")
        if not isinstance(self.contract, str) or not self.contract:
            raise ValueError("contract must be nonempty text")
        if not callable(self.predicate) or inspect.iscoroutinefunction(self.predicate):
            raise ValueError("predicate must be a synchronous callable")
        if not math.isfinite(self.sample) or not 0 <= self.sample <= 1:
            raise ValueError("sample must be finite and between 0 and 1")


class Policy:
    """Shared, thread-safe per-process fixed-window check execution policy.

    None means unlimited; zero disables execution through budget suppression.
    Call configure() to change limits or exact module:qualified_name paths.
    Checks already admitted are not interrupted by a configuration change.
    """

    def __init__(
        self,
        checks_per_second: int | None = None,
        disabled_paths: Sequence[str] = (),
    ) -> None:
        self._lock = threading.Lock()
        self.configure(checks_per_second=checks_per_second, disabled_paths=disabled_paths)

    def configure(
        self,
        *,
        checks_per_second: int | None = None,
        disabled_paths: Sequence[str] = (),
    ) -> None:
        if checks_per_second is not None and (
            type(checks_per_second) is not int or checks_per_second < 0
        ):
            raise ValueError("checks_per_second must be a nonnegative integer or None")
        if isinstance(disabled_paths, str) or any(not isinstance(p, str) for p in disabled_paths):
            raise ValueError("disabled_paths must be a sequence of function paths")
        with self._lock:
            self._limit = checks_per_second
            self._disabled = frozenset(disabled_paths)
            self._window = int(time.monotonic())
            self._used = 0

    def admit(self, path: str, sampled: bool) -> str | None:
        with self._lock:
            if path in self._disabled:
                return "disabled"
            if not sampled:
                return "sampled_out"
            window = int(time.monotonic())
            if window != self._window:
                self._window, self._used = window, 0
            if self._limit is not None and self._used >= self._limit:
                return "budget"
            self._used += 1
            return None


DEFAULT_POLICY = Policy()


def _sampled(check: Check, span: Span) -> bool:
    if check.sample in (0, 1):
        return check.sample == 1
    ctx = span.get_span_context()
    seed = f"{ctx.trace_id:032x}:{ctx.span_id:016x}:{check.id}"
    value = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")
    return value < int(check.sample * (1 << 64))


def _evaluate(
    span: Span, checks: tuple[Check, ...], result: Any, path: str, policy: Policy
) -> None:
    outcomes = []
    for check in checks:
        reason = policy.admit(path, _sampled(check, span))
        if reason:
            outcomes.append(reason)
            continue
        try:
            verdict = check.predicate(result)
            if type(verdict) is not bool:
                # Defensive cleanup for callable objects that return coroutine objects.
                if inspect.iscoroutine(verdict):
                    verdict.close()
                outcomes.append("error")
            else:
                outcomes.append("passed" if verdict else "failed")
        except Exception:
            # No exception details: check errors can contain application secrets.
            outcomes.append("error")
    span.set_attribute(sc.CHECK_RESULTS, outcomes)


def instrumented(
    *,
    intent: str,
    checks: Sequence[Check] = (),
    assumptions: Sequence[str] = (),
    generator: str = "unspecified",
    policy: Policy | None = None,
    tracer: Tracer | None = None,
    capture_content: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Declare intent and evaluate checks on sync or async function return values.

    Generators are rejected because their execution outlives an ordinary call.
    Content capture is reserved and unsupported in the first release.
    """
    if capture_content:
        raise NotImplementedError("content capture is not supported in schema 0.1.0")
    if not isinstance(intent, str) or not intent:
        raise ValueError("intent must be nonempty text")
    if not IDENTIFIER.fullmatch(generator):
        raise ValueError("generator must be 1–64 ASCII identifier characters")
    if isinstance(assumptions, str) or any(not isinstance(a, str) for a in assumptions):
        raise ValueError("assumptions must be a sequence of strings")
    frozen_checks = tuple(checks)
    if len(frozen_checks) > MAX_CHECKS or len({c.id for c in frozen_checks}) != len(frozen_checks):
        raise ValueError("checks must have unique IDs and contain at most 16 entries")
    selected_policy = DEFAULT_POLICY if policy is None else policy
    selected_tracer = tracer if tracer is not None else trace.get_tracer("melampus", SCHEMA_VERSION)
    declaration: dict[str, Any] = {
        sc.SCHEMA_VERSION: SCHEMA_VERSION,
        sc.GENERATOR: generator,
        sc.INTENT_HASH: _hash(intent),
        sc.ASSUMPTIONS_HASH: _hash(
            json.dumps(list(assumptions), ensure_ascii=False, separators=(",", ":"))
        ),
        sc.CHECK_IDS: tuple(c.id for c in frozen_checks),
        sc.CHECK_CONTRACT_HASHES: tuple(_hash(c.contract) for c in frozen_checks),
        sc.CHECK_SAMPLE_RATES: tuple(float(c.sample) for c in frozen_checks),
        sc.CHECK_RESULTS: tuple("not_executed" for _ in frozen_checks),
    }

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
            raise TypeError("generator functions are not supported")
        path = f"{function.__module__}:{function.__qualname__}"
        if len(path) > 256 or not path.isprintable():
            raise ValueError("function path must contain at most 256 printable characters")
        attributes = {**declaration, sc.FUNCTION: path}

        def start() -> Any:
            return selected_tracer.start_as_current_span(
                path,
                attributes=attributes,
                record_exception=False,
                set_status_on_exception=False,
            )

        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                with start() as span:
                    try:
                        result = await function(*args, **kwargs)
                    except BaseException:
                        span.set_status(Status(StatusCode.ERROR))
                        raise
                    if frozen_checks and span.is_recording():
                        _evaluate(span, frozen_checks, result, path, selected_policy)
                    return result

            return cast(Callable[P, R], async_wrapper)

        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with start() as span:
                try:
                    result = function(*args, **kwargs)
                except BaseException:
                    span.set_status(Status(StatusCode.ERROR))
                    raise
                if frozen_checks and span.is_recording():
                    _evaluate(span, frozen_checks, result, path, selected_policy)
                return result

        return wrapper

    return decorate
