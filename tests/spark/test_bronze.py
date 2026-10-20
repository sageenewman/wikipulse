"""to_bronze keeps every Kafka message as it arrived; it only decodes key and value."""

from datetime import datetime

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import SparkSession  # noqa: E402

from streaming.bronze import to_bronze  # noqa: E402

# The columns the Kafka source produces.
KAFKA_SCHEMA = (
    "key BINARY, value BINARY, topic STRING, partition INT, offset BIGINT, "
    "timestamp TIMESTAMP, timestampType INT, headers ARRAY<STRUCT<key: STRING, value: BINARY>>"
)


def test_a_message_keeps_its_content_and_position(spark: SparkSession) -> None:
    value = '{"meta": {"id": "abc"}, "title": "Flüg 1073"}'
    sent = datetime(2026, 9, 30, 12, 0, 0)
    kafka = spark.createDataFrame(
        [
            (
                b"enwiki:Flight 1073",
                value.encode(),
                "wiki.raw",
                2,
                41,
                sent,
                0,
                [("last_event_id", b'[{"offset": 7}]')],
            )
        ],
        KAFKA_SCHEMA,
    )
    row = to_bronze(kafka).first()
    assert row is not None
    assert row["key"] == "enwiki:Flight 1073"
    assert row["value"] == value  # non-ASCII text survives the decoding
    assert (row["topic"], row["kafka_partition"], row["kafka_offset"]) == ("wiki.raw", 2, 41)
    assert row["kafka_timestamp"] == sent
    assert row["headers"][0]["key"] == "last_event_id"
    assert bytes(row["headers"][0]["value"]) == b'[{"offset": 7}]'
    assert row["ingested_at"] is not None


def test_bronze_has_exactly_the_table_columns(spark: SparkSession) -> None:
    kafka = spark.createDataFrame([], KAFKA_SCHEMA)
    assert to_bronze(kafka).columns == [
        "key",
        "value",
        "topic",
        "kafka_partition",
        "kafka_offset",
        "kafka_timestamp",
        "headers",
        "ingested_at",
    ]
