"""Compare a bronze table with its Kafka topic: are messages missing or duplicated?

Each message is identified by its Kafka partition and offset, which bronze keeps.
Safe to run while the bronze job is writing: the table is read at one fixed snapshot,
taken before the topic is read, so messages the job has not reached yet are counted as
not yet written, never as missing. Exits with 1 if anything is missing or duplicated.

Run in the Spark image: `make check-bronze`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from streaming.config import BronzeSettings
from streaming.session import build_session

POSITION = ["kafka_partition", "kafka_offset"]


@dataclass(frozen=True)
class BronzeReport:
    topic_messages: int
    table_rows: int
    # In the topic, older than the table's newest message in that partition, yet not in
    # the table: a hole. Bronze commits whole batches in offset order, so this is a loss.
    missing: int
    # Extra copies of a message in the table.
    duplicates: int
    # In the topic and newer than anything the table has in that partition: the job has
    # not reached it yet. Lag, not an error.
    not_yet_written: int

    @property
    def ok(self) -> bool:
        return self.missing == 0 and self.duplicates == 0


def compare(topic_positions: DataFrame, table_positions: DataFrame) -> BronzeReport:
    """Count lost, duplicated and pending messages in one query.

    Both frames have the columns in POSITION, one row per message (the table may hold
    the same position more than once). They must not change while the query runs: the
    table is read at a fixed snapshot (read_table_positions), and the topic is read once.
    """
    copies = table_positions.groupBy(*POSITION).agg(F.count(F.lit(1)).alias("copies"))
    newest = table_positions.groupBy("kafka_partition").agg(
        F.max("kafka_offset").alias("newest_offset")
    )
    rows = (
        topic_positions.withColumn("in_topic", F.lit(True))
        .join(copies, POSITION, "full_outer")
        .join(newest, "kafka_partition", "left")
    )
    in_topic = F.col("in_topic").isNotNull()
    in_table = F.col("copies").isNotNull()
    # A partition the table has no row of yet has no newest offset: nothing reached.
    reached = F.coalesce(F.col("kafka_offset") <= F.col("newest_offset"), F.lit(False))
    result = rows.agg(
        F.count(F.when(in_topic, 1)).alias("topic_messages"),
        F.coalesce(F.sum("copies"), F.lit(0)).alias("table_rows"),
        F.count(F.when(in_topic & ~in_table & reached, 1)).alias("missing"),
        F.coalesce(F.sum(F.col("copies") - 1), F.lit(0)).alias("duplicates"),
        F.count(F.when(in_topic & ~in_table & ~reached, 1)).alias("not_yet_written"),
    ).first()
    return BronzeReport(**{k: int(v) for k, v in result.asDict().items()})


def read_table_positions(spark: SparkSession, settings: BronzeSettings) -> DataFrame:
    """The table's positions for the source topic, pinned to its current snapshot.

    compare() scans the table more than once. Without a pinned snapshot, a commit by the
    running job between two scans would make the counts disagree with each other.
    """
    table = settings.bronze_table
    current = spark.sql(f"SELECT snapshot_id FROM {table}.refs WHERE name = 'main'").first()
    rows = (
        spark.table(table)
        if current is None  # no commit yet: the table is empty
        else spark.sql(f"SELECT * FROM {table} VERSION AS OF {current['snapshot_id']}")
    )
    return rows.where(F.col("topic") == settings.bronze_source_topic).select(*POSITION)


def read_topic_positions(spark: SparkSession, settings: BronzeSettings) -> DataFrame:
    """Every message the topic still holds. The topic keeps a few days, the table more,
    so table rows older than the topic's retention are never counted as missing."""
    return (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.bronze_source_topic)
        .option("startingOffsets", "earliest")
        .option("endingOffsets", "latest")
        .load()
        .select(F.col("partition").alias("kafka_partition"), F.col("offset").alias("kafka_offset"))
    )


def main() -> None:
    settings = BronzeSettings()
    spark = build_session("check-bronze", settings)
    spark.sparkContext.setLogLevel("WARN")
    # The table first, then the topic: the topic can then only be newer than the table.
    table_positions = read_table_positions(spark, settings)
    topic_positions = read_topic_positions(spark, settings)
    report = compare(topic_positions, table_positions)
    print(json.dumps({"table": settings.bronze_table, **asdict(report), "ok": report.ok}))
    spark.stop()
    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
