# Melampus coding session

Implement the approved intent in `intent.py`. Use its Contract.instrument()
decorator on every named function. Do not copy or weaken checks. Keep imports
and inputs compatible with `exercise.py`.

A separate `melampus session` process reexecutes the scenario after source edits.
Hooks request fresh evidence before/after tools and before you finish. A drift
or incomplete result means stop feature work and repair the implementation now.
Read the function/check identifiers in the hook evidence. Use Read/Grep/Glob to
inspect and Edit/Write on the watched implementation to repair it. Shell and
other progression tools are blocked until the evidence is healthy again.

Do not remove instrumentation, modify intent/scenarios/settings, restart the
supervisor to accept changed contracts, or treat missing evidence as success.
If the approved intent is wrong or a repair is impossible, ask the owner. After
three unsuccessful repair attempts, explain the evidence and ask for help.

Healthy only means the reviewed predicates passed for the exercised inputs.
For example, a constant zero implementation satisfies this example's bounds;
pricing accuracy would need a stronger approved contract. Never claim that a
green session proves complete correctness or absence of all AI-generated slop.
