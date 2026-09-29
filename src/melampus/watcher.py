"""Bounded local OTLP/HTTP receiver for deterministic predicate evidence."""

from __future__ import annotations

import gzip
import io
import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
from typing import Any, cast

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from . import _semconv as sc
from .sdk import IDENTIFIER, MAX_CHECKS, SCHEMA_VERSION

MAX_BODY = 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
RESULTS = {"passed", "failed", "error", "sampled_out", "budget", "disabled", "not_executed"}


@dataclass(frozen=True)
class Evidence:
    trace_id: str
    span_id: str
    function: str
    checks: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class Finding:
    function: str
    check_id: str
    contract_hash: str
    trace_id: str
    span_id: str
    observed: bool = False
    expected: bool = True


def _value(value: Any) -> Any:
    kind = value.WhichOneof("value")
    if kind == "array_value":
        return [_value(item) for item in value.array_value.values]
    if kind in {"string_value", "double_value", "int_value", "bool_value"}:
        return getattr(value, kind)
    raise ValueError("unsupported attribute value")


def decode(payload: bytes) -> list[Evidence]:
    """Validate the whole request before accepting any evidence from it."""
    request = ExportTraceServiceRequest()
    request.ParseFromString(payload)
    evidence = []
    for resource in request.resource_spans:
        for scope in resource.scope_spans:
            for span in scope.spans:
                attrs = {}
                for attr in span.attributes:
                    if not attr.key.startswith("code_artifact."):
                        continue
                    if attr.key in attrs:
                        raise ValueError("duplicate code_artifact attribute")
                    attrs[attr.key] = _value(attr.value)
                if not attrs:
                    continue
                if attrs.get(sc.SCHEMA_VERSION) != SCHEMA_VERSION:
                    raise ValueError("unsupported or missing code_artifact schema version")
                function = attrs.get(sc.FUNCTION)
                if (
                    not isinstance(function, str)
                    or not 1 <= len(function) <= 256
                    or not function.isprintable()
                ):
                    raise ValueError("invalid function identifier")
                generator = attrs.get(sc.GENERATOR)
                if not isinstance(generator, str) or not IDENTIFIER.fullmatch(generator):
                    raise ValueError("invalid generator identifier")
                for name in (sc.INTENT_HASH, sc.ASSUMPTIONS_HASH):
                    if not isinstance(attrs.get(name), str) or not HASH.fullmatch(attrs[name]):
                        raise ValueError("invalid declaration hash")
                arrays = [
                    attrs.get(key)
                    for key in (
                        sc.CHECK_IDS,
                        sc.CHECK_CONTRACT_HASHES,
                        sc.CHECK_SAMPLE_RATES,
                        sc.CHECK_RESULTS,
                    )
                ]
                if any(not isinstance(a, list) for a in arrays):
                    raise ValueError("missing check arrays")
                ids, hashes, rates, results = cast(list[list[Any]], arrays)
                if len(ids) > MAX_CHECKS or any(
                    len(a) != len(ids) for a in (hashes, rates, results)
                ):
                    raise ValueError("misaligned or oversized check arrays")
                if any(not isinstance(i, str) or not IDENTIFIER.fullmatch(i) for i in ids) or len(
                    set(ids)
                ) != len(ids):
                    raise ValueError("invalid or duplicate check identifier")
                if any(not isinstance(h, str) or not HASH.fullmatch(h) for h in hashes):
                    raise ValueError("invalid check contract hash")
                if any(
                    type(r) not in (float, int) or not math.isfinite(r) or not 0 <= r <= 1
                    for r in rates
                ):
                    raise ValueError("invalid check sample rate")
                if any(not isinstance(r, str) or r not in RESULTS for r in results):
                    raise ValueError("invalid check result")
                if (
                    len(span.trace_id) != 16
                    or not any(span.trace_id)
                    or len(span.span_id) != 8
                    or not any(span.span_id)
                ):
                    raise ValueError("invalid trace or span ID")
                evidence.append(
                    Evidence(
                        span.trace_id.hex(),
                        span.span_id.hex(),
                        function,
                        tuple(zip(ids, hashes, results, strict=True)),
                    )
                )
    return evidence


class Session:
    """Deduplicate complete spans within a bounded observation session."""

    def __init__(self, emit: Callable[[Finding], None], max_spans: int = 100_000) -> None:
        if max_spans < 1:
            raise ValueError("max_spans must be positive")
        self.emit = emit
        self.max_spans = max_spans
        self.seen: set[tuple[str, str]] = set()
        self.counts: Counter[str] = Counter()
        self.invalid = 0

    def accept(self, evidence: list[Evidence]) -> None:
        new_ids = {(e.trace_id, e.span_id) for e in evidence} - self.seen
        if len(self.seen) + len(new_ids) > self.max_spans:
            raise ValueError("session span capacity exhausted")
        for item in evidence:
            key = (item.trace_id, item.span_id)
            if key in self.seen:
                continue
            self.seen.add(key)
            for check_id, contract_hash, result in item.checks:
                self.counts[result] += 1
                if result == "failed":
                    self.emit(Finding(item.function, check_id, contract_hash, *key))

    @property
    def exit_code(self) -> int:
        if self.invalid or self.counts["error"] or self.counts["not_executed"]:
            return 2
        if not (self.counts["passed"] + self.counts["failed"]):
            return 2
        return 1 if self.counts["failed"] else 0

    def summary(self) -> dict[str, Any]:
        return {
            "spans": len(self.seen),
            "checks": dict(self.counts),
            "invalid_requests": self.invalid,
            "exit_code": self.exit_code,
        }


def make_server(host: str, port: int, session: Session) -> HTTPServer:
    """Use a serial receiver to bound concurrency and preserve session ordering."""

    class Receiver(HTTPServer):
        def server_bind(self) -> None:
            # HTTPServer does an unnecessary reverse DNS lookup here. On offline
            # or misconfigured hosts it can block readiness for tens of seconds.
            TCPServer.server_bind(self)
            self.server_name = str(self.server_address[0])
            self.server_port = self.server_address[1]

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(1)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def respond(self, status: int, body: bytes = b"", content_type: str = "text/plain") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self.respond(200, b"ready\n") if self.path == "/healthz" else self.respond(404)

        def do_POST(self) -> None:
            if self.path != "/v1/traces":
                self.respond(404)
                return
            if self.headers.get_content_type() != "application/x-protobuf":
                session.invalid += 1
                self.respond(415, b"OTLP/HTTP binary protobuf required\n")
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("chunked requests are unsupported")
                length = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= length <= MAX_BODY:
                    session.invalid += 1
                    self.respond(413)
                    return
                payload = self.rfile.read(length)
                if len(payload) != length:
                    raise ValueError("incomplete request")
                encoding = self.headers.get("Content-Encoding", "identity").lower()
                if encoding == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                        payload = stream.read(MAX_BODY + 1)
                    if len(payload) > MAX_BODY:
                        raise ValueError("decompressed payload too large")
                elif encoding != "identity":
                    session.invalid += 1
                    self.respond(415)
                    return
                session.accept(decode(payload))
            except (ValueError, DecodeError, OSError, EOFError):
                session.invalid += 1
                self.respond(400, b"invalid telemetry or session capacity exceeded\n")
                return
            self.respond(
                200, ExportTraceServiceResponse().SerializeToString(), "application/x-protobuf"
            )

    server = Receiver((host, port), Handler)
    server.timeout = 0.2
    return server


def run(host: str, port: int, duration: float, max_spans: int) -> int:
    def emit(finding: Finding) -> None:
        print("DRIFT " + json.dumps(asdict(finding), sort_keys=True), flush=True)

    session = Session(emit, max_spans)
    with make_server(host, port, session) as server:
        print(f"READY http://{host}:{server.server_port}", flush=True)
        deadline = time.monotonic() + duration if duration else math.inf
        try:
            while time.monotonic() < deadline:
                server.handle_request()
        except KeyboardInterrupt:
            pass
        except TimeoutError:
            session.invalid += 1
    print("SUMMARY " + json.dumps(session.summary(), sort_keys=True), flush=True)
    return session.exit_code
