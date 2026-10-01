# Timed Python SDK integration pilot

This ports the TypeScript 0.2.0 pilot to native Python decorators, class instances
and grouped module functions. It collects feedback locally with the participant's
usual editor and uses fresh Melampus scenarios to verify task completion.

## Validate the collection workflow

```sh
uv sync --locked --all-extras
make demo-pilot
```

This is a **synthetic walkthrough**, not human feedback. It supplies scripted
edits, answers and notes for all styles and checks detection/block/repair.
Reports under `pilot-results/demo-.../` say SYNTHETIC; their timings cannot
establish human onboarding speed or comfort.

## Run with a participant

```sh
make pilot ARGS='--participant p01 --rotation 0'
# Optional persistent directory:
make pilot ARGS='--participant p01 --rotation 0 --dir /path/to/p01-study'
```

Python/session dependencies must already be installed in the same environment.
Environment installation is outside the timers. Task time starts when integration
instructions appear and includes reading, edits and gate evaluation. This measures
integration into a prepared service, not machine setup.

Open the printed style directory in the participant's editor. Type `check` after
editing or `pause` at any prompt; Ctrl+C/EOF also saves and pauses. Repeat the
same command/options to resume. One-second checkpoints retain active timing;
an unexpected termination excludes downtime, records an interruption and can
lose up to one second since the last checkpoint. Verify an earlier process stopped
before removing a stale `.lock`. One runner owns each directory. A completed
study remains completed; use a new participant ID/directory for another trial.

Use pseudonymous IDs. Nothing is uploaded. `pilot-results/` is Git-ignored.
Review free-text responses before sharing them. Treat test/demo-generated
responses as scripted data even when exercising participant mode in tests.

## Every worksheet measure has a task

| Measure | Participant task | Stored evidence |
| --- | --- | --- |
| Minutes to first passing gate | Instrument only price | Active milliseconds/minutes and all gate attempts |
| Business-code lines changed | Submit the first passing business.py | Added/deleted lines, total and submitted snapshot |
| Minutes to second checked method | Add discount after first pass | Separate timer, attempts and incremental business diff |
| Covered/uncovered calls recognized | Answer six scope questions | Answer, ground truth, correctness and score |
| Understand and repair a failure | Diagnose seeded negative-price drift and repair it | Cause score, explanation, drift, blocked Stop, attempts and fresh gate 0 |
| Setup/error confusion | Answer three prompts per style | Setup, second-method and error-message notes; `none` is valid |
| Preferred style and reason | Compare after all three styles | Explicit wrapper/class/module/no-preference and free-text reason |

The fixture calls price, discount and label on inputs -100, 0 and 250. Price is
initially the only required path. After first pass the harness extends reviewed
intent with discount. Label stays unconfigured. Adding discount early, checking
label or duplicate wrappers fails the task protocol even when the SDK gate is
healthy; reports retain SDK exit separately. Modifying reviewed intent/scenario/
configuration cannot pass a task. Keep the supplied business formulas throughout
integration; the runner changes price later for the repair task.

Wrapper style edits `business.py` with `@PRICE.instrument(path="pilot:price")`
and later `@DISCOUNT.instrument(path="pilot:discount")`. Class style edits
`entry.py` using `instrument(api, namespace="pilot:PricingService", ...)`.
Module style edits `entry.py` using `instrument(api, namespace="pilot", ...)`.
Import `instrument` from `melampus` and reviewed contracts from `intent.py`.

Business-line counts use literal additions + deletions: a replacement counts as
two lines; formatting changes count; CRLF/LF differences do not. Registration
edits in entry.py are excluded, so zero business edits **is not zero setup effort**.
All styles share claims, inputs, runtime and checkpoints. The first gate's
submitted business snapshot anchors the second-method diff.

## Balance learning effects

Assign successive participants rotations 0–5, then repeat:

| Rotation | First | Second | Third |
| --- | --- | --- | --- |
| 0 | wrapper | class | module |
| 1 | wrapper | module | class |
| 2 | class | wrapper | module |
| 3 | class | module | wrapper |
| 4 | module | wrapper | class |
| 5 | module | class | wrapper |

This balances order across six participants but cannot eliminate learning effects.
Apply the same help policy and record facilitator assistance in the notes.
Participants may consult [API documentation](../../docs/SDK-REGISTRATION.md).
The cause-choice score measures basic diagnosis; review the explanation for
deeper understanding. Wrong answers remain wrong after a successful repair.

## Reports and interpretation

- `feedback.md`: worksheet with pending cells empty and mode prominently labeled.
- `feedback.csv`: one row per style, including identity, mode, rotation, status,
  all measures, confusion and preference. Filter completed participant studies
  and exclude scripted/test runs before analyzing human usability.
- `study.json`: full resumable state, attempts, timing, snapshots, quiz answers,
  diagnosis, interruptions and preference.

Preference is supplied by a participant and never inferred from speed/edit count.
Incomplete studies remain incomplete. Synthetic runs validate collection; actual
human participation is required to conclude which API feels comfortable.
