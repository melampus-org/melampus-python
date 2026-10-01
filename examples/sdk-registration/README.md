# Compare decorators, class registration and module boundaries

From the repository root:

```sh
uv sync --locked --all-extras
make demo-registration
```

The command runs the same nonnegative-integer claim through three styles. Each
style goes healthy → deliberate drift → blocked completion → repaired. Removing
a registered module wrapper yields incomplete evidence. No model request,
collector, network export or external account is needed.

| Style | Business source | Setup | Reviewed path |
| --- | --- | --- | --- |
| Decorator | `wrapper.py` | `@PRICE.instrument(path=...)` on a function | `wrapper:price` |
| Class | `service.py` stays plain | `instrument(PricingService(), ...)` in registration.py | `pricing:PricingService.price` |
| Module boundary | `functions.py` stays plain | Registered SimpleNamespace in registration.py | `pricing:price` |

`label()` is deliberately unconfigured. Call through the registered object;
original imports and previously captured methods bypass wrappers. Multiple
instances can use the same reviewed path, but each must be registered.

For a real coding-agent session:

```sh
source .venv/bin/activate
cd examples/sdk-registration
melampus session
```

In a second terminal, activate that environment, enter the same directory, then
start Claude Code and enable the included project hooks. Ask it to change the
service price implementation while keeping reviewed intent/registration intact.
Reads and scoped Edit/Write repairs remain available on drift; progression and
completion require fresh healthy evidence. Other agents can use `melampus gate`.

The executable claim checks bounds/types; it does not prove price accuracy.
Tests can catch the same seeded failure. Melampus adds automatic replay of
reviewed scenarios and the agent gate, rather than replacing unit tests.

[API and scope](../../docs/SDK-REGISTRATION.md) ·
[Research and tradeoffs](../../docs/SDK-UX-RESEARCH.md) ·
[Timed participant study](../pilot_study/README.md)
