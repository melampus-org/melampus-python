"""Explicit, per-object registration without changing classes or evaluating properties."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from types import (
    GetSetDescriptorType,
    MemberDescriptorType,
    MethodType,
    ModuleType,
    SimpleNamespace,
)
from typing import Any, TypeVar

from opentelemetry.trace import Tracer

from .contracts import Contract
from .sdk import Policy, instrumented

T = TypeVar("T")
_MARKER = "_melampus_registration"


def instrument(
    target: T,
    *,
    namespace: str,
    contracts: Mapping[str, Contract],
    generator: str = "unspecified",
    policy: Policy | None = None,
    tracer: Tracer | None = None,
) -> T:
    """Register selected methods on an ordinary instance, module or SimpleNamespace.

    Return the same object with its type preserved. Register before sharing it or
    capturing methods. Previously captured functions bypass the wrappers.
    Properties, custom attribute hooks, class/static methods, classes themselves,
    slot-only objects and generator methods are intentionally unsupported.
    """
    if (
        not isinstance(namespace, str)
        or not namespace
        or not namespace.isprintable()
        or namespace.count(":") > 1
        or any(not part for part in namespace.split(":"))
    ):
        raise ValueError("namespace must be module or module:Class with nonempty parts")
    if not isinstance(contracts, Mapping) or not contracts:
        raise TypeError("contracts must be a nonempty method-to-Contract mapping")
    cls = type(target)
    if inspect.isclass(target) or inspect.isroutine(target):
        raise TypeError("register an instance or module, not a class or function")
    if cls not in (ModuleType, SimpleNamespace) and (
        cls.__getattribute__ is not object.__getattribute__
        or cls.__setattr__ is not object.__setattr__
        or inspect.getattr_static(cls, "__getattr__", None) is not None
    ):
        raise TypeError("custom attribute hooks are unsupported; use a plain boundary object")
    dictionary_descriptor = next(
        (base.__dict__["__dict__"] for base in cls.__mro__ if "__dict__" in base.__dict__), None
    )
    if dictionary_descriptor is not None and not isinstance(
        dictionary_descriptor, (GetSetDescriptorType, MemberDescriptorType)
    ):
        raise TypeError("custom __dict__ descriptors are unsupported")
    try:
        attributes: dict[str, Any] = object.__getattribute__(target, "__dict__")
    except AttributeError as exc:
        raise TypeError(
            "target requires a writable __dict__; slot-only objects are unsupported"
        ) from exc
    if type(attributes) is not dict:
        raise TypeError("target requires a writable instance or module dictionary")
    if _MARKER in attributes:
        raise TypeError("object is already instrumented; register all selected methods once")

    plan: dict[str, Any] = {}
    for name, contract in contracts.items():
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise TypeError("contract keys must name public methods")
        if not isinstance(contract, Contract):
            raise TypeError(f"contract for {name} must be a reviewed Contract")
        # Static inspection never invokes a property or user descriptor.
        descriptor = inspect.getattr_static(target, name, None)
        if inspect.isdatadescriptor(descriptor):
            raise TypeError(f"method {name} uses an unsupported descriptor")
        if name in attributes:
            function = attributes[name]
        elif inspect.isfunction(descriptor):
            function = MethodType(descriptor, target)
        else:
            raise TypeError(f"method {name} is missing or uses an unsupported descriptor")
        if not (inspect.isfunction(function) or inspect.ismethod(function)):
            raise TypeError(f"method {name} must be a Python function or bound method")
        if getattr(function, "_melampus_wrapped", False):
            raise TypeError(f"method {name} is already instrumented; choose one integration style")
        path = f"{namespace}{'.' if ':' in namespace else ':'}{name}"
        wrapped = instrumented(
            intent=contract.intent,
            checks=contract.checks,
            assumptions=contract.assumptions,
            generator=generator,
            policy=policy,
            tracer=tracer,
            path=path,
        )(function)
        plan[name] = wrapped
    # Validate every entry before changing ordinary dictionary entries. Shared
    # class attributes stay untouched; no property setters are evaluated.
    attributes.update(plan)
    attributes[_MARKER] = True
    return target
