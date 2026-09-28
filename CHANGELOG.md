# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-28

### Added

- Experimental `code_artifact` schema, generated constants and compatibility fixtures.
- OTel API-only `instrumented` decorator for synchronous and async functions.
- Hash-only declarations, predicate results, deterministic check sampling, shared
  per-process execution limits, and runtime path disabling.
- Optional OTLP/HTTP protobuf watcher with finite sessions, bounded ingestion,
  duplicate suppression and explicit incomplete-evidence exit codes.
- Direct and stock collector demos, test suite, typing, package checks, CI, and
  separate Trusted Publishing workflow for TestPyPI/PyPI.
- Apache-2.0 license, quickstart, contribution and release documentation.

### Known limitations

- Alpha wire/API stability; no content capture, gRPC/JSON receiver, or durable backend.
- The founding spec's <3% overhead target remains unmet; see docs/RELEASE.md.

## [0.0.0] - 2026-08-22

### Added

- Release automation (version guard + auto-tag on merge)
