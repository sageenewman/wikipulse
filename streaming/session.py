"""The Spark session, with the Iceberg REST catalog registered as `lakehouse`."""

from __future__ import annotations

from pyspark.sql import SparkSession

from streaming.config import CATALOG, LakehouseSettings


def build_session(app_name: str, settings: LakehouseSettings) -> SparkSession:
    catalog = f"spark.sql.catalog.{CATALOG}"
    return (
        SparkSession.builder.appName(app_name)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(catalog, "org.apache.iceberg.spark.SparkCatalog")
        .config(f"{catalog}.type", "rest")
        .config(f"{catalog}.uri", settings.iceberg_catalog_uri)
        .config(f"{catalog}.warehouse", settings.iceberg_warehouse)
        # Table files are read and written by Iceberg's own S3 client. It has no storage
        # credentials: the catalog returns the storage endpoint with each table and signs
        # each request (remote signing, ADR-0012).
        .config(f"{catalog}.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.session.timeZone", "UTC")
        # Set at startup: Spark otherwise logs dozens of INFO lines before a job could
        # lower the level itself.
        .config("spark.log.level", "WARN")
        # One small machine: the default of 200 shuffle partitions is pure overhead.
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
