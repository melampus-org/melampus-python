# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-02

### Added

- Explicit `instrument(target, namespace=..., contracts=...)` registration for
  ordinary Python class instances, modules and grouped function boundaries.
  Selected methods preserve binding, signatures, sync/async behavior and target
  typing; shared classes are untouched and unsupported descriptors fail explicitly.
- Optional stable `path=` on existing function decorators; the inferred path
  and experimental 0.1.0 wire schema remain compatible.
- Three-style registration/repair demo, Claude session example, official-source
  SDK/decorator research and documented scope/bypass tradeoffs.
- Local timed, resumable pilot covering all seven worksheet measures, six task
  order rotations and Markdown/CSV/JSON reports. Synthetic runs are labeled;
  human preference and comfort remain unmeasured.

### Changed

- Permit matching declarations from multiple instances sharing reviewed paths;
  conflicts remain incomplete and passing calls do not erase drift.
- Recommend explicit registration for existing services while retaining native
  decorators as an equal supported choice for small function integrations.

## [0.1.0] - 2026-09-28

### Added

- Local AI coding-session supervisor, reviewed SDK Contract objects, fresh-process
  scenario execution, required-check coverage, and revision-bound repair evidence.
- Agent-neutral gate and synchronous Claude Code hooks that restrict progression
  and completion during drift/incomplete evidence while permitting scoped repair.
- Runnable generation/drift/repair example and setup guide; local coding is the
  first-release focus, with broader service monitoring reserved for expansion.
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
- Local sessions support macOS/Linux and reviewed executable claims on exercised
  inputs; they do not infer arbitrary intent or detect all generated-code defects.
- The founding spec's <3% overhead target remains unmet; see docs/RELEASE.md.

## [0.0.0] - 2026-08-22

### Added

- Release automation (version guard + auto-tag on merge)
