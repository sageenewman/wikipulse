# Data Source Notes

What we learned from looking at the real stream, and how each finding changes the design. Update this file whenever the data surprises us.

**Source:** `https://stream.wikimedia.org/v2/stream/recentchange` (Server-Sent Events)
**Schema:** https://schema.wikimedia.org/#!/primary/jsonschema/mediawiki/recentchange

## Sample used

One 60-second capture on 2026-10-04, 07:40 UTC (a Sunday morning): 1,855 events. This is a single small sample, so treat the percentages as rough. Re-measure on a 24-hour recording in Phase 1.

## Findings

### 1. Most of the stream is not article edits
| Slice | Share of events |
|---|---|
| `type = categorize` (category membership changes) | 49% |
| `type = edit` | 41% |
| `type = log` (admin actions: blocks, deletions, uploads) | 8% |
| `type = new` (page creation) | 2% |

One real edit can emit several `categorize` events, one per affected category. Counting them as edits would create fake spikes.

**Adaptation:** spike detection counts only `type in (edit, new)`. Bronze keeps every type.

### 2. Most events are not from Wikipedia at all
| Wiki | Share |
|---|---|
| `commonswiki` (media files) | 47% |
| `wikidatawiki` | 13% |
| `enwiki` | 12% |
| all other wikis | 28% |

**Adaptation:** silver carries a `project` column derived from `wiki` / `server_name` (wikipedia, commons, wikidata, wiktionary, ...). Detection runs on Wikipedia projects only.

### 3. Namespace matters
Namespace `0` (real articles) is only 32% of events. Namespace `14` (categories) is 51%, and `6` (files) is 11%. Talk, user and project pages make up the rest.

**Adaptation:** detection uses `namespace = 0` only.

### 4. The useful signal is small
Human edits to Wikipedia articles (`type in (edit, new)`, `namespace = 0`, `bot = false`, a Wikipedia project) were **9% of events: about 2.7 per second**, against 31 per second in total.

**Adaptation:**
- Total volume is about 2.7M events/day and the signal about 230K/day. The pipeline is sized for far more than the live stream needs, so scale claims must come from **replay load tests**, not from live volume.
- A 5-minute window may hold too few edits per page on small wikis. Window size and minimum-activity thresholds must be tuned on recorded data.

### 5. Hebrew Wikipedia is sparse
`hewiki` produced 3 events in the sample minute.

**Adaptation:** the Hebrew Wikipedia view is descriptive (daily and hourly stats). Spike detection on `hewiki` needs longer windows or lower thresholds, and may not be statistically meaningful.

### 6. Bots are a third of the stream
`bot = true` on 32% of events.

**Adaptation:** as planned, keep the flag everywhere and exclude bots from detection.

### 7. Fields depend on the event type
- `revision`, `length` and `minor` exist only on `edit` and `new`.
- `log_id`, `log_type`, `log_action`, `log_params` exist only on `log`.
- `id` and `user` are occasionally missing.
- `patrolled` and `notify_url` are optional.

**Adaptation:** the schema treats all of these as nullable. A missing `revision` on a `categorize` event is valid and must not go to the DLQ. Validation requires only `meta.id`, `meta.dt`, `type` and `wiki`.

### 8. Two timestamps, a few seconds apart
`timestamp` is when the change happened (seconds). `meta.dt` is when the event was produced (milliseconds). The gap was p50 1.6s, p99 7.2s, max 19.7s.

**Adaptation:** event time is `timestamp`. A watermark of about one minute covers normal lateness. Lateness after a reconnect or replay still has to be measured.

### 9. Deduplication key
`meta.id` is a UUID per event, and there were no duplicates in normal operation. Duplicates are expected only after a reconnect.

**Adaptation:** dedupe on `meta.id`, as designed.

### 10. Resume position
Each SSE message carries an `id` with the upstream Kafka topic, partition and timestamp, for example:
`[{"topic":"eqiad.mediawiki.recentchange","partition":0,"timestamp":1791099495075}, ...]`

**Adaptation:** the producer stores the last `id` it delivered and sends it back as `Last-Event-ID` on reconnect.

### 11. Resuming really works, and every event carries its upstream offset
Sending a `Last-Event-ID` with a timestamp five minutes in the past returned 8,550 events in eight seconds, starting exactly at that timestamp. Each event also carries `meta.topic`, `meta.partition` and `meta.offset` from Wikimedia's Kafka, and those offsets were consecutive.

**Adaptation:** the upstream offsets are a free loss detector. `make check-gaps` reads the raw topic and reports missing and duplicated offsets.

### 12. Volume and size, measured on longer runs
- A 10-minute live run carried 21,445 events: about 36 per second, or 3.1M per day. That is a little above the first one-minute sample.
- A 10-minute recording (20,875 events) is 4.3MB gzipped, about 207 bytes per event. At that ratio a day of raw events is roughly 0.65GB compressed.
- In 28,000+ live events, none failed validation and none were canary events.

**Adaptation:** the 0.5GB/day estimate in ADR-0006 was close, and the retention values stay as they are. Redpanda's on-disk size could not be read from the file system, because it preallocates 32MiB per partition segment. Measure it through its metrics once monitoring exists.

### 13. About seven days of history are available on request
`?since=<ISO timestamp>` starts the stream in the past. Ten minutes of history arrived in five seconds. Asking for 30 days back returned events starting 7 days and 3 hours ago, so that is the retention of the busy upstream topic.

**Adaptation:** `make record ARGS="--from <time> --to <time>"` records a past window. A news event can be captured up to a week after it happened.

### 14. Two upstream topics, not merged by time
The stream is fed by one topic per Wikimedia datacenter: `eqiad.mediawiki.recentchange` and `codfw.mediawiki.recentchange`. In a 15-hour recording, eqiad carried 2,655,517 events and codfw 103. When history is served, each topic arrives in time order, but the quiet topic runs days ahead of the busy one.

**Adaptation:** the recorder writes one part file per upstream topic and merges them by event time. It stops only when every topic has passed the end of the window. Consumers must not assume the stream is globally ordered: within one topic, 2.3% of events were slightly out of order by `meta.dt`.

### 15. Canary events are real
Wikimedia emits a synthetic event every hour at minute 15 (`meta.domain = "canary"`), on the quiet topic. None appeared in the first live samples because they are rare.

**Adaptation:** the producer drops them, as already implemented.

### 16. What a real news event looks like
Recorded: 2026-09-30, 09:00 to 24:00 UTC, the day of the Flydubai Flight 1073 hijacking attempt. 2,655,620 events (49 per second, on a weekday), 484MB gzipped.

Human edits to the English article `Flydubai Flight 1073`, per hour:

| Hour (UTC) | Edits | Editors |
|---|---|---|
| 11 (article created 11:42) | 1 | 1 |
| 12 | 17 | 10 |
| 13 | 14 | 9 |
| 14 | 5 | 4 |
| 15 | 7 | 3 |
| 16 | 19 | 8 |
| 17 | 14 | 10 |
| 18 | 10 | 6 |
| 19 | 13 | 9 |
| 20 | 38 | 21 |
| 21 | 14 | 6 |
| 22 | 15 | 8 |
| 23 | 3 | 2 |

These counts match Wikipedia's own revision history for the article to within a few edits per hour.

**Adaptation:**
- The original rule (at least 5 edits in a 5-minute window) would probably have missed a world news event: the first full hour averaged 1.4 edits per 5 minutes. Windows need to be much longer (30 to 60 minutes), or thresholds lower.
- The number of distinct editors looks like a stronger signal than the number of edits.
- The article did not exist before the event, so there is no per-page baseline. A new page that quickly gathers many editors is itself the signal.
- The event was spread over several titles: `Flydubai` (28 edits), and duplicates such as `Flydubai Flight FZ1073` and `2026 Flydubai plane hijack` that were created in parallel.
- This recording is the first tuning and regression dataset for detection.

## Open questions
- How do volume and the type mix change over 24 hours and during a major news event?
- Is the busy/quiet split between the two upstream topics stable, or does it flip when Wikimedia switches datacenters?
- Do `canary` test events (`meta.domain = "canary"`) appear? None in this sample. If they do, drop them at ingestion.
