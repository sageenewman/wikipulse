"""Bronze job: every message of a Kafka topic, appended unchanged to an Iceberg table.

Bronze keeps the raw stream so that everything after it can be rebuilt (ADR-0006).
Nothing is parsed or filtered here; that happens in silver.

Run in the Spark image: `make bronze`.
"""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import BronzeSettings
from streaming.log import configure_logging
from streaming.session import build_session

log = logging.getLogger("streaming.bronze")

# The Kafka source's columns as they arrive. Key and value are the producer's UTF-8 text
# (ADR-0007), stored as strings so they can be read directly. Headers stay binary.
# Partition and offset identify each message, so the table can be checked for lost and
# duplicated messages (`make check-bronze`).
BRONZE_COLUMNS = """
    key STRING,
    value STRING,
    topic STRING,
    kafka_partition INT,
    kafka_offset BIGINT,
    kafka_timestamp TIMESTAMP,
    headers ARRAY<STRUCT<key: STRING, value: BINARY>>,
    ingested_at TIMESTAMP
"""


def to_bronze(kafka_rows: DataFrame) -> DataFrame:
    """Kafka source rows to bronze rows: key and value decoded as text, nothing else changed."""
    return kafka_rows.select(
        F.col("key").cast("string").alias("key"),
        F.col("value").cast("string").alias("value"),
        F.col("topic"),
        F.col("partition").alias("kafka_partition"),
        F.col("offset").alias("kafka_offset"),
        F.col("timestamp").alias("kafka_timestamp"),
        F.col("headers"),
        # When this micro-batch ran. Compared with kafka_timestamp, it shows the delay.
        F.current_timestamp().alias("ingested_at"),
    )


def ensure_table(spark: SparkSession, table: str) -> None:
    namespace = table.rsplit(".", 1)[0]
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {namespace}")
    # One partition per day: bronze is read by time range and expired by day (ADR-0006).
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {table} ({BRONZE_COLUMNS}) "
        "USING iceberg PARTITIONED BY (days(kafka_timestamp))"
    )


def start(spark: SparkSession, settings: BronzeSettings) -> StreamingQuery:
    kafka_rows = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.bronze_source_topic)
        # Only used the first time; after that the checkpoint says where to continue.
        .option("startingOffsets", "earliest")
        .option("includeHeaders", "true")
        .option("maxOffsetsPerTrigger", settings.bronze_max_offsets_per_trigger)
        .load()
    )
    return (
        to_bronze(kafka_rows)
        .writeStream.format("iceberg")
        .outputMode("append")
        .queryName("bronze")
        .trigger(processingTime=f"{settings.bronze_trigger_seconds} seconds")
        .option("checkpointLocation", settings.checkpoint_dir)
        # Rows of one batch can belong to two days (around midnight). Without fanout,
        # Iceberg requires the rows of a batch to be sorted by partition.
        .option("fanout-enabled", "true")
        .toTable(settings.bronze_table)
    )


def main() -> None:
    settings = BronzeSettings()
    configure_logging(settings.log_level)
    spark = build_session("bronze", settings)
    spark.sparkContext.setLogLevel("WARN")
    ensure_table(spark, settings.bronze_table)
    query = start(spark, settings)
    log.info(
        "bronze job started",
        extra={
            "topic": settings.bronze_source_topic,
            "table": settings.bronze_table,
            "checkpoint": settings.checkpoint_dir,
            "trigger_seconds": settings.bronze_trigger_seconds,
        },
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()
