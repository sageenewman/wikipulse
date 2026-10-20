"""Settings of the streaming jobs, read from environment variables."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The Spark catalog name under which the Iceberg REST catalog is registered.
CATALOG = "lakehouse"

LIVE_TOPIC = "wiki.raw"
LIVE_BRONZE_TABLE = f"{CATALOG}.bronze.recentchange"


class LakehouseSettings(BaseSettings):
    """Where Kafka, the Iceberg catalog and object storage are, as seen from the job."""

    model_config = SettingsConfigDict(extra="ignore")

    kafka_bootstrap_servers: str = "redpanda:9092"
    iceberg_catalog_uri: str = "http://iceberg-rest:8181"
    s3_endpoint: str = "http://object-store:9000"
    log_level: str = "INFO"


class BronzeSettings(LakehouseSettings):
    """One bronze job: which topic it reads and which table it appends to."""

    bronze_source_topic: str = LIVE_TOPIC
    bronze_table: str = LIVE_BRONZE_TABLE

    # Each micro-batch is one Iceberg commit and writes at least one file per partition,
    # so a shorter interval means fresher data but more small files.
    bronze_trigger_seconds: int = 60
    # Caps one batch, so a backlog (a long replay, a restart after downtime) is read in
    # several batches instead of one that may not fit in memory.
    bronze_max_offsets_per_trigger: int = 100_000

    checkpoint_root: str = "/checkpoints"

    @model_validator(mode="after")
    def _only_live_data_in_the_live_table(self) -> BronzeSettings:
        # Replayed and test data never mixes with live data (ADR-0008, ADR-0011).
        if self.bronze_table == LIVE_BRONZE_TABLE and self.bronze_source_topic != LIVE_TOPIC:
            raise ValueError(
                f"only {LIVE_TOPIC} may be written to {LIVE_BRONZE_TABLE}, "
                f"not {self.bronze_source_topic}"
            )
        return self

    @property
    def checkpoint_dir(self) -> str:
        # A checkpoint records how far one query has read. Derived from the table, so
        # two jobs writing different tables can never share one.
        return f"{self.checkpoint_root}/{self.bronze_table}"
