import gzip
import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from melampus.watcher import MAX_BODY, Session, decode, make_server

FIXTURES = Path(__file__).parent / "fixtures"


def payload(name="healthy", mutate=None):
    fixture = json.loads((FIXTURES / f"{name}.json").read_text())
    if mutate:
        mutate(fixture)
    request = ExportTraceServiceRequest()
    span = request.resource_spans.add().scope_spans.add().spans.add()
    span.trace_id = bytes.fromhex(fixture["trace_id"])
    span.span_id = bytes.fromhex(fixture["span_id"])
    for key, value in fixture["attributes"].items():
        attr = span.attributes.add(key=key)
        if isinstance(value, list):
            attr.value.array_value.SetInParent()
            for item in value:
                entry = attr.value.array_value.values.add()
                if isinstance(item, str):
                    entry.string_value = item
                else:
                    entry.double_value = item
        else:
            attr.value.string_value = value
    return request.SerializeToString()


@pytest.mark.parametrize(
    "name,code,findings", [("healthy", 0, 0), ("drift", 1, 1), ("suppressed", 2, 0)]
)
def test_contract_fixtures_and_duplicate_delivery(name, code, findings):
    emitted = []
    session = Session(emitted.append)
    evidence = decode(payload(name))
    session.accept(evidence)
    session.accept(evidence)
    assert session.exit_code == code
    assert len(emitted) == findings
    assert sum(session.counts.values()) == 1
    if findings:
        assert emitted[0].check_id == "nonnegative"
        assert emitted[0].trace_id == "01" * 16
        assert emitted[0].observed is False
        assert emitted[0].expected is True


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema.version", "9.0.0"),
        ("intent.hash", "not-a-hash"),
        ("function", "injected\noutput"),
        ("generator", "bad!"),
        ("check.results", ["unknown"]),
        ("check.ids", ["duplicate", "duplicate"]),
        ("check.ids", ["bad!"]),
        ("check.contract_hashes", ["invalid"]),
        ("check.sample_rates", [float("nan")]),
        ("check.sample_rates", [-1.0]),
        ("check.results", []),
        ("check.results", "passed"),
    ],
)
def test_rejects_invalid_wire_contract(key, value):
    data = payload(mutate=lambda f: f["attributes"].update({"code_artifact." + key: value}))
    with pytest.raises(ValueError):
        decode(data)


def test_rejects_missing_fields_and_bad_ids():
    with pytest.raises(ValueError):
        decode(payload(mutate=lambda f: f["attributes"].pop("code_artifact.check.ids")))
    with pytest.raises(ValueError):
        decode(payload(mutate=lambda f: f.update(trace_id="00" * 16)))


def test_capacity_rejects_atomically():
    session = Session(lambda _: None, max_spans=1)
    a = decode(payload())
    b = decode(payload(mutate=lambda f: f.update(span_id="03" * 8)))
    with pytest.raises(ValueError):
        session.accept(a + b)
    assert not session.seen
    assert not session.counts


@pytest.mark.parametrize("result", ["error", "not_executed"])
def test_errors_are_incomplete_not_healthy(result):
    session = Session(lambda _: None)
    session.accept(
        decode(
            payload(
                mutate=lambda f: f["attributes"].update({"code_artifact.check.results": [result]})
            )
        )
    )
    assert session.exit_code == 2


def test_empty_session_is_not_healthy():
    session = Session(lambda _: None)
    session.accept(decode(b""))
    assert session.exit_code == 2


def test_receiver_startup_does_not_require_reverse_dns(monkeypatch):
    def unexpected_dns(*args):
        raise AssertionError("receiver startup must not depend on reverse DNS")

    monkeypatch.setattr("socket.getfqdn", unexpected_dns)
    with make_server("127.0.0.1", 0, Session(lambda _: None)) as server:
        assert server.server_port > 0


@pytest.fixture
def receiver():
    findings = []
    session = Session(findings.append)
    server = make_server("127.0.0.1", 0, session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, session, findings
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(port, method="POST", path="/v1/traces", body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(
            method, path, body=body, headers=headers or {"Content-Type": "application/x-protobuf"}
        )
        response = conn.getresponse()
        return response.status, response.read(), response.getheader("Content-Type")
    finally:
        conn.close()


def test_real_receiver_health_protobuf_and_gzip(receiver):
    port, session, findings = receiver
    assert request(port, "GET", "/healthz")[0] == 200
    assert request(port, "GET", "/missing")[0] == 404
    status, body, kind = request(
        port,
        body=gzip.compress(payload("drift")),
        headers={"Content-Type": "application/x-protobuf", "Content-Encoding": "gzip"},
    )
    assert status == 200 and body == b"" and kind == "application/x-protobuf"
    assert request(port, body=payload("drift"))[0] == 200
    assert len(findings) == 1
    assert session.exit_code == 1


@pytest.mark.parametrize(
    "body,headers,code",
    [
        (b"bad protobuf", {"Content-Type": "application/x-protobuf"}, 400),
        (b"{}", {"Content-Type": "application/json"}, 415),
        (b"", {"Content-Type": "application/x-protobuf", "Content-Encoding": "br"}, 415),
        (b"", {"Content-Type": "application/x-protobuf", "Content-Length": str(MAX_BODY + 1)}, 413),
        (
            gzip.compress(b"x" * (MAX_BODY + 1)),
            {"Content-Type": "application/x-protobuf", "Content-Encoding": "gzip"},
            400,
        ),
        (b"bad gzip", {"Content-Type": "application/x-protobuf", "Content-Encoding": "gzip"}, 400),
    ],
)
def test_receiver_rejects_bad_input_without_healthy_exit(receiver, body, headers, code):
    port, session, _ = receiver
    assert request(port, body=body, headers=headers)[0] == code
    assert session.invalid == 1
    assert session.exit_code == 2


def test_finite_cli_no_telemetry():
    process = subprocess.run(
        [sys.executable, "-m", "melampus", "watch", "--port", "0", "--duration", "0.1"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert process.returncode == 2
    assert "READY " in process.stdout and "SUMMARY " in process.stdout


@pytest.mark.parametrize(
    "args", [["--duration", "nan"], ["--duration", "-1"], ["--port", "65536"], ["--max-spans", "0"]]
)
def test_cli_invalid_configuration(args):
    process = subprocess.run(
        [sys.executable, "-m", "melampus", "watch", *args],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert process.returncode == 2
    assert "error:" in process.stderr


def test_exporter_to_cli_end_to_end():
    process = subprocess.run(
        [sys.executable, "scripts/demo_session.py"], capture_output=True, text=True, timeout=20
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "healthy=0 findings; seeded drift=1 finding" in process.stdout


def test_cli_in_process_reports_empty_session(monkeypatch, capsys):
    from melampus.cli import main

    monkeypatch.setattr(sys, "argv", ["melampus", "watch", "--port", "0", "--duration", "0.01"])
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2
    assert '"spans": 0' in capsys.readouterr().out


def test_cli_startup_failure(monkeypatch, capsys):
    from melampus.cli import main

    def fail(*args):
        raise OSError("address in use")

    monkeypatch.setattr("melampus.watcher.run", fail)
    monkeypatch.setattr(sys, "argv", ["melampus", "watch"])
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2
    assert "address in use" in capsys.readouterr().err


def test_duplicate_attributes_rejected():
    data = ExportTraceServiceRequest.FromString(payload())
    span = data.resource_spans[0].scope_spans[0].spans[0]
    span.attributes.add().CopyFrom(span.attributes[0])
    with pytest.raises(ValueError, match="duplicate"):
        decode(data.SerializeToString())


def test_unrelated_spans_ignored():
    data = ExportTraceServiceRequest()
    data.resource_spans.add().scope_spans.add().spans.add(name="unrelated")
    assert decode(data.SerializeToString()) == []


def test_no_check_declarations_are_incomplete():
    def empty(f):
        for key in f["attributes"]:
            if ".check." in key:
                f["attributes"][key] = []

    session = Session(lambda _: None)
    session.accept(decode(payload(mutate=empty)))
    assert session.exit_code == 2
