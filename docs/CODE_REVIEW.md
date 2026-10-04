# Code Review Guide

How a pull request is reviewed in this project. It is written so that a reviewer with no prior context, human or automated, can follow it from start to finish.

## The reviewer's job

Find the problems that matter before the code is merged, and say clearly whether it should be merged.

The reviewer is independent of the author:

- **Verify, don't trust.** The PR description is a claim, not evidence. Check it against the code and against what the checks actually report.
- **Report, don't fix.** The reviewer does not push commits to the PR. Fixes are the author's job, so that the review stays a second opinion.
- **Passing tests are not approval.** They show that what was tested works. The review asks what was not tested.
- **Judge the code, not the effort.** A large or carefully described PR gets the same scrutiny as a small one.

## Before reading the diff

1. Read the PR description: why the change exists, what changed, how it was verified, what is not included. If any of the four is missing, that is the first finding.
2. Read [ENGINEERING.md](ENGINEERING.md). It is the standard the code is held to.
3. Read what the change touches: the relevant ADRs in [`adr/`](adr/), [DATA_SOURCE.md](DATA_SOURCE.md) for anything that handles events, and [ROADMAP.md](ROADMAP.md) for where the change fits.
4. Run the checks on the PR branch and record the results:
   ```bash
   make lint
   make typecheck
   make test
   ```
   A failing check is a blocker. Stop and report it.

## What to check

Work through these in order. The order is the priority: a correctness problem matters more than a design problem, which matters more than a naming problem.

### 1. Correctness
- Does the code do what the description says? Trace the main path by hand.
- What happens on the unhappy paths: empty input, malformed input, a missing field, a timeout, a dropped connection, a full queue, a restart in the middle?
- Can data be lost, duplicated or reordered? Under what sequence of events?
- Are resources released on every path, including errors and cancellation?
- In async code: is anything blocking the event loop? Is a cancelled task handled? Can two tasks touch the same state?
- Off-by-one and boundary conditions: first item, last item, exactly at a limit, zero.

### 2. Evidence
- Every "verified" claim in the description should name what was run and what came out. Re-run what is cheap to re-run.
- Which parts of the change were exercised only by hand, or not at all? Name them.
- Are measurements honest about their limits (sample size, duration, one run)?

### 3. Tests
- Does every change in behaviour have a test? Does a bug fix have a test that fails without the fix?
- Would the tests fail if the code were wrong? Pick an important line, imagine it broken, and check that a test would catch it.
- Do tests assert behaviour, or do they mirror the implementation?
- Do tests control time and the network, or do they sleep and reach out?
- Are fakes real implementations of a protocol, or is the type checker being silenced with `cast` or `# type: ignore`?
- Is there code that talks to an external system with no integration test?

### 4. Design
Check against [ENGINEERING.md](ENGINEERING.md), sections 1 and 2:
- Is decision logic free of I/O?
- Does code depend on a protocol at each external boundary, or on a concrete class?
- Are objects created only in the entry point and passed in everywhere else?
- Does each module and function have one responsibility? Is there a long function carrying state that should be a class, or a class that should be a function?
- Was a capability added as a new implementation, or as another branch in existing code?
- Is there abstraction with no second user, dead code, or generality nobody asked for? Simpler is better.

### 5. Errors and observability
- Is any exception caught and dropped? Is there a bare `except`?
- Does every failure end as handled, dead-lettered with a reason, or a loud crash?
- Will an operator be able to tell from logs and metrics that this code is failing?

### 6. Data rules
Check against [ENGINEERING.md](ENGINEERING.md), section 4:
- Does ingestion filter or rewrite anything?
- Does the code assume a message arrives once, or in order?
- Is processing time used where event time is meant?
- Is a field treated as required that [DATA_SOURCE.md](DATA_SOURCE.md) shows to be optional?

### 7. Scope and hygiene
- Does the PR do one thing? Are there unrelated changes?
- Are docs updated in the same PR: roadmap, README commands, ADR for a significant decision, data notes for a data surprise?
- Are there secrets, credentials, personal information or large data files in the diff?
- Are new dependencies justified?

### Do not report
- Formatting, import order, or anything `ruff` and `mypy` already enforce.
- Personal preference with no consequence ("I would have named this differently").
- Problems in code the PR does not touch, unless the change makes them worse. Mention those separately as follow-ups.

## Known traps in this project

Things that have already gone wrong here, or that the data makes easy to get wrong:

- **The stream is not globally ordered.** Two upstream topics feed it, and when history is served the quiet one runs far ahead. Code that assumes time only moves forward is suspect.
- **Most events are not article edits.** About 9% of the stream is human edits to Wikipedia articles. Counting anything else as an edit creates false signal.
- **Fields depend on the event type.** `revision` and `length` exist only on `edit` and `new`.
- **Zero duplicates in a test run is not a guarantee.** Delivery is at-least-once.
- **Short measurements.** A throughput number from a one-second run is an indication, not a benchmark.
- **Code that talks to Kafka with no automated test.** Check whether new broker-facing code is covered by more than a manual run.
- **Long functions with hidden state.** A function with many state-holding locals is where bugs hide.
- **Thresholds chosen without data.** Any number in detection logic should point to the recording or measurement it came from.

## Reporting findings

Verify every finding against the code before reporting it. If you cannot confirm it, report it as a question, not as a defect.

Each finding has:

- **Severity** (see below).
- **Location:** file and line.
- **What is wrong,** in one sentence.
- **Why it matters:** the concrete input or sequence of events that leads to a wrong result, a crash or lost data.
- **Suggested fix,** when one is clear.

### Severity

| Level | Meaning | Effect on merge |
|---|---|---|
| **Blocker** | Wrong behaviour, data loss or duplication, a failing check, a secret in the diff, or a behaviour change with no test | Must be fixed before merge |
| **Should fix** | A violation of [ENGINEERING.md](ENGINEERING.md) that will cost later: untestable structure, a swallowed error, a missing integration test | Fix in this PR, or open a tracked follow-up with a reason |
| **Suggestion** | A simpler or clearer way that changes no behaviour | Author's choice |
| **Question** | Something the reviewer could not confirm either way | Author answers |

## Verdict

End with one of:

- **Approve:** no blockers, and every "should fix" is either fixed or has a tracked follow-up.
- **Request changes:** at least one blocker, or "should fix" items with no plan.

The verdict is a recommendation. The repository owner makes the merge decision.

## Review template

```markdown
## Review of #<number>: <title>

**Verdict:** Approve | Request changes

**Checks:** lint <pass/fail> · typecheck <pass/fail> · tests <n passed, n failed>

**Summary:** two or three sentences on what the change does and the overall state.

### Blockers
1. `path/file.py:42` — what is wrong.
   Why it matters: the input or sequence that breaks.
   Suggested fix: ...

### Should fix
...

### Suggestions
...

### Questions
...

### Not verified
What the reviewer could not check, and why.
```

Leave a section out when it is empty, except **Not verified**: say "nothing" if everything was checked.
