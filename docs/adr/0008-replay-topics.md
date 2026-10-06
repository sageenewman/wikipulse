# ADR-0008: Replayed data gets its own topics

- **Status:** Accepted
- **Date:** 2026-10-06

## Context
[ADR-0007](0007-ingestion-message-contract.md) puts the upstream stream position in a `last_event_id` header on every message. On startup the live producer reads the newest message in `wiki.raw` and `wiki.dlq` and resumes from the position it carries. That design needs no state store, but it rests on a rule that was never written down: **the live producer is the only writer to those topics.**

Replay broke the rule. It publishes a recording through the same routing code as the live stream, so its messages went to the same topics and carried the position stored in the recording. A code review found the result:

- Stop the live producer, replay a recording of the last ten minutes, start the producer again. It resumes from the replay's position, and everything between the stop and the start of the recording is never ingested.
- Replay a recording from five days ago, then start the producer. It resumes five days back and ingests that history a second time.
- Replay the broken-events sample. The producer sends a position that does not exist upstream.

Recordings are used for tests, load tests, reproducing a problem, tuning detection against a known event, and demos. None of these is production data, and none needs to be in the live topics.

## Decision
- **A replay writes to its own topics:** `wiki.replay` for valid events and `wiki.replay.dlq` for dead letters (`REPLAY_RAW_TOPIC`, `REPLAY_DLQ_TOPIC`). `wiki.replay` has 3 partitions, like `wiki.raw`, so a replay spreads keys the same way. Both are kept for one day.
- **The settings refuse a replay topic that is also a live topic.** The service does not start with such a configuration, so a mistake cannot bring the bug back.
- **The live topics have one writer, the live producer.** Anything else that needs to publish events gets its own topics.
- **Replay and load tests run in the development environment.** The always-on server runs the live producer only. Separate topics keep the data apart; they do not keep the load apart, because the topics share one broker.

Everything else in ADR-0007 stands: the key, the value, the headers and the way the position is recovered.

## Alternatives considered
- **Replay writes no position header, and resume searches backwards for the newest message that has one:** replay could keep writing to `wiki.raw`. But after a large replay the search walks through millions of messages, it adds broker-facing code that is hard to test, and recorded and live data stay mixed in one topic.
- **Store the resume position in a dedicated topic that only the live producer writes** (as Kafka Connect does for source connectors): the strongest protection, since a replay could then write anywhere. It replaces the recovery design of ADR-0007, needs a new topic, periodic position writes and their own tests, and re-reads a few seconds of events after a crash. More than the problem needs today. It becomes the right choice if more writers to the live topics appear.
- **A convention only ("do not replay into the live topics"):** costs nothing and is what the pull request that added replay already said in a note. A note did not prevent the bug.

## Consequences
- ✅ A replay cannot move the live producer's resume point, whatever is replayed and in whatever order the tools are run.
- ✅ Test data and live data never mix, so replay topics can be emptied or have short retention without touching real data.
- ✅ The rule is enforced by configuration validation and covered by tests, not by memory.
- ⚠️ A consumer that should process a recording (a Spark job under test, the dead-letter triage agent) must be pointed at the replay topics. Consumers take their topic from configuration for this reason.
- ⚠️ Replaying the same recording twice appends it twice to `wiki.replay`. A test that needs an exact copy starts from an empty topic.
- ⚠️ Messages replayed into `wiki.raw` before this change still carry a recording's position until retention removes them. An environment that ran such a replay must have its topics emptied once (`make clean` in development).
- ⚠️ The guard compares topic names inside one configuration. It cannot stop a second process that is configured with different live topic names and pointed at the same broker.
