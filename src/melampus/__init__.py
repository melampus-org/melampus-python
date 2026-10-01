"""Declare runtime contracts and observe their results through OpenTelemetry."""

from importlib.metadata import version

from .contracts import Contract
from .registration import instrument
from .sdk import DEFAULT_POLICY, Check, Policy, instrumented

__version__ = version("melampus")
__all__ = [
    "Check",
    "Contract",
    "Policy",
    "DEFAULT_POLICY",
    "instrument",
    "instrumented",
    "__version__",
]
