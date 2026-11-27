# abysshub libraries

The public `abysshub` libraries for JavaScript and Python, and the agent skill `abyss-widget` that ships with them. This file holds only the words the sdk adds; the platform's own terms (Widget, Creator, Result, Test Run, Creator Environment, …) are the ones `contract/openapi.json` uses. `docs/adr/0001` says what the publish command does with them.

## Language

**Port**:
A Widget its Creator's own coding agent built, following the `abyss-widget` skill, from a tool the Creator already had somewhere else: a flow, a script, a notebook, an app. Only a tool shaped like a function ports: inputs in, a Result and files out. A tool driven by triggers, schedules or a sign-in on every run is declined.
_Avoid_: migration, import, clone, conversion

**Case**:
One recorded use of the original tool: the inputs it was given and what it produced. A Port is checked against a handful of them, from ordinary uses to one that should fail cleanly. A Template's Cases are the same thing (abysshub-templates).
_Avoid_: test case, fixture, example (an Example Run is the platform's)

**Done List**:
What one Port must do, written by the agent for that tool and confirmed by the Creator before any code is written: which Cases it uses, what each must produce, what may vary and what must hold.
_Avoid_: spec, acceptance criteria, contract

**Check**:
Running a Port on its Cases and judging each against its Done List as passed, failed, or not run (a secret it needs is missing). It runs on the Creator's machine while the agent works, then once on Abyss through the Widget's private link before the Port is done. It claims that the Port works and makes sense on these Cases, never that it equals the original.
_Avoid_: proof (it promises more than a Check gives), parity, verification, Test Run (the platform's run of a Candidate)
