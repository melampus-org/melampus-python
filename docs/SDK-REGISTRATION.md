# Choose the integration style that fits your code

Version 0.2.0 adds `instrument` for existing service instances
and module boundaries. The 0.1.0 artifact supports the existing function
decorators. PyPI publication is separate from GitHub releases.

| Your code | Start with | Main tradeoff |
| --- | --- | --- |
| A few functions you own | `@PRICE.instrument()` | Familiar decorator, one edit per function |
| Existing service class | `instrument(service, ...)` | One explicit setup map; register each instance |
| Plain module functions | Register a `SimpleNamespace` boundary | Business code stays plain; callers must use the boundary |
| Third-party objects, frozen models, slots or dynamic proxies | Decorate a plain adapter function | More explicit glue; avoids surprising mutation |

## Register a service once

Reviewed `intent.py`:

```python
from melampus import Check, Contract

PRICE = Contract(
    intent="Return a nonnegative price in cents",
    checks=(Check("nonnegative", lambda value: value >= 0, "Price is nonnegative."),),
)
CONTRACTS = {"pricing:PricingService.price": PRICE}
```

Plain `service.py`:

```python
class PricingService:
    def price(self, cents: int) -> int:
        return max(0, cents)
```

Application boundary `registration.py`:

```python
from melampus import instrument
from intent import PRICE
from service import PricingService

pricing = instrument(
    PricingService(),
    namespace="pricing:PricingService",
    contracts={"price": PRICE},
    generator="claude-code",
)
pricing.price(-100)
```

The returned object is the same instance and retains its type. Bound method
arguments, instance state, signatures, annotations and docstrings remain intact.
Sync stays sync; async methods are evaluated after `await`. Method references
captured **after** registration remain bound to the registered instance.

Namespace `pricing` emits `pricing:price`; `pricing:PricingService` emits
`pricing:PricingService.price`. Use stable reviewed paths, not instance IDs.
`generator`, `policy` and `tracer` are shared keyword options. Each Contract
owns its intent, assumptions and checks. Explicit `path=` is also available on
`instrumented` and `Contract.instrument`; omitting it retains the 0.1.0 inferred path.

## Group functions at an explicit module boundary

```python
from types import SimpleNamespace
from melampus import instrument
from functions import price, label
from intent import PRICE

pricing = instrument(
    SimpleNamespace(price=price, label=label),
    namespace="pricing",
    contracts={"price": PRICE},
)
pricing.price(-100)  # checked with a recording tracer
pricing.label()  # deliberately unconfigured
price(-100)  # original imported reference: no check
```

An actual Python module is supported too: `instrument(module, ...)` replaces
selected module attributes. Existing `from module import price` references
bypass that replacement. Later attribute/global lookups can reach the replacement,
including module-internal calls. Prefer a `SimpleNamespace` boundary when you
want mutation confined to a newly created object.

## Scope is visible, never automatic

| Call | Evidence |
| --- | --- |
| Registered instance's selected method | Checks its successful result |
| `self.price(...)` on that instance | Reaches the installed wrapper |
| Another unregistered instance | Uncovered |
| Method/reference captured before registration | Uncovered |
| `PricingService.price(instance, ...)` directly | Uncovered |
| Omitted method | Unconfigured; no automatic discovery |
| Required method not exercised in the scenario | Session incomplete (exit 2) |
| A failure followed by a pass in the same scenario | Drift remains (exit 1) |

Every required check must run; the session aggregates evidence by path, not by
instance. Multiple instances may share a reviewed path if intent, assumptions
and exact Check objects match. A conflicting declaration remains incomplete
even if later registrations are valid. This is not per-instance coverage proof.

Registration mutates selected instance/module attributes, never the class.
Register before sharing the object across threads or handing references to a
framework. Register each object once with its full map. Replacing its methods
afterwards bypasses instrumentation; sessions report missing required evidence
when their scenarios only reach the replacement.

Supported targets are ordinary writable Python objects, modules and
`SimpleNamespace`; selected members must be Python functions or bound methods.
Inherited methods and instance-owned function fields are supported. Properties,
custom descriptors, private/dunder names, class/static methods, class objects,
custom attribute hooks, slot-only/frozen objects and generators fail explicitly.
All entries are validated before mutation. No property getter runs during
method discovery. Registration is not a sandbox for arbitrary objects.

Unlike TypeScript's mapped member types, Python's `Mapping[str, Contract]` cannot
statically validate arbitrary method names or predicate return types. Typos fail
at registration; `instrument` preserves the target type and function decorators
preserve parameter/return types. Predicates still must return exactly `bool`.

The core SDK remains OpenTelemetry API-only. Ordinary applications own provider
and export setup; checks need recording spans. Local `melampus session` owns an
always-on provider in each fresh scenario process. No arguments, returned
values, intent prose or exception text are exported. Failures preserve results;
application exceptions and cancellation propagate unchanged. Wire schema stays
at **0.1.0**. Registration does not add argument/state predicates or prove
unexercised behavior; no new performance guarantee is claimed.

## Try it beside an agent

```sh
uv sync --locked --all-extras
make demo-registration
source .venv/bin/activate
cd examples/sdk-registration
melampus session
```

In another terminal, activate the same environment, enter the same example
directory, and start Claude Code with the supplied project hooks enabled.
Ask it to edit `service.py` while preserving registration and reviewed intent.
The supervisor detects edits; hooks block progression/completion on drift or
missing evidence and permit scoped repair. Other automation can call
`melampus gate` and use its 0/1/2 exits. See [session setup](AGENT-SESSION.md).

Run `make demo-pilot` to validate collection across decorator/class/module
styles. Run `make pilot ARGS='--participant p01 --rotation 0'` to collect
participant feedback. See the [pilot guide](../examples/pilot_study/README.md)
and [design research](SDK-UX-RESEARCH.md). Familiar APIs and lower edit counts
are design hypotheses; human comfort and preference require actual participants.
