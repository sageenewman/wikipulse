"""The checker must fail when a message is lost or duplicated, and only then."""

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import DataFrame, SparkSession  # noqa: E402

from streaming.check_bronze import BronzeReport, compare  # noqa: E402


def positions(spark: SparkSession, rows: list[tuple[int, int]]) -> DataFrame:
    return spark.createDataFrame(rows, "kafka_partition INT, kafka_offset BIGINT")


TOPIC = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]


def test_a_complete_table_is_ok(spark: SparkSession) -> None:
    report = compare(positions(spark, TOPIC), positions(spark, TOPIC))
    assert report == BronzeReport(
        topic_messages=5, table_rows=5, missing=0, duplicates=0, not_yet_written=0
    )
    assert report.ok


def test_a_duplicated_message_fails(spark: SparkSession) -> None:
    table = [*TOPIC, (0, 1)]
    report = compare(positions(spark, TOPIC), positions(spark, table))
    assert report.duplicates == 1
    assert report.table_rows == 6
    assert not report.ok


def test_a_hole_is_missing_and_fails(spark: SparkSession) -> None:
    # (0, 1) is gone, but the table has the newer (0, 2): it was lost, not skipped yet.
    table = [(0, 0), (0, 2), (1, 0), (1, 1)]
    report = compare(positions(spark, TOPIC), positions(spark, table))
    assert report.missing == 1
    assert report.not_yet_written == 0
    assert not report.ok


def test_messages_the_job_has_not_reached_are_not_missing(spark: SparkSession) -> None:
    # The job is behind: partition 0 stops at offset 1, partition 1 has nothing yet.
    table = [(0, 0), (0, 1)]
    report = compare(positions(spark, TOPIC), positions(spark, table))
    assert report.missing == 0
    assert report.not_yet_written == 3
    assert report.ok


def test_rows_the_topic_no_longer_holds_are_not_missing(spark: SparkSession) -> None:
    # Retention removed offsets 0 from the topic; the table still has them.
    topic = [(0, 1), (0, 2), (1, 1)]
    report = compare(positions(spark, topic), positions(spark, TOPIC))
    assert report.missing == 0
    assert report.duplicates == 0
    assert report.table_rows == 5
    assert report.ok


def test_a_lost_and_a_duplicated_message_are_both_reported(spark: SparkSession) -> None:
    table = [(0, 0), (0, 2), (0, 2), (1, 0), (1, 1)]
    report = compare(positions(spark, TOPIC), positions(spark, table))
    assert (report.missing, report.duplicates) == (1, 1)
    assert not report.ok


def test_an_empty_table_has_written_nothing_yet(spark: SparkSession) -> None:
    report = compare(positions(spark, TOPIC), positions(spark, []))
    assert report == BronzeReport(
        topic_messages=5, table_rows=0, missing=0, duplicates=0, not_yet_written=5
    )
