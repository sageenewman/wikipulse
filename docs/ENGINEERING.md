# Engineering Guidelines

How code in this project is written. These rules apply to every contributor and are what a [code review](CODE_REVIEW.md) checks against.

A rule that a tool can enforce is enforced by a tool. The rest are enforced in review.

## 1. Code structure

### Pure core, I/O at the edges
Code that decides (validation, keys, scoring) does not touch the network, the disk or Kafka. Code that touches them does not decide.

*Example:* `ingestion/events.py` classifies an event and builds its key with no I/O at all, so it is tested without a broker or a network.

### Depend on interfaces, not implementations
Every external system (Kafka, HTTP, the clock, files) sits behind a small interface, written as a `typing.Protocol`. Code depends on the protocol. Tests pass a fake that satisfies the same protocol.

`cast` and `# type: ignore` are not ways around this. Each use needs a comment that says why it is unavoidable.

### One composition root
Only the entry point (`main`) creates objects and wires them together. Everything else receives its dependencies as parameters. A function that builds its own Kafka client cannot be tested without Kafka.

### One reason to change
A module has one responsibility, and so does a function. `main` only wires. A function you have to scroll to read is a candidate for splitting.

### Extend without modifying
A new capability arrives as another implementation of an existing interface, not as another `if` in existing code.

*Example:* replay was added as a second source of messages. The code that routes messages did not change.

## 2. Classes and functions

Python is not Java: a class is used when it has something to hold, not by default.

| Situation | Use |
|---|---|
| State or a lifecycle (open/close, a connection, counters that accumulate) | A class |
| A boundary with an external system | A `Protocol`, and a class that implements it |
| Data passed from place to place | A frozen dataclass |
| A calculation or decision with no state | A function |
| Behaviour that varies | Several implementations of one protocol |
| Producing values one at a time | A generator |

- **No inheritance for code reuse.** Use composition. Inheriting from a library base class (settings, a log formatter, exceptions) is fine.
- **No classes named `Manager`, `Helper` or `Utils`,** no classes that hold only static methods, and no getters and setters.
- **A function carrying a lot of state is a class in disguise.** Many local variables that hold state, or several parameters that always travel together, mean an object is waiting to be named.
- **A class with only `__init__` and one method is a function in disguise.**

## 3. Reliability

### No error is swallowed
Every failure has one of three outcomes: it is handled, it is dead-lettered with a reason, or the process fails loudly. Catching an exception and carrying on silently is not allowed. Catch specific exceptions, never a bare `except`.

### Measure, don't assume
A claim about behaviour (no loss, throughput, size) is backed by a measurement that can be repeated.

*Example:* `make check-gaps` reads the raw topic and reports missing and duplicated events from the upstream offsets.

### Every service reports its state
Structured (JSON) logs and metrics. No `print` in services.

### Resources are released
Files, connections and tasks are closed on every path, including errors and cancellation. Use context managers and `try`/`finally`.

### Async code does not block
No blocking call on the event loop for longer than a moment. A blocking call that is acceptable (startup, shutdown) carries a comment saying so.

## 4. Data rules

These follow from [ADR-0006](adr/0006-data-scope-and-retention.md), [ADR-0007](adr/0007-ingestion-message-contract.md) and [DATA_SOURCE.md](DATA_SOURCE.md).

- **Ingestion never filters and never rewrites.** The raw payload is stored byte for byte. Filtering happens in processing.
- **Assume every message can arrive twice.** Delivery is at-least-once. Downstream steps are idempotent or deduplicate by `meta.id`.
- **Assume messages can arrive out of order.** The stream is fed by more than one upstream topic and is not globally ordered.
- **Use event time, not processing time,** for anything that depends on when something happened.
- **Fields are optional unless the data proves otherwise.** Check [DATA_SOURCE.md](DATA_SOURCE.md) before requiring a field.
- **Look at real data before designing around it.** A surprise in the data is written down in [DATA_SOURCE.md](DATA_SOURCE.md) with the adaptation it needs.

## 5. Tests

- **A change in behaviour comes with a test.** A bug fix comes with a test that fails without the fix.
- **Pure logic gets unit tests.** Code that talks to an external system gets an integration test against the real thing.
- **Tests assert behaviour, not implementation.** A test should survive a refactor that keeps behaviour the same.
- **Tests control time and the network.** Inject the clock, the sleep function and the transport. Tests never sleep for real and never reach the internet.
- **Use real data.** Samples and recordings in `data/samples/`, not only invented events.
- **Live verification is reported.** When a change is checked against the live stream or a real broker, the PR states what was run and the numbers that came out.

## 6. Types, style and configuration

- Type hints everywhere. `mypy` runs in strict mode.
- `ruff` formats and lints. Do not argue with the formatter.
- Names say what a thing is. Comments say why, never what.
- Public functions and classes have a docstring that states behaviour a caller relies on.
- Configuration comes from environment variables through the settings class. No hardcoded hosts, ports or topic names in logic.
- No secrets in the repo.

## 7. Process

- **One PR, one purpose.** The description answers four questions: why, what changed, how it was verified, and what is not included.
- **Every PR is reviewed before it is merged,** following [CODE_REVIEW.md](CODE_REVIEW.md). The reviewer only reports. The author fixes and writes a summary of what changed after the review.
- **Only the repository owner approves a merge,** after reading the PR description and the changes-after-review summary.
- **A significant decision gets an ADR.** A tool choice or an architecture change is recorded in [`docs/adr/`](adr/).
- **Docs change with the code.** The roadmap, the README commands and the data notes are updated in the same PR.

## 8. What is enforced automatically

| Rule | Tool | Status |
|---|---|---|
| Formatting and lint | `ruff` (`make lint`) | Enforced locally |
| Static types, strict | `mypy` (`make typecheck`) | Enforced locally |
| Tests pass | `pytest` (`make test`) | Enforced locally |
| All of the above on every PR | GitHub Actions | Planned |
| Function complexity and length limits | `ruff` | Planned |
| Test coverage of at least 85% | `pytest-cov` | Planned |

"Enforced locally" means the check exists but nothing stops a merge if nobody runs it. Closing that gap is the first item of the quality pass in the [roadmap](ROADMAP.md).
