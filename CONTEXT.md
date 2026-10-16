# abysshub libraries

The public `abysshub` libraries for JavaScript and Python, and the agent skill that ships with them. Platform words — **Widget**, **Creator**, **Result**, **Creator Environment**, **Test Run** — are used exactly as the api's glossary defines them (`abysshub-api/app/CONTEXT.md`) and never redefined here.

## Language

### Porting

**Port**:
A Widget its Creator's own coding agent built, following the Widget skill, from a tool the Creator already had somewhere else — a flow, a script, a notebook, an app. Only a tool shaped like a function ports: inputs in, a Result and files out; a tool driven by triggers, schedules or a sign-in on every run is declined.
_Avoid_: migration, import, clone, conversion

**Case**:
One recorded use of the original tool: the inputs it was given and what it produced. A Port is checked against a handful of them, from ordinary uses to one that should fail cleanly.
_Avoid_: test case, fixture, example (an Example Run is the Platform's)

**Done List**:
What one Port must do, written by the agent for that tool and confirmed by the Creator before any code is written: which Cases it uses, what each must produce, what may vary and what must hold.
_Avoid_: spec, acceptance criteria, contract

**Check**:
Running a Port on its Cases and judging each against its Done List as passed, failed, or not run (a secret it needs is missing). It runs on the Creator's machine while the agent works, then once on Abyss through the Widget's private link before the Port is done. It claims that the Port works and makes sense on these Cases, never that it equals the original.
_Avoid_: proof (it promises more than a Check gives), parity (the marketing context's word for a cheaper change being as good), verification, Test Run (the Platform's run of a Candidate)
