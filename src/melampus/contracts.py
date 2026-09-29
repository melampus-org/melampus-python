"""Reviewed intent shared by generated implementations and the local supervisor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from .sdk import Check, instrumented

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class Contract:
    """Keep intent and predicates outside the implementation an agent is repairing.

    Session contract modules expose CONTRACTS: dict[str, Contract], keyed by the
    exact module:qualified_name. Review these claims before starting a session.
    """

    intent: str
    checks: tuple[Check, ...]
    assumptions: tuple[str, ...] = ()

    def instrument(
        self, *, generator: str = "unspecified"
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        return instrumented(
            intent=self.intent,
            checks=self.checks,
            assumptions=self.assumptions,
            generator=generator,
        )
