"""Declare runtime contracts and observe their results through OpenTelemetry."""

from importlib.metadata import version

from .sdk import DEFAULT_POLICY, Check, Policy, instrumented

__version__ = version("melampus")
__all__ = ["Check", "Policy", "DEFAULT_POLICY", "instrumented", "__version__"]
