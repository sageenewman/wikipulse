"""Tests that need Spark. They run in the Spark image (`make test-spark`), on its Python
3.10, and are skipped where PySpark is not installed (the project environment)."""

from collections.abc import Iterator

import pytest

pyspark = pytest.importorskip("pyspark")

from pyspark.sql import SparkSession  # noqa: E402


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    session = (
        SparkSession.builder.master("local[1]")
        .appName("tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()
