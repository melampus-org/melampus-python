# Reviewed SDK registration session

Keep business methods plain in service.py/functions.py. registration.py registers
selected methods with the exact reviewed Contract objects from intent.py. Keep
the wrapper style in wrapper.py for comparison; do not stack integration styles.
Scenarios must call the registered objects. Captured raw functions and other
instances bypass registration. label() is deliberately unconfigured.

The separate melampus session supervisor blocks progression/completion on drift
or incomplete evidence. Inspect the function/check identifiers and repair the
watched implementation with Edit/Write. Leave intent, scenarios, configuration
and hooks unchanged. Do not restart the supervisor to accept new intent.
Ask the owner if reviewed intent needs to change. A healthy gate validates only
required checks on exercised calls, and never proves complete correctness.
