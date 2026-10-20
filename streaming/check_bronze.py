"""Compare a bronze table with its Kafka topic: are messages missing or duplicated?

Each message is identified by its Kafka partition and offset, which bronze keeps.
Run it when the job has caught up with the topic; messages it has not read yet are
reported as missing. Exits with 1 if anything is missing or duplicated.

Run in the Spark image: `make check-bronze`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from streaming.config import BronzeSettings
from streaming.session import build_session

POSITION = ["kafka_partition", "kafka_offset"]


@dataclass(frozen=True)
class BronzeReport:
    topic_messages: int
    table_rows: int
    missing: int
    duplicates: int

    @property
    def ok(self) -> bool:
        return self.missing == 0 and self.duplicates == 0


def compare(topic_positions: DataFrame, table_positions: DataFrame) -> BronzeReport:
    """Both frames have one row per message, with the columns in POSITION."""
    table_rows = table_positions.count()
    distinct = table_positions.distinct()
    return BronzeReport(
        topic_messages=topic_positions.count(),
        table_rows=table_rows,
        missing=topic_positions.join(distinct, POSITION, "left_anti").count(),
        duplicates=table_rows - distinct.count(),
    )


def main() -> None:
    settings = BronzeSettings()
    spark = build_session("check-bronze", settings)
    spark.sparkContext.setLogLevel("WARN")
    topic_positions = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.bronze_source_topic)
        .option("startingOffsets", "earliest")
        .option("endingOffsets", "latest")
        .load()
        .select(F.col("partition").alias("kafka_partition"), F.col("offset").alias("kafka_offset"))
    )
    # The topic keeps only a few days; the table keeps more. Messages the topic no longer
    # has are not compared, so they never count as missing.
    table_positions = (
        spark.table(settings.bronze_table)
        .where(F.col("topic") == settings.bronze_source_topic)
        .select(*POSITION)
    )
    report = compare(topic_positions, table_positions)
    print(json.dumps({"table": settings.bronze_table, **asdict(report), "ok": report.ok}))
    spark.stop()
    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
