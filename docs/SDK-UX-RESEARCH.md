# Python SDK onboarding: evidence and design decisions

Research date: 2026-10-01. This comparison uses official documentation and the
TypeScript [0.2.0 alpha release](https://github.com/melampus-org/melampus-typescript/releases/tag/v0.2.0),
commit `2af85ad82db624e0c32cdfe54116f57f3789d7db`. It evaluates interaction
patterns; it does not claim adoption rankings or measured Melampus preference.

## Familiarity reduces the concepts users must learn

| Reference | Documented pattern | Melampus design inference | Tradeoff |
| --- | --- | --- | --- |
| [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/instrumentation/) | Function decorators/context managers; libraries depend on the API, applications configure the SDK | Retain decorators and API-only core; the local session supplies tracing automatically | Plain SDK usage still requires a recording provider |
| [OpenTelemetry FastAPI instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html) | `instrument_app(app)` registers an existing application | Offer explicit per-service registration at composition time | We instrument selected business members, not framework traffic automatically |
| [Pydantic validate_call](https://docs.pydantic.dev/latest/concepts/validation_decorator/) | Decorator supports async functions and parameter forms; return validation is optional; input coercion is default | Preserve call signatures, typing and async behavior; clearly state what checks observe | Melampus neither parses inputs nor coerces results; it records reviewed predicate outcomes |
| [AWS Powertools Tracer](https://docs.aws.amazon.com/powertools/python/latest/core/tracer/) | Shared tracer plus `capture_method`; response capture is configurable and default-on | Keep one setup object/map and small decorator examples; expose privacy behavior early | Melampus exports bounded check metadata and hashes, not response content |
| [icontract](https://icontract.readthedocs.io/en/latest/api.html) | `require`/`ensure` decorators; postconditions can refer to result and arguments | Keep reviewed, named claims separate and explain them in terms of executable postconditions | Melampus currently checks results only and gates agent progression; it does not implement all design-by-contract semantics |
| [wrapt](https://wrapt.readthedocs.io/en/master/decorators.html) | Dedicated binding/introspection semantics for functions and methods | Treat binding and signatures as behavior to test; reject unsupported descriptors explicitly | No broad proxy/decorator compatibility claim; use adapters for exotic objects |
| [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) | Compose application dependencies via explicit callables | Register services before handing them to framework handlers/dependency factories | Register before the framework captures a reference; no FastAPI dependency is added |

These are inferred choices from documented patterns. A familiar surface is a
reasonable starting point, but it is not evidence that participants prefer it.

## Recommendation: two entry points, one contract model

For a small function, use `@PRICE.instrument()`: it is discoverable beside the
code, retains the original inferred path and requires no service abstraction.
For an existing service or function group, use
`instrument(target, namespace=..., contracts=...)`: business methods stay plain,
the reviewed map is visible at application setup, and the same object is returned.

Avoid a new base class, global auto-patching, metaclass, class replacement,
framework dependency or automatic discovery of business intent. Those mechanisms
would make scope and side effects harder to explain. Keep explicit member names
and stable paths even though they require a setup map. Keep decorators as a
first-class alternative; Python already has native decorator syntax, unlike the
Node type-stripping constraint behind the TypeScript release's decorator deferral.

## Comfort criteria we can verify now

| Concern | Implementation/verification |
| --- | --- |
| Will it change my calls? | Tests preserve sync/async, arguments, method binding, signatures, docstrings, identity and exception propagation |
| Do I need to rewrite business code? | Class/module-boundary reference integrations edit only entry.py; decorator integration edits business.py |
| What is actually covered? | Examples explicitly exercise captured references, unregistered instances and omitted members; missing required execution yields exit 2 |
| Does a passing instance hide a failing one? | Fresh-process tests retain drift and conflicting declarations across shared paths |
| Does it leak values? | Existing hash/metadata-only telemetry behavior remains; no new content export path |
| Can I undo adoption? | Remove the setup registration or decorators and restart with an owner-reviewed registry; current session deliberately reports missing evidence |
| Can I try it without cloud accounts? | Demos need no LLM request/backend; participant study stays local |

The zero-business-edit metric excludes registration edits and is not zero setup
effort. Both approaches still need reviewed claims, exercise inputs and local
session configuration. A strong unit test can catch the same predicate failure;
the supervisor adds automatic replay, required evidence and agent hook decisions.
See [test/CI comparison](AGENT-SESSION.md).

## What needs human evidence

Use the [counterbalanced pilot](../examples/pilot_study/README.md) to collect
seven worksheet measures: first passing gate time, business-code edits, time to
add a second method, coverage understanding, diagnosis/repair, confusion and
explicit preference/reason. Rotate all six style orders to reduce order bias.
Keep environment setup outside the integration timer and apply equal assistance.

Synthetic tests validate measurement, gates and reporting. They cannot establish
comfort, human onboarding time or which API is best. Review actual participant
comments as well as timing. Revise onboarding before introducing a class decorator
or framework adapter; add one only if feedback identifies a repeated unmet need.
