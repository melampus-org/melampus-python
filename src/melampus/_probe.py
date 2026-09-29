"""Disposable scenario runner. Invoked by the supervisor, never by an agent hook."""

from __future__ import annotations

import importlib
import json
import runpy
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

from . import Contract, sdk
from .watcher import Session, decode


def evaluate(config: dict[str, Any]) -> dict[str, Any]:
    """Execute reviewed scenarios against exactly the reviewed check objects."""
    contracts = getattr(importlib.import_module(config["contracts"]), "CONTRACTS", None)
    if not isinstance(contracts, dict) or not contracts:
        raise ValueError("contract module must expose a nonempty CONTRACTS mapping")
    expected: set[tuple[str, str]] = set()
    for path, contract in contracts.items():
        if (
            not isinstance(path, str)
            or ":" not in path
            or not 1 <= len(path) <= 256
            or not path.isprintable()
            or not isinstance(contract, Contract)
        ):
            raise ValueError("invalid contract entry")
        if not contract.checks or any(check.sample != 1 for check in contract.checks):
            raise ValueError("session contracts require unsampled checks")
        # Validate the SDK declaration even if its implementation never imports.
        contract.instrument()
        expected.update((path, check.id) for check in contract.checks)
    if len(expected) > 256:
        raise ValueError("at most 256 required checks per session")

    declarations: set[str] = set()
    violations: set[str] = set()

    def validate(
        path: str, intent: str, checks: tuple[sdk.Check, ...], assumptions: tuple[str, ...]
    ) -> None:
        contract = contracts.get(path)
        if contract is None:
            return
        if (
            path in declarations
            or intent != contract.intent
            or assumptions != contract.assumptions
            or len(checks) != len(contract.checks)
            or any(a is not b for a, b in zip(checks, contract.checks, strict=True))
        ):
            violations.add(path)
        declarations.add(path)

    findings: list[dict[str, Any]] = []
    session = Session(lambda f: findings.append(asdict(f)) if len(findings) < 32 else None, 10_000)
    observed: set[tuple[str, str]] = set()

    class Exporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            try:
                evidence = decode(encode_spans(spans).SerializeToString())
                session.accept(evidence)
                for item in evidence:
                    for check_id, _, result in item.checks:
                        if result in {"passed", "failed"}:
                            observed.add((item.function, check_id))
                        else:
                            session.invalid += 1
            except (ValueError, TypeError):
                session.invalid += 1
            return SpanExportResult.SUCCESS

    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(Exporter()))
    trace.set_tracer_provider(provider)
    sdk._declaration_validator = validate
    error = False
    try:
        runpy.run_path(config["probe"], run_name="__main__")
    except BaseException:
        # Application output and exception text may contain secrets. Return only
        # a category; users can run their scenario themselves for full debugging.
        error = True
    finally:
        provider.shutdown()
        sdk._declaration_validator = None
    missing = sorted(f"{path}/{check}" for path, check in expected - observed)
    undeclared = sorted(set(contracts) - declarations)
    incomplete = error or missing or undeclared or violations or session.exit_code == 2
    return {
        "exit_code": 2 if incomplete else session.exit_code,
        "findings": findings,
        "missing": missing,
        "undeclared": undeclared,
        "contract_mismatch": sorted(violations),
        "probe_error": error,
        "checks": dict(session.counts),
    }


def main() -> None:
    config = json.loads(Path(sys.argv[1]).read_text())
    sys.path[:0] = config["python_paths"]
    try:
        report = evaluate(config)
    except BaseException:
        report = {"exit_code": 2, "message": "Contract or scenario configuration failed to load."}
    Path(sys.argv[2]).write_text(json.dumps(report))


if __name__ == "__main__":
    main()
