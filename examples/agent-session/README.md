# Try the generation → drift → repair loop

This is a local runnable project for Python 3.11+ on macOS/Linux. It uses SDK
contracts and five inputs without a collector or cloud account. It also includes
a pytest comparison that separates behavioral coverage from Melampus's local
agent-session controls. Claude Code is optional for observing drift and required
for the bundled agent hook integration.

## 1. Install from the release candidate

From the repository root:

```sh
uv sync --locked --all-extras
source .venv/bin/activate
```

Or use `python -m pip install '.[session]' pytest` inside your own virtual environment.
The alpha is not yet published to PyPI; don't assume an unrelated registry
package is this release. After publication the install becomes
`python -m pip install 'melampus[session]==0.1.0'`.

Copy this example into an isolated working directory if you want to experiment
without changing the release checkout. Keep the installed environment active.

## 2. Review the four inputs

- `intent.py`: approved intent and three predicates; `CONTRACTS` requires `pricing:price`.
- `exercise.py`: negative, zero, normal, boundary, and excessive prices.
- `melampus.toml`: source scope, protected settings/instructions, five-second deadline.
- `CLAUDE.md` and `.claude/settings.json`: agent instructions and synchronous hooks.
- `unit_tests/`: a typical smoke test plus contract-equivalent boundary tests.

The predicates check integer/nonnegative/capped outputs. They do not prove a
complete pricing algorithm. The contract belongs to the owner; the agent repairs
`pricing.py` to satisfy it.

## 3. Start the dedicated process

```sh
cd examples/agent-session  # or your copied example directory
melampus session
```

Wait for `READY` and a `healthy` report with 15 passed evaluations (five calls ×
three checks). Leave this terminal running. In a second terminal, activate the
same environment and enter the same directory:

```sh
melampus gate
claude
```

Review/enable the supplied project hooks in Claude Code. `/hooks` lets you inspect
them. If you already have settings, merge these four hook entries rather than
overwriting your configuration. `melampus` must resolve in the hook's PATH; an
absolute executable path is also supported. Don't turn on async execution.

## 4. See drift before doing more work

For a controlled demo, use your editor to change the implementation to:

```python
@PRICE.instrument(generator="example")
def price(cents: int) -> int:
    return cents
```

The dedicated terminal reports `drift`, identifying `nonnegative` and `capped`.
No CI push is needed. Ask Claude:

> Inspect the Melampus evidence and repair pricing.py using the existing SDK
> contract. Keep intent.py and the scenario unchanged. Resume only after the
> supervisor reports healthy.

The hooks block shell/progression and completion, while allowing inspection and
Edit/Write on `pricing.py`. Restoring `min(10000, max(0, cents))` produces fresh
healthy evidence and reopens the gate. Removing the decorator produces incomplete
evidence, even if the return value happens to be valid.

To observe hook decisions without sending a model request:

```sh
printf '%s\n' '{"hook_event_name":"Stop"}' | melampus gate --claude
```

Healthy outputs `{}`; drift/incomplete outputs `decision: block` and repair
evidence. `--claude` uses the hook's JSON protocol and normally exits 0; the
agent-neutral `melampus gate` uses process exit codes 0/1/2.

## 5. Compare it with unit tests

Run the automated comparison from the example directory with no other supervisor
running:

```sh
python compare_with_unit_tests.py
```

It makes two temporary edits, runs real pytest processes, queries a real Melampus
session, prints this table, and restores `pricing.py` even if interrupted:

| Temporary edit | Smoke unit test | Full boundary tests | Melampus | Next agent action |
| --- | --- | --- | --- | --- |
| `return cents` | Pass | Fail | Drift | Blocked |
| Remove `@PRICE.instrument(...)` while keeping correct behavior | Pass | Pass | Incomplete | Blocked |

The first row is a coverage lesson, not a Melampus advantage. A complete unit
test suite catches the same behavioral defect when it runs. The narrow smoke test
passes because `1200` does not exercise either boundary.

The second row shows the added invariant: the reviewed contract must still be
attached to and observed from the generated function. Ordinary behavioral tests
do not care where their evidence came from. You could add a structural unit test
for the decorator, but then you are rebuilding part of Melampus's required-
evidence protocol.

The remaining difference is timing and control. Pytest helps when a person, CI,
or another hook invokes it and honors its exit status. The Melampus supervisor
runs after watched changes, rejects stale or missing evidence, and its Claude Code
hook blocks unrelated progression until the current source revision is healthy.
Keep the unit tests: they remain the broader, mature regression suite.

## 6. Generate a new implementation

After the owner has reviewed the contract, ask the agent to rewrite `pricing.py`
using `PRICE.instrument()` and preserve `pricing:price`. The supervisor accepts
any implementation that satisfies the approved executable claims on the supplied
inputs. Add new targets/contracts only through owner review and a session restart.

Ctrl-C stops the supervisor. Subsequent gates report incomplete instead of using
old evidence. See [the complete behavior and limits](../../docs/AGENT-SESSION.md).
